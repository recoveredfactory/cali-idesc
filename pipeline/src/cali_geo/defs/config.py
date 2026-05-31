"""Shared paths and constants for the Cali IDESC pipeline.

Everything is anchored to the project root (the directory containing
``pyproject.toml``) so assets write to a predictable ``data/`` tree regardless
of the working directory Dagster is launched from. ``CALI_GEO_DATA_DIR`` can
override the base for tests or alternate runs.
"""

from __future__ import annotations

import os
from pathlib import Path

# .../src/cali_geo/defs/config.py -> project root is three parents up from defs/
PROJECT_ROOT = Path(__file__).resolve().parents[3]

_DATA_DIR = Path(os.environ.get("CALI_GEO_DATA_DIR", PROJECT_ROOT / "data"))


class Paths:
    """Filesystem layout for pipeline outputs (see plan)."""

    base = _DATA_DIR
    raw = _DATA_DIR / "raw"  # paged native EPSG:6249 (GeoJSONSeq)
    geojson = _DATA_DIR / "geojson"  # reprojected EPSG:4326
    pmtiles = _DATA_DIR / "pmtiles"  # vector tiles (large/dense layers only)
    fragments = _DATA_DIR / "manifest"  # one per-layer manifest fragment, json
    dem = _DATA_DIR / "dem"  # self-hosted green relief image + its placement meta
    dem_image = _DATA_DIR / "dem" / "dem_relief.png"
    dem_meta = _DATA_DIR / "dem" / "dem.json"
    catalog = _DATA_DIR / "catalog.json"  # 357-layer catalog (es)
    translations = _DATA_DIR / "translations.json"  # cached en titles/abstracts
    dist = PROJECT_ROOT / "dist"  # published copy of the manifest
    manifest = PROJECT_ROOT / "dist" / "layers.json"
    manifest_served = _DATA_DIR / "layers.json"  # served alongside geojson/ + pmtiles/

    @classmethod
    def ensure(cls) -> None:
        for d in (cls.raw, cls.geojson, cls.pmtiles, cls.fragments, cls.dem, cls.dist):
            d.mkdir(parents=True, exist_ok=True)


# --- WFS / GeoServer ---------------------------------------------------------
WFS_BASE_URL = "https://ws-idesc.cali.gov.co/geoserver/ows"
WFS_VERSION = "2.0.0"

# --- Projection --------------------------------------------------------------
# Native CRS of (almost) every layer: MAGNA-SIRGAS Cali urban grid (col_urban).
SOURCE_EPSG = "EPSG:6249"
TARGET_EPSG = "EPSG:4326"
# GeoServer placeholder for "no/unknown CRS" -> such layers are not reprojected.
UNKNOWN_EPSG_URN = "urn:ogc:def:crs:EPSG::404000"

# Cali sits at roughly lon -76.5, lat 3.4. A generous bbox used as a sanity
# check that reprojection landed features in the right hemisphere/city.
CALI_BBOX = (-77.2, 2.9, -76.0, 4.0)  # (min_lon, min_lat, max_lon, max_lat)

# --- Tiling decision ("as the case may be") ----------------------------------
# Emit PMTiles when a layer is large/dense; otherwise serve raw GeoJSON.
PMTILES_FEATURE_THRESHOLD = 2000
PMTILES_BYTES_THRESHOLD = 5 * 1024 * 1024  # 5 MB


def partition_key(typename: str) -> str:
    """``workspace:layer`` -> ``workspace__layer`` (colon is illegal in keys)."""
    return typename.replace(":", "__")


def typename(partition_key: str) -> str:
    """Inverse of :func:`partition_key`."""
    return partition_key.replace("__", ":", 1)
