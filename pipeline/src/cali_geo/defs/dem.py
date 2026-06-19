"""Self-hosted DEM relief, baked once per theme from a real elevation model.

The viewer can't tint a grayscale raster (MapLibre has no Mapbox-style
``raster-color``), so the relief is baked ONCE into pre-tinted RGBA PNGs hosted
alongside the rest of ``data/`` — one per theme, placed with a plain ``image``
source using the bbox corners in ``dem.json``.

Source is the public AWS *terrarium* elevation tiles (no key; global coverage,
so the relief extends past the city to both cordilleras flanking the Cauca
valley). For each theme:

1. Fetch terrarium tiles over the Cali bbox at zoom ``DEM_Z`` and decode to
   metres (``elev = R*256 + G + B/256 - 32768``); mosaic + resample to the
   output grid (cached on disk so re-colouring is fast).
2. A single shared WEST hillshade gives the terrain form. Shading is
   DARKEN-ONLY (``f = 1 - shade*(1-hs)``): west-lit faces keep the true ramp
   colour, east faces darken. (Brightening lit faces pushed greens to neon.)
3. Each theme's hypsometric ramp colours by real metres; the low end is tuned
   toward the theme's basemap colour.
4. Alpha is keyed on elevation-above-valley (``coverage_alpha``) so the flat
   valley/city dissolves to transparent — mountains emerge from the basemap,
   the city stays readable, and there's no bbox rectangle.
5. ``pngquant`` compresses the continuous RGBA bake (truecolor would be tens of
   MB at this resolution).
"""

import json
import math
import shutil
import subprocess
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import dagster as dg
import numpy as np
from dagster import AssetExecutionContext
from PIL import Image

from .config import CALI_BBOX, Paths

# We RENDER the relief internally at ~z13-native resolution, then supersample the
# finished image DOWN to OUTPUT_WIDTH with LANCZOS — cleaner than sampling the DEM
# straight to the output grid. OUTPUT_WIDTH is the served PNG width and the real
# file-size knob: the z13 terrain detail is high-entropy, so PNG compression can't
# shrink it much — resolution is what controls weight. 5000px ≈ 10 MB/theme,
# crisp on screen; a dedicated higher-res print bake can bump this later.
RENDER_WIDTH = 8000
OUTPUT_WIDTH = 5000
# Terrarium zoom to fetch. z13 ≈ 19 m/px at this latitude — feeds the render grid
# with real detail (supersampled into the output). z12 would be soft.
DEM_Z = 13
# Shared WEST light (gentle): the look David signed off on.
HS_AZ, HS_ALT, HS_ZFACTOR = 295.0, 42.0, 1.6
# Elevation-keyed alpha: transparent <= VALLEY_M, fully opaque VALLEY_M+ALPHA_FADE.
VALLEY_M, ALPHA_FADE = 1015.0, 150.0
TERRARIUM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"

# Named ramps: (elevation_m, R, G, B) keyed on REAL metres (valley ~950m ->
# Farallones ~4000m). `shade` is the per-theme darken-only depth. Each ramp's low
# end sits near that theme's basemap colour so the relief dissolves into the base.
# Only the live themes are baked: original (default, olive), slate, oscuro (dark).
RELIEF_RAMPS: list[dict] = [
    {
        # Default: soft, pale, muted OLIVE rising over the warm cream base.
        "id": "original",
        "label_es": "Original",
        "label_en": "Original",
        "shade": 0.38,
        "ramp": [
            (900, 220, 218, 200), (1050, 176, 178, 148), (1500, 132, 146, 110),
            (2200, 96, 120, 88), (3000, 66, 92, 66), (4200, 46, 70, 52),
        ],
    },
    {
        # Slate: light, blue, pale-to-medium over the pale cool base.
        "id": "slate",
        "label_es": "Pizarra",
        "label_en": "Slate",
        "shade": 0.40,
        "ramp": [
            (900, 226, 233, 241), (1050, 192, 210, 230), (1500, 156, 184, 216),
            (2200, 120, 156, 202), (3000, 92, 132, 188), (4200, 70, 110, 172),
        ],
    },
    {
        # Dark: deep desaturated slate mountains on a black page (only a hint of
        # cool). Stays dark — the valley dissolves to the black base.
        "id": "oscuro",
        "label_es": "Relieve oscuro",
        "label_en": "Dark hillshade",
        "shade": 0.50,
        "ramp": [
            (900, 46, 49, 55), (1050, 55, 59, 66), (1500, 68, 73, 82),
            (2200, 85, 92, 102), (3000, 104, 112, 124), (4200, 124, 134, 148),
        ],
    },
]

_R = 6378137.0  # WGS84 / web-mercator sphere radius


def _merc(lon: float, lat: float) -> tuple[float, float]:
    x = math.radians(lon) * _R
    y = _R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def _lon2tx(lon: float, z: int) -> float:
    return (lon + 180.0) / 360.0 * (1 << z)


def _lat2ty(lat: float, z: int) -> float:
    s = math.sin(math.radians(lat))
    return (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * (1 << z)


def _load_elevation(width: int, height: int) -> np.ndarray:
    """Terrarium elevation (metres) resampled to height×width, cached on disk."""
    min_lon, min_lat, max_lon, max_lat = CALI_BBOX
    cache = Path(tempfile.gettempdir()) / f"cali_relief_elev_z{DEM_Z}_{width}.npy"
    if cache.exists():
        return np.load(cache)

    tx0 = int(math.floor(_lon2tx(min_lon, DEM_Z)))
    tx1 = int(math.floor(_lon2tx(max_lon, DEM_Z)))
    ty0 = int(math.floor(_lat2ty(max_lat, DEM_Z)))  # north
    ty1 = int(math.floor(_lat2ty(min_lat, DEM_Z)))  # south
    nx, ny = tx1 - tx0 + 1, ty1 - ty0 + 1
    mosaic = np.zeros((ny * 256, nx * 256), np.float32)

    def fetch(tx: int, ty: int):
        url = TERRARIUM_URL.format(z=DEM_Z, x=tx, y=ty)
        req = urllib.request.Request(url, headers={"User-Agent": "cali-relief/1.0"})
        last = None
        for _ in range(5):  # transient network: retry
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    a = np.asarray(Image.open(BytesIO(r.read())).convert("RGB")).astype(np.float32)
                return tx, ty, a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
            except Exception as e:
                last = e
        raise RuntimeError(f"terrarium tile {DEM_Z}/{tx}/{ty} failed after retries: {last}")

    tiles = [(x, y) for x in range(tx0, tx1 + 1) for y in range(ty0, ty1 + 1)]
    with ThreadPoolExecutor(max_workers=16) as ex:
        for tx, ty, elev in ex.map(lambda t: fetch(*t), tiles):
            mosaic[(ty - ty0) * 256:(ty - ty0) * 256 + 256,
                   (tx - tx0) * 256:(tx - tx0) * 256 + 256] = elev

    # Mosaic mercator extent (web-merc is linear in tile space), then nearest-
    # sample onto the north-up output grid that matches the placement bbox.
    def tx2mx(tx): return (tx / (1 << DEM_Z)) * 2 * math.pi * _R - math.pi * _R
    def ty2my(ty): return math.pi * _R - (ty / (1 << DEM_Z)) * 2 * math.pi * _R
    mos_x0, mos_x1 = tx2mx(tx0), tx2mx(tx1 + 1)
    mos_y0, mos_y1 = ty2my(ty0), ty2my(ty1 + 1)  # north, south

    x0, _ = _merc(min_lon, min_lat)
    x1, _ = _merc(max_lon, max_lat)
    _, oy0 = _merc(min_lon, max_lat)  # north edge merc-y
    _, oy1 = _merc(min_lon, min_lat)  # south edge merc-y
    ox = np.linspace(x0, x1, width)
    oy = np.linspace(oy0, oy1, height)
    fx = (ox - mos_x0) / (mos_x1 - mos_x0) * (mosaic.shape[1] - 1)
    fy = (mos_y0 - oy) / (mos_y0 - mos_y1) * (mosaic.shape[0] - 1)
    ix = np.clip(fx, 0, mosaic.shape[1] - 1).astype(int)
    iy = np.clip(fy, 0, mosaic.shape[0] - 1).astype(int)
    elev = mosaic[np.ix_(iy, ix)]
    np.save(cache, elev)
    return elev


def _hillshade(elev: np.ndarray, width: int) -> np.ndarray:
    min_lon, min_lat, max_lon, max_lat = CALI_BBOX
    px_m = (_merc(max_lon, 0)[0] - _merc(min_lon, 0)[0]) / width \
        * math.cos(math.radians((min_lat + max_lat) / 2))
    gy, gx = np.gradient(elev * HS_ZFACTOR, px_m)
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gy, gx)
    azr, altr = math.radians(HS_AZ), math.radians(HS_ALT)
    hs = np.sin(altr) * np.sin(slope) + np.cos(altr) * np.cos(slope) * np.cos((azr - math.pi / 2) - aspect)
    return np.clip(hs, 0, 1)


def _coverage_alpha(elev: np.ndarray) -> np.ndarray:
    """Alpha keyed on elevation-above-valley: the flat valley/city dissolves to
    transparent (basemap shows through, no bbox rectangle); mountains read opaque.
    A border feather guarantees no hard cut where terrain meets the bbox edge."""
    a = np.clip((elev - VALLEY_M) / ALPHA_FADE, 0, 1) ** 0.85
    h, w = elev.shape
    fr = 0.04
    ex = np.clip(np.minimum(np.arange(w), w - 1 - np.arange(w)) / (fr * w), 0, 1)
    ey = np.clip(np.minimum(np.arange(h), h - 1 - np.arange(h)) / (fr * h), 0, 1)
    edge = np.minimum(ey[:, None], ex[None, :])
    return a * edge * 255.0


def build_dem_relief() -> dict:
    """Bake every theme's relief into ``data/dem/dem_<id>.png`` (pngquant'd).

    Writes ``dem.json`` (placement + variant list) and returns it. Safe to run
    standalone (no Dagster instance) — see ``scripts/build_dem.py``.
    """
    Paths.ensure()
    pngquant = shutil.which("pngquant")
    if not pngquant:
        raise RuntimeError(
            "pngquant not found on PATH — needed to compress the relief PNGs. "
            "Install it (apt-get install pngquant) or link a binary into PATH."
        )

    min_lon, min_lat, max_lon, max_lat = CALI_BBOX
    x0, y0 = _merc(min_lon, min_lat)
    x1, y1 = _merc(max_lon, max_lat)
    width = RENDER_WIDTH
    height = max(1, round(width * (y1 - y0) / (x1 - x0)))
    out_w = OUTPUT_WIDTH
    out_h = max(1, round(out_w * (y1 - y0) / (x1 - x0)))

    elev = _load_elevation(width, height)
    hs = _hillshade(elev, width)
    alpha = _coverage_alpha(elev).astype(np.uint8)

    variants = []
    for spec in RELIEF_RAMPS:
        ev = np.array([s[0] for s in spec["ramp"]], np.float32)
        tint = np.stack([np.interp(elev, ev, np.array([s[i] for s in spec["ramp"]], np.float32))
                         for i in (1, 2, 3)], -1)
        f = (1 - spec["shade"] * (1 - hs))[..., None]  # darken-only
        rgb = np.clip(tint * f, 0, 255)
        img = Image.fromarray(np.dstack([rgb, alpha]).astype(np.uint8), "RGBA")
        if (out_w, out_h) != (width, height):  # supersample z13 detail down
            img = img.resize((out_w, out_h), Image.LANCZOS)
        out = Paths.dem / f"dem_{spec['id']}.png"
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            raw = Path(tf.name)
        try:
            img.save(raw)
            subprocess.run(
                [pngquant, "--quality", "65-90", "--speed", "1", "--force",
                 "--strip", "--output", str(out), str(raw)],
                check=True, capture_output=True, text=True,
            )
        finally:
            raw.unlink(missing_ok=True)
        variants.append({
            "id": spec["id"],
            "label_es": spec["label_es"],
            "label_en": spec["label_en"],
            "url": f"dem/dem_{spec['id']}.png",
        })

    # MapLibre `image` source corner order: TL, TR, BR, BL (lon/lat). The image is
    # mercator-rendered over the same bbox, so these corners place it exactly.
    coordinates = [
        [min_lon, max_lat], [max_lon, max_lat], [max_lon, min_lat], [min_lon, min_lat],
    ]
    meta = {
        "coordinates": coordinates,
        "width": out_w,
        "height": out_h,
        "default": "original",
        "variants": variants,
    }
    Paths.dem_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


@dg.asset(
    group_name="manifest",
    description="Bake self-hosted DEM relief PNGs from real elevation (one per theme).",
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
