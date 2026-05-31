"""The per-layer dynamic partition set, shared by the download/tile assets.

Partition keys are sanitized typenames (``workspace__layer``). The set is
populated at runtime by the ``wfs_catalog`` asset from GetCapabilities, so the
357 keys are never hardcoded.
"""

import dagster as dg

layer_partitions = dg.DynamicPartitionsDefinition(name="layer")
