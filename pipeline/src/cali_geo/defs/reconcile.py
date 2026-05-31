"""``catalog_reconciliation`` — confirm the global catalog misses no WFS layers.

GeoServer can be configured so a workspace's layers are excluded from the global
GetCapabilities. This asset probes each declared workspace's own WFS endpoint and
asserts every per-workspace feature type is present in ``catalog.json``. Today the
gap is zero; the check exists to catch future drift.

Note: this only covers WFS (vector). Raster/WMS-WCS coverages (orthophotos, DEM)
in the ``raster`` workspace are a separate modality this pipeline does not ingest.
"""

import json

import dagster as dg
from dagster import AssetExecutionContext
from lxml import etree

from .catalog import _WFS, wfs_catalog
from .config import Paths
from .resources import WfsResource

# GeoServer ships demo workspaces; they are not Cali data.
DEMO_WORKSPACES = {"tiger", "topp", "sf", "ne", "nurc", "sde", "cite", "it.geosolutions"}
_RESERVED_NS = {"xsi", "xml", "wfs", "ows", "gml", "fes", "xlink", "xs"}


@dg.asset(
    deps=[wfs_catalog],
    group_name="catalog",
    description="Cross-check per-workspace WFS endpoints against the global catalog.",
    check_specs=[
        dg.AssetCheckSpec(
            name="no_missing_layers",
            asset="catalog_reconciliation",
            description="every per-workspace feature type is in catalog.json",
        )
    ],
)
def catalog_reconciliation(
    context: AssetExecutionContext, wfs: WfsResource
) -> dg.MaterializeResult:
    global_set = {r["typename"] for r in json.loads(Paths.catalog.read_text("utf-8"))}

    root = etree.fromstring(wfs.get_capabilities_xml())
    prefixes = sorted(
        k
        for k in root.nsmap
        if k and k not in _RESERVED_NS and k not in DEMO_WORKSPACES
    )

    per_workspace: dict[str, object] = {}
    missing: list[str] = []
    for ws in prefixes:
        try:
            xml = wfs.get_capabilities_xml(workspace=ws)
        except Exception as exc:  # noqa: BLE001 - record and continue
            per_workspace[ws] = f"error: {exc}"
            continue
        names = [e.text for e in etree.fromstring(xml).iterfind(f".//{{{_WFS}}}Name")]
        per_workspace[ws] = len(names)
        missing.extend(n for n in names if n and n not in global_set)

    return dg.MaterializeResult(
        metadata={
            "global_layers": len(global_set),
            "workspaces_probed": len(prefixes),
            "missing_count": len(missing),
            "missing": dg.MetadataValue.json(sorted(set(missing))),
            "per_workspace": dg.MetadataValue.json(per_workspace),
        },
        check_results=[
            dg.AssetCheckResult(
                check_name="no_missing_layers",
                passed=len(missing) == 0,
                metadata={"missing_count": len(missing)},
            )
        ],
    )
