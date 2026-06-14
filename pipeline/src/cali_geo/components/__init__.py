"""Custom Dagster Component *types* for cali_geo.

Re-exported here so YAML can refer to them by their short path, e.g.
``type: cali_geo.components.WfsLayerSet`` (Dagster splits on the last dot:
module ``cali_geo.components`` + attribute ``WfsLayerSet``).
"""

from cali_geo.components.wfs_layer_set import LayerSpec, WfsLayerSet

__all__ = ["LayerSpec", "WfsLayerSet"]
