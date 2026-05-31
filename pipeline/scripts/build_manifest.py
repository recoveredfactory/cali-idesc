"""Regenerate dist/layers.json + data/layers.json from the manifest fragments.

Materializes just `viewer_manifest` (its upstreams are treated as already-done),
which inventories every fragment, self-heals `fields`/`numeric_fields` from the
on-disk GeoJSON for older fragments, and folds in the baked DEM relief.

    DAGSTER_HOME="$PWD/.dagster" uv run python scripts/build_manifest.py
"""

from dagster import DagsterInstance, materialize

from cali_geo.defs.layers import viewer_manifest

result = materialize(
    [viewer_manifest],
    instance=DagsterInstance.get(),
    raise_on_error=False,
)
print("OK" if result.success else "FAILED")
