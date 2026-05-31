"""``wfs_catalog`` — enumerate every published layer and seed the partitions.

Parses the WFS GetCapabilities document into one record per feature type
(357 of them across 23 workspaces), writes ``data/catalog.json``, and registers
each as a dynamic ``layer`` partition. The geometry type is not available in
capabilities; it is captured later at download time.
"""

import json

import dagster as dg
from dagster import AssetExecutionContext
from lxml import etree

from .config import Paths, partition_key
from .partitions import layer_partitions
from .resources import WfsResource

_WFS = "http://www.opengis.net/wfs/2.0"
_OWS = "http://www.opengis.net/ows/1.1"


def parse_capabilities(xml: bytes) -> list[dict]:
    """Parse a WFS 2.0 GetCapabilities document into layer records."""
    root = etree.fromstring(xml)
    records: list[dict] = []
    for ft in root.iterfind(f".//{{{_WFS}}}FeatureType"):
        name = (ft.findtext(f"{{{_WFS}}}Name") or "").strip()
        if not name:
            continue
        workspace, _, layer = name.partition(":")
        title = (ft.findtext(f"{{{_WFS}}}Title") or "").strip()
        abstract = (ft.findtext(f"{{{_WFS}}}Abstract") or "").strip()
        crs = (ft.findtext(f"{{{_WFS}}}DefaultCRS") or "").strip()
        bbox = _wgs84_bbox(ft)
        records.append(
            {
                "key": partition_key(name),
                "typename": name,
                "workspace": workspace,
                "layer": layer,
                "title_es": title,
                "abstract_es": abstract,
                "default_crs": crs,
                "bbox": bbox,  # [min_lon, min_lat, max_lon, max_lat] or None
            }
        )
    records.sort(key=lambda r: r["key"])
    return records


def _wgs84_bbox(ft) -> list[float] | None:
    bb = ft.find(f"{{{_OWS}}}WGS84BoundingBox")
    if bb is None:
        return None
    lower = (bb.findtext(f"{{{_OWS}}}LowerCorner") or "").split()
    upper = (bb.findtext(f"{{{_OWS}}}UpperCorner") or "").split()
    if len(lower) != 2 or len(upper) != 2:
        return None
    return [float(lower[0]), float(lower[1]), float(upper[0]), float(upper[1])]


@dg.asset(
    group_name="catalog",
    description="Enumerate every Cali IDESC WFS layer and register dynamic partitions.",
)
def wfs_catalog(context: AssetExecutionContext, wfs: WfsResource) -> dg.MaterializeResult:
    xml = wfs.get_capabilities_xml()
    records = parse_capabilities(xml)

    Paths.ensure()
    Paths.catalog.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    keys = [r["key"] for r in records]
    # Reconcile the dynamic partition set with the live catalog.
    existing = set(context.instance.get_dynamic_partitions(layer_partitions.name))
    to_add = [k for k in keys if k not in existing]
    if to_add:
        context.instance.add_dynamic_partitions(layer_partitions.name, to_add)

    workspaces = sorted({r["workspace"] for r in records})
    return dg.MaterializeResult(
        metadata={
            "num_layers": len(records),
            "num_workspaces": len(workspaces),
            "workspaces": dg.MetadataValue.json(workspaces),
            "partitions_added": len(to_add),
            "catalog_path": dg.MetadataValue.path(str(Paths.catalog)),
            "sample": dg.MetadataValue.json(records[:3]),
        }
    )
