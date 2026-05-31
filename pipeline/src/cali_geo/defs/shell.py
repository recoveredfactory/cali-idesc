"""Thin subprocess wrappers around GDAL and tippecanoe.

These are plain CLI invocations (not Dagster resources). Each raises a
``ShellError`` carrying the command and the tail of stderr so failures surface
usefully in the Dagster run log.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .config import SOURCE_EPSG, TARGET_EPSG


class ShellError(RuntimeError):
    def __init__(self, cmd: list[str], stderr: str):
        self.cmd = cmd
        self.stderr = stderr
        tail = "\n".join(stderr.strip().splitlines()[-12:])
        super().__init__(f"command failed: {' '.join(cmd[:3])} ...\n{tail}")


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ShellError(cmd, proc.stderr or proc.stdout)


def reproject(src: Path, dst: Path, source_epsg: str = SOURCE_EPSG) -> None:
    """Reproject a GeoJSONSeq file from the native CRS to WGS84 GeoJSON.

    The source coordinates carry no CRS tag, so ``-s_srs`` is forced. Output is
    a single FeatureCollection (``.geojson``) that both MapLibre and tippecanoe
    can consume directly.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ogr2ogr",
            "-f",
            "GeoJSON",
            "-s_srs",
            source_epsg,
            "-t_srs",
            TARGET_EPSG,
            "-lco",
            "RFC7946=YES",
            str(dst),
            str(src),
        ]
    )


def convert(src: Path, dst: Path) -> None:
    """Convert to WGS84 GeoJSON using the source's *declared* CRS (no forced -s_srs).

    Used for the handful of layers whose native CRS is unknown/non-6249.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ogr2ogr",
            "-f",
            "GeoJSON",
            "-t_srs",
            TARGET_EPSG,
            "-lco",
            "RFC7946=YES",
            str(dst),
            str(src),
        ]
    )


def to_pmtiles(src: Path, dst: Path, layer: str) -> None:
    """Tile a WGS84 GeoJSON into a single-layer PMTiles archive."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "tippecanoe",
            "-o",
            str(dst),
            "--force",
            "-zg",  # auto-choose max zoom
            "--drop-densest-as-needed",
            "--extend-zooms-if-still-dropping",
            "-l",
            layer,
            str(src),
        ]
    )


def tile_join(parts: list[Path], dst: Path) -> None:
    """Merge per-layer PMTiles into one multi-layer archive."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run(["tile-join", "-o", str(dst), "--force", *[str(p) for p in parts]])


_FIELD_RE = re.compile(
    r"^(\w+):\s+(String|Integer|Integer64|Real|Date|DateTime|Time|Binary)\b"
)


def ogrinfo_summary(path: Path) -> dict:
    """Read feature count, geometry type, extent, and field names from a file.

    Returns ``{"feature_count": int, "geometry_type": str|None,
    "bbox": [minx,miny,maxx,maxy]|None, "fields": [str, ...]}``. Cheap — uses
    ``ogrinfo -so`` which reads metadata without materializing every geometry.
    """
    out: dict = {
        "feature_count": 0,
        "geometry_type": None,
        "bbox": None,
        "fields": [],
        "numeric_fields": [],
    }
    proc = subprocess.run(
        ["ogrinfo", "-so", "-al", str(path)], capture_output=True, text=True
    )
    if proc.returncode != 0:
        return out
    fields: list[str] = []
    numeric: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("Feature Count:"):
            try:
                out["feature_count"] = int(line.split(":", 1)[1])
            except ValueError:
                pass
        elif line.startswith("Geometry:"):
            gt = line.split(":", 1)[1].strip()
            out["geometry_type"] = gt or None
        elif line.startswith("Extent:"):
            # Format: "Extent: (minx, miny) - (maxx, maxy)"
            try:
                a, b = line.split(" - ")
                minx, miny = _pair(a)
                maxx, maxy = _pair(b)
                out["bbox"] = [minx, miny, maxx, maxy]
            except (ValueError, IndexError):
                pass
        else:
            m = _FIELD_RE.match(line)
            if m:
                fields.append(m.group(1))
                if m.group(2) in ("Integer", "Integer64", "Real"):
                    numeric.append(m.group(1))
    out["fields"] = fields
    out["numeric_fields"] = numeric
    return out


def _pair(s: str) -> tuple[float, float]:
    inner = s[s.index("(") + 1 : s.index(")")]
    x, y = inner.split(",")
    return float(x), float(y)
