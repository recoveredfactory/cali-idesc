"""Build the self-hosted green DEM relief without Dagster.

Safe to run beside a live backfill (doesn't touch the Dagster instance). The
`dem_relief` asset wraps the same `build_dem_relief()`; this is the quick path.

    uv run python scripts/build_dem.py
"""

from cali_geo.defs.dem import build_dem_relief

meta = build_dem_relief()
ids = ", ".join(v["id"] for v in meta["variants"])
print(f"built {len(meta['variants'])} relief variants ({meta['width']}x{meta['height']}): {ids}; default={meta['default']}")
