"""Compute per-field styling metadata for every layer, in one streaming pass.

For each layer's on-disk GeoJSON (RAM-safe — GDAL streams, never `json.load`):

1. **Coerce comma-decimal strings** — fields stored like ``"47439,499408"`` /
   ``"1,7"`` (Spanish locale) are typed String by GDAL, so they can't drive a
   ramp. Where detected (and the file is small enough), rewrite the GeoJSON
   adding a ``<field>_num`` REAL sibling **keeping the original string**, and
   re-tile if the layer is served as PMTiles.
2. **Numeric ranges** — MIN/MAX per numeric field (for graduated color/size/width
   ramps), via one ``ogr2ogr -f CSV`` aggregate query.
3. **Categorical values** — distinct values for low-cardinality String fields
   (≤ CAT_MAX distinct), for categorical coloring (e.g. pavement type).

Writes ``numeric_fields`` / ``field_ranges`` / ``field_categories`` back into each
manifest fragment. Idempotent & resumable: skips fragments that already carry
``field_ranges``. Run, then regenerate the manifest:

    uv run python scripts/build_field_stats.py
    DAGSTER_HOME="$PWD/.dagster" uv run python scripts/build_manifest.py
"""

import csv
import io
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from cali_geo.defs.config import Paths
from cali_geo.defs.shell import ogrinfo_summary, to_pmtiles

DECIMAL_RE = re.compile(r"^-?\d+,\d+$")  # comma-decimal: "1,7", "47439,499408"
SAMPLE = 25  # features sampled to sniff comma-decimal string fields
CAT_MAX = 12  # a String field with <= this many distinct values is categorical
COERCE_MAX_BYTES = 200 * 1024 * 1024  # don't rewrite/re-tile giant files
CAT_MAX_BYTES = 60 * 1024 * 1024  # skip distinct-value scans on giant files


def _run_csv(args: list[str]) -> list[dict]:
    """Run an ogr2ogr CSV-to-stdout command, return parsed rows."""
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("\n".join((proc.stderr or "").splitlines()[-5:]))
    return list(csv.DictReader(io.StringIO(proc.stdout)))


def ogr_layer_name(path: Path) -> str:
    out = subprocess.run(
        ["ogrinfo", "-ro", "-so", str(path)], capture_output=True, text=True
    ).stdout
    m = re.search(r"^\d+:\s+(\S+)", out, re.M)
    return m.group(1) if m else path.stem


def sample_rows(path: Path) -> list[dict]:
    return _run_csv(["ogr2ogr", "-f", "CSV", "-limit", str(SAMPLE), "/vsistdout/", str(path)])


def detect_decimal_fields(rows: list[dict], string_fields: list[str]) -> list[str]:
    """String fields whose sampled values look like comma-decimals."""
    out = []
    for f in string_fields:
        vals = [r[f] for r in rows if r.get(f)]
        if vals and all(DECIMAL_RE.match(v) for v in vals):
            out.append(f)
    return out


def coerce(path: Path, layer: str, fields: list[str]) -> None:
    """Rewrite GeoJSON in place, adding `<f>_num` REAL siblings (keep originals)."""
    sel = ", ".join(f'CAST(REPLACE("{f}", \',\', \'.\') AS REAL) AS "{f}_num"' for f in fields)
    sql = f'SELECT *, {sel} FROM "{layer}"'
    with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False) as tf:
        tmp = Path(tf.name)
    tmp.unlink()
    subprocess.run(
        ["ogr2ogr", "-f", "GeoJSON", "-dialect", "SQLITE", "-sql", sql, str(tmp), str(path)],
        capture_output=True, text=True, check=True,
    )
    tmp.replace(path)


def numeric_ranges(path: Path, layer: str, numeric: list[str]) -> dict:
    if not numeric:
        return {}
    sel = ", ".join(f'MIN("{f}") AS "{f}__mn", MAX("{f}") AS "{f}__mx"' for f in numeric)
    rows = _run_csv([
        "ogr2ogr", "-f", "CSV", "-dialect", "SQLITE",
        "-sql", f'SELECT {sel} FROM "{layer}"', "/vsistdout/", str(path),
    ])
    if not rows:
        return {}
    row, ranges = rows[0], {}
    for f in numeric:
        mn, mx = row.get(f"{f}__mn", ""), row.get(f"{f}__mx", "")
        if mn not in ("", None) and mx not in ("", None):
            try:
                ranges[f] = [float(mn), float(mx)]
            except ValueError:
                pass
    return ranges


def categorical_values(path: Path, layer: str, string_fields: list[str]) -> dict:
    cats = {}
    for f in string_fields:
        try:
            rows = _run_csv([
                "ogr2ogr", "-f", "CSV", "-dialect", "SQLITE",
                "-sql", f'SELECT DISTINCT "{f}" AS v FROM "{layer}" WHERE "{f}" IS NOT NULL LIMIT {CAT_MAX + 1}',
                "/vsistdout/", str(path),
            ])
        except RuntimeError:
            continue
        vals = [r["v"] for r in rows if r.get("v") not in (None, "")]
        if 2 <= len(vals) <= CAT_MAX:
            cats[f] = sorted(vals)
    return cats


def main() -> int:
    frags = sorted(Paths.fragments.glob("*.json"))
    done = skip = 0
    for i, fp in enumerate(frags, 1):
        frag = json.loads(fp.read_text("utf-8"))
        key = frag["key"]
        if "field_ranges" in frag:
            skip += 1
            continue
        geo = Paths.geojson / f"{key}.geojson"
        if not geo.exists():
            frag["field_ranges"] = {}
            frag["field_categories"] = {}
            fp.write_text(json.dumps(frag, ensure_ascii=False, indent=2), encoding="utf-8")
            skip += 1
            continue
        try:
            size = geo.stat().st_size
            layer = ogr_layer_name(geo)
            summary = ogrinfo_summary(geo)
            fields = summary.get("fields", [])
            numeric = summary.get("numeric_fields", [])
            string_fields = [f for f in fields if f not in numeric]

            # 1. comma-decimal coercion (small files only)
            cd = detect_decimal_fields(sample_rows(geo), string_fields) if string_fields else []
            if cd and size <= COERCE_MAX_BYTES:
                coerce(geo, layer, cd)
                if frag.get("serve") == "pmtiles":
                    to_pmtiles(geo, Paths.pmtiles / f"{key}.pmtiles", layer=key)
                layer = ogr_layer_name(geo)
                summary = ogrinfo_summary(geo)
                fields = summary.get("fields", [])
                numeric = summary.get("numeric_fields", [])
                string_fields = [f for f in fields if f not in numeric]

            # 2. numeric ranges
            ranges = numeric_ranges(geo, layer, numeric)
            # 3. categorical values (small files only)
            cats = categorical_values(geo, layer, string_fields) if size <= CAT_MAX_BYTES else {}

            frag["fields"] = fields
            frag["numeric_fields"] = numeric
            frag["field_ranges"] = ranges
            frag["field_categories"] = cats
            fp.write_text(json.dumps(frag, ensure_ascii=False, indent=2), encoding="utf-8")
            done += 1
            tag = f"coerce={cd}" if cd else ""
            print(f"[{i}/{len(frags)}] {key}  num={len(ranges)} cat={len(cats)} {tag}", flush=True)
        except Exception as exc:  # noqa: BLE001 — keep the pass going
            print(f"[{i}/{len(frags)}] {key}  ERROR: {exc}", file=sys.stderr, flush=True)
    print(f"\nDONE  computed={done} skipped={skip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
