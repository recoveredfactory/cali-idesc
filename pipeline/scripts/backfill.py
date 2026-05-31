"""Backfill every layer partition (layer_geojson + layer_pmtiles), sequentially.

Resumable: skips any layer whose manifest fragment already records a `serve`
decision. Run with the project venv and DAGSTER_HOME set:

    DAGSTER_HOME="$PWD/.dagster" uv run python scripts/backfill.py
"""

import json
import sys
import time

from dagster import DagsterInstance, materialize

from cali_geo.defs.config import Paths
from cali_geo.defs.layers import layer_geojson, layer_pmtiles
from cali_geo.defs.resources import WfsResource


def already_done(key: str) -> bool:
    frag = Paths.fragments / f"{key}.json"
    if not frag.exists():
        return False
    try:
        return "serve" in json.loads(frag.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False


def main() -> int:
    inst = DagsterInstance.get()
    records = json.loads(Paths.catalog.read_text(encoding="utf-8"))
    keys = [r["key"] for r in records]
    resources = {"wfs": WfsResource()}

    done = skip = fail = 0
    failures: list[str] = []
    t0 = time.time()
    for i, key in enumerate(keys, 1):
        if already_done(key):
            skip += 1
            continue
        tag = f"[{i}/{len(keys)}]"
        try:
            res = materialize(
                [layer_geojson, layer_pmtiles],
                partition_key=key,
                resources=resources,
                instance=inst,
                raise_on_error=False,
            )
        except Exception as exc:  # noqa: BLE001 - keep the backfill going
            fail += 1
            failures.append(key)
            print(f"{tag} ERROR {key}: {exc}", flush=True)
            continue
        if res.success:
            done += 1
            frag = json.loads((Paths.fragments / f"{key}.json").read_text())
            print(
                f"{tag} OK   {key}  ({frag.get('feature_count')} feats, {frag.get('serve')})",
                flush=True,
            )
        else:
            fail += 1
            failures.append(key)
            print(f"{tag} FAIL {key}", flush=True)

    mins = (time.time() - t0) / 60
    print(
        f"\nDONE in {mins:.1f}m — materialized={done} skipped={skip} failed={fail}",
        flush=True,
    )
    if failures:
        print("FAILURES:", ", ".join(failures), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
