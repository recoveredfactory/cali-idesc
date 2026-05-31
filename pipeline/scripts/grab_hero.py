"""Dev helper: materialize specific layers WITHOUT Dagster (safe alongside a
running backfill — no shared instance/SQLite), then regenerate data/layers.json.

    uv run python scripts/grab_hero.py emru:emru_pcp_altura_edificaciones ...
"""

import json
import sys

from cali_geo.defs.config import (
    PMTILES_BYTES_THRESHOLD,
    PMTILES_FEATURE_THRESHOLD,
    Paths,
    partition_key,
)
from cali_geo.defs.resources import WfsResource
from cali_geo.defs.shell import ogrinfo_summary, reproject, to_pmtiles

WFS = WfsResource()


def record_for(key: str) -> dict:
    for r in json.loads(Paths.catalog.read_text("utf-8")):
        if r["key"] == key:
            return r
    return {}


def grab(typename: str) -> None:
    key = partition_key(typename)
    rec = record_for(key)
    Paths.ensure()
    raw = Paths.raw / f"{key}.fc.json"
    out = Paths.geojson / f"{key}.geojson"

    res = WFS.download_geojson(typename, raw)
    assert res.complete, f"incomplete {typename}: {res.number_returned}/{res.number_matched}"
    reproject(raw, out)
    summ = ogrinfo_summary(out)
    nbytes = out.stat().st_size
    fc = res.number_returned

    if fc == 0:
        serve, url = "empty", None
    elif fc > PMTILES_FEATURE_THRESHOLD or nbytes > PMTILES_BYTES_THRESHOLD:
        to_pmtiles(out, Paths.pmtiles / f"{key}.pmtiles", key)
        serve, url = "pmtiles", f"pmtiles/{key}.pmtiles"
    else:
        serve, url = "geojson", f"geojson/{key}.geojson"

    # capture the attribute field names from the first feature (for the viewer)
    fields: list[str] = []
    with raw.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("features"):
        fields = sorted((data["features"][0].get("properties") or {}).keys())

    frag = {
        "key": key,
        "typename": typename,
        "workspace": rec.get("workspace", key.split("__")[0]),
        "layer": rec.get("layer", ""),
        "title_es": rec.get("title_es", ""),
        "abstract_es": rec.get("abstract_es", ""),
        "geometry_type": summ["geometry_type"],
        "feature_count": fc,
        "number_matched": res.number_matched,
        "geojson_bytes": nbytes,
        "bbox": summ["bbox"] or rec.get("bbox"),
        "fields": fields,
        "serve": serve,
        "url": url,
    }
    (Paths.fragments / f"{key}.json").write_text(
        json.dumps(frag, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  grabbed {key}: {fc} feats, {summ['geometry_type']}, serve={serve}, fields={fields}")


def regen_manifest() -> None:
    translations = {}
    if Paths.translations.exists():
        translations = json.loads(Paths.translations.read_text("utf-8"))
    layers = []
    for p in sorted(Paths.fragments.glob("*.json")):
        f = json.loads(p.read_text("utf-8"))
        tr = translations.get(f["key"], {})
        layers.append(
            {
                "key": f["key"],
                "typename": f.get("typename"),
                "workspace": f.get("workspace"),
                "title_es": f.get("title_es", ""),
                "title_en": tr.get("title_en", ""),
                "abstract_es": f.get("abstract_es", ""),
                "abstract_en": tr.get("abstract_en", ""),
                "geometry_type": f.get("geometry_type"),
                "feature_count": f.get("feature_count", 0),
                "serve": f.get("serve", "empty"),
                "url": f.get("url"),
                "bbox": f.get("bbox"),
                "fields": f.get("fields", []),
            }
        )
    manifest = {
        "generated_layers": len(layers),
        "workspaces": sorted({l["workspace"] for l in layers if l["workspace"]}),
        "layers": layers,
    }
    Paths.manifest_served.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  regenerated layers.json ({len(layers)} layers)")


if __name__ == "__main__":
    for tn in sys.argv[1:]:
        grab(tn)
    regen_manifest()
