"""Self-hosted DEM relief, baked once in several color ramps.

The viewer used to fetch the relief live from the IDESC GeoServer WMS on every
pan/zoom — a runtime dependency we don't control, served only as grayscale
(MapLibre can't tint a grayscale raster, and has no Mapbox-style ``raster-color``).
This asset bakes the relief ONCE into a set of green/terrain-tinted RGBA PNGs
hosted alongside the rest of ``data/`` — one per named ramp, so the viewer can
offer a relief-style selector.

For each ramp:
1. WMS ``GetMap`` of the styled (hillshaded) DEM over the Cali bbox, EPSG:3857
   (downloaded once, shared across ramps).
2. ``gdaldem color-relief`` recolors the gray hillshade through the ramp.
3. The WMS alpha band (coverage mask) is re-applied so the no-data border stays
   transparent.

The grayscale source is a *styled* product, so the ramp keys off rendered gray
value (pseudo-elevation), not true metres — but it preserves the baked-in
hillshading, which is what reads as relief. The viewer places each variant with
a plain ``image`` source using the bbox corners recorded in ``dem.json``.
"""

import json
import math
import subprocess
import tempfile
from pathlib import Path

import dagster as dg
import requests
from dagster import AssetExecutionContext

from .config import CALI_BBOX, Paths, WFS_BASE_URL

DEM_LAYER = "raster:dem_modelo_elevacion_digital"
# Long-side resolution of the baked image (px). Higher = crisper when zoomed into
# the hills and better for high-res print export, at the cost of more WMS tiles +
# larger PNGs. ~8000px ≈ 16 m/px over the Cali bbox.
DEM_WIDTH = 8000
# The IDESC WMS rejects a single GetMap above ~4096px ("MaxMemoryExceeded"), so
# anything larger is fetched as a grid of sub-tiles (each ≤ this) and mosaicked.
WMS_MAX_TILE = 4000

# Named ramps: rendered gray value (0–255) -> R G B. Each becomes a selectable
# relief style in the viewer. `default` (first) loads when relief is toggled on.
RELIEF_RAMPS: list[dict] = [
    {
        # Emerald, gently desaturated toward gray (greens still dominate). Default.
        "id": "esmeralda",
        "label_es": "Esmeralda",
        "label_en": "Emerald",
        "ramp": [
            (0, 30, 91, 56), (60, 53, 137, 88), (120, 91, 172, 112),
            (185, 152, 197, 159), (255, 223, 236, 226),
        ],
    },
    {
        # Restored favorite: sandy valley floor rising to green hills.
        "id": "arena_verde",
        "label_es": "Arena y verde",
        "label_en": "Sandy valley",
        "ramp": [
            (0, 216, 200, 158), (60, 200, 196, 140), (130, 150, 175, 100),
            (195, 86, 140, 66), (255, 38, 102, 48),
        ],
    },
    {
        # Deeper olive — muted khaki/olive across the whole range.
        "id": "oliva",
        "label_es": "Oliva",
        "label_en": "Olive",
        "ramp": [
            (0, 54, 58, 30), (70, 84, 88, 44), (140, 124, 124, 68),
            (200, 168, 160, 104), (255, 214, 206, 156),
        ],
    },
    {
        # Dramatic dark-mode hillshade: near-black shadows to bright silver ridges.
        "id": "oscuro",
        "label_es": "Relieve oscuro",
        "label_en": "Dark hillshade",
        "ramp": [
            (0, 8, 10, 14), (90, 38, 44, 54), (160, 96, 104, 118),
            (215, 170, 178, 190), (255, 236, 240, 248),
        ],
    },
]
_R = 6378137.0  # WGS84 / web-mercator sphere radius


def _merc(lon: float, lat: float) -> tuple[float, float]:
    x = math.radians(lon) * _R
    y = _R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-8:])
        raise RuntimeError(f"command failed: {' '.join(cmd[:2])} ...\n{tail}")


def build_dem_relief() -> dict:
    """Download the DEM once and bake every ramp into ``data/dem/dem_<id>.png``.

    Writes ``dem.json`` (placement + variant list) and returns it. Safe to run
    standalone (no Dagster instance) — see ``scripts/build_dem.py``.
    """
    Paths.ensure()
    min_lon, min_lat, max_lon, max_lat = CALI_BBOX
    x0, y0 = _merc(min_lon, min_lat)
    x1, y1 = _merc(max_lon, max_lat)
    width = DEM_WIDTH
    height = max(1, round(width * (y1 - y0) / (x1 - x0)))

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # 1. Styled (grayscale, hillshaded) DEM over the bbox, mercator-rendered.
        #    The WMS caps a single GetMap at ~4096px, so split the image into a
        #    grid of sub-tiles (each ≤ WMS_MAX_TILE) and mosaic them. Tiles are
        #    georeferenced in north-up *pixel* space (positive args dodge GDAL's
        #    negative-coord bug) so gdalbuildvrt stitches them back to width×height.
        cols = math.ceil(width / WMS_MAX_TILE)
        rows = math.ceil(height / WMS_MAX_TILE)
        px = [round(width * c / cols) for c in range(cols + 1)]
        py = [round(height * r / rows) for r in range(rows + 1)]
        tile_tifs: list[str] = []
        for r in range(rows):
            for c in range(cols):
                tw, th = px[c + 1] - px[c], py[r + 1] - py[r]
                # Sub-bbox in mercator: x left→right, y top→bottom (row 0 = top).
                xa = x0 + (x1 - x0) * px[c] / width
                xb = x0 + (x1 - x0) * px[c + 1] / width
                ytop = y1 - (y1 - y0) * py[r] / height
                ybot = y1 - (y1 - y0) * py[r + 1] / height
                params = {
                    "service": "WMS", "version": "1.1.1", "request": "GetMap",
                    "layers": DEM_LAYER, "styles": "", "format": "image/png",
                    "transparent": "true", "srs": "EPSG:3857",
                    "width": str(tw), "height": str(th),
                    "bbox": f"{xa},{ybot},{xb},{ytop}",
                }
                resp = requests.get(WFS_BASE_URL, params=params, timeout=180, allow_redirects=True)
                resp.raise_for_status()
                if "image" not in resp.headers.get("content-type", "").lower():
                    raise RuntimeError(f"WMS DEM tile ({c},{r}) did not return an image: {resp.text[:200]}")
                tile_png = tmp / f"tile_{r}_{c}.png"
                tile_png.write_bytes(resp.content)
                # North-up pixel georef: uly = height - top_row, lry = height - bottom_row.
                tile_tif = tmp / f"tile_{r}_{c}.tif"
                _run([
                    "gdal_translate", "-q", "-a_ullr",
                    str(px[c]), str(height - py[r]), str(px[c + 1]), str(height - py[r + 1]),
                    str(tile_png), str(tile_tif),
                ])
                tile_tifs.append(str(tile_tif))

        src_vrt = tmp / "src.vrt"
        _run(["gdalbuildvrt", "-q", str(src_vrt), *tile_tifs])

        # Shared inputs: gray band + the coverage mask (alpha), north-up so
        # gdalbuildvrt accepts them (positive args dodge GDAL's negative-coord bug).
        gray = tmp / "gray.tif"
        alpha_n = tmp / "alpha_n.tif"
        _run(["gdal_translate", "-q", "-b", "1", str(src_vrt), str(gray)])
        _run(["gdal_translate", "-q", "-b", "4", str(src_vrt), str(tmp / "alpha.tif")])
        ullr = ["-a_ullr", "0", str(height), str(width), "0"]
        _run(["gdal_translate", "-q", *ullr, str(tmp / "alpha.tif"), str(alpha_n)])

        variants = []
        for spec in RELIEF_RAMPS:
            ramp_txt = tmp / f"{spec['id']}.txt"
            ramp_txt.write_text("\n".join(f"{v} {r} {g} {b}" for v, r, g, b in spec["ramp"]) + "\n")
            relief = tmp / f"{spec['id']}.tif"
            relief_n = tmp / f"{spec['id']}_n.tif"
            _run(["gdaldem", "color-relief", str(gray), str(ramp_txt), str(relief), "-q"])
            _run(["gdal_translate", "-q", *ullr, str(relief), str(relief_n)])
            bands = []
            for i in (1, 2, 3):
                b = tmp / f"{spec['id']}_b{i}.tif"
                _run(["gdal_translate", "-q", "-b", str(i), str(relief_n), str(b)])
                bands.append(str(b))
            vrt = tmp / f"{spec['id']}.vrt"
            _run(["gdalbuildvrt", "-q", "-separate", str(vrt), *bands, str(alpha_n)])
            out = Paths.dem / f"dem_{spec['id']}.png"
            _run([
                "gdal_translate", "-q", "-of", "PNG",
                "-colorinterp", "red,green,blue,alpha", str(vrt), str(out),
            ])
            out.with_suffix(".png.aux.xml").unlink(missing_ok=True)  # drop GDAL stats sidecar
            variants.append({
                "id": spec["id"],
                "label_es": spec["label_es"],
                "label_en": spec["label_en"],
                "url": f"dem/dem_{spec['id']}.png",
            })

    # MapLibre `image` source corner order: TL, TR, BR, BL (lon/lat). The image
    # is mercator-rendered over the same bbox, so these corners place it exactly.
    coordinates = [
        [min_lon, max_lat], [max_lon, max_lat], [max_lon, min_lat], [min_lon, min_lat],
    ]
    meta = {
        "coordinates": coordinates,
        "width": width,
        "height": height,
        "default": variants[0]["id"],
        "variants": variants,
    }
    Paths.dem_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


@dg.asset(
    group_name="manifest",
    description="Bake self-hosted DEM relief PNGs (several color ramps; replaces the live WMS).",
)
def dem_relief(context: AssetExecutionContext) -> dg.MaterializeResult:
    meta = build_dem_relief()
    total = sum((Paths.dem / f"dem_{v['id']}.png").stat().st_size for v in meta["variants"])
    return dg.MaterializeResult(
        metadata={
            "variants": dg.MetadataValue.json([v["id"] for v in meta["variants"]]),
            "resolution": f"{meta['width']}x{meta['height']}",
            "total_bytes": total,
        }
    )
