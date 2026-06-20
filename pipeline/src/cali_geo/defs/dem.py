"""Self-hosted DEM relief, baked once per theme from a real elevation model.

The viewer can't tint a grayscale raster (MapLibre has no Mapbox-style
``raster-color``), so the relief is baked ONCE per theme into a pre-tinted raster
PMTiles pyramid hosted alongside the rest of ``data/`` and range-served like the
basemap (``dem.json`` lists the variants + placement bbox). Tiled, not a single
image, so it stays sharp at every zoom on every device.

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
4. Alpha is keyed on elevation-above-valley so the flat valley/city dissolves to
   transparent — mountains emerge from the basemap, the city stays readable, and
   there's no bbox rectangle.
5. The coloured RGBA frame is rendered in horizontal strips straight to a
   disk-backed raw raster, then a raw VRT hands it to GDAL, which slices the
   PMTiles pyramid. Strips + streaming keep peak RAM to one band, so the 16000px
   (z14) bake fits a small box that a full-frame render would OOM.
"""

import hashlib
import json
import math
import sqlite3
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
from pmtiles.convert import mbtiles_to_pmtiles

from .config import CALI_BBOX, Paths

# Relief is rendered at this width, then sliced into a raster PMTiles pyramid (one
# per theme), range-served like the basemap. TILED (not a single image) so it stays
# sharp at every zoom on every device and lazy-loads on mobile — a single image is
# one GPU texture, capped at ~4096px on phones, so it blurred when zoomed in. 16000px
# over the bbox ≈ the z14 terrarium native resolution (the relief's detail ceiling),
# so the pyramid stays crisp one zoom deeper (≈9.5 m/px) than the old 8000px/z13 bake.
RENDER_WIDTH = 16000
# Terrarium zoom to fetch (≈9.5 m/px at this latitude) = the relief's detail ceiling.
DEM_Z = 14
# At 16000px the full-frame float arrays (elev/hillshade/tint are ~0.9–2.8 GB each)
# would OOM a small box, so the bake is rendered in horizontal row strips and written
# straight to a disk-backed raw raster — peak RAM is one strip, not the whole frame.
STRIP_ROWS = 512
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
        # Slate: cool SLATE-GRAY (#708090 family), desaturated — not "blue".
        "id": "slate",
        "label_es": "Pizarra",
        "label_en": "Slate",
        "shade": 0.40,
        "ramp": [
            (900, 227, 230, 235), (1050, 200, 206, 214), (1500, 168, 178, 190),
            (2200, 134, 148, 164), (3000, 106, 122, 140), (4200, 84, 100, 118),
        ],
    },
    {
        # Dark: deep desaturated slate on a black page (only a hint of cool).
        # Darker + a touch more contrast than before; valley dissolves to black.
        "id": "oscuro",
        "label_es": "Relieve oscuro",
        "label_en": "Dark hillshade",
        "shade": 0.58,
        "ramp": [
            (900, 30, 33, 38), (1050, 38, 41, 47), (1500, 50, 54, 62),
            (2200, 68, 74, 85), (3000, 90, 98, 111), (4200, 112, 122, 138),
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


def _px_m(width: int) -> float:
    """Ground sample distance (metres/pixel) of the output grid."""
    min_lon, min_lat, max_lon, max_lat = CALI_BBOX
    return (_merc(max_lon, 0)[0] - _merc(min_lon, 0)[0]) / width \
        * math.cos(math.radians((min_lat + max_lat) / 2))


def _hillshade_strip(elev_strip: np.ndarray, px_m: float) -> np.ndarray:
    """Hillshade of one row strip. Pass a 1-row halo above/below so the gradient's
    central differences match the full-frame result; the caller drops the halo."""
    gy, gx = np.gradient(elev_strip * HS_ZFACTOR, px_m)
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gy, gx)
    azr, altr = math.radians(HS_AZ), math.radians(HS_ALT)
    hs = np.sin(altr) * np.sin(slope) + np.cos(altr) * np.cos(slope) * np.cos((azr - math.pi / 2) - aspect)
    return np.clip(hs, 0, 1)


def _edge_factors(width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    """Separable border feather (per-column, per-row) so terrain meeting the bbox
    edge dissolves rather than cutting hard. Combined per strip as min(ey, ex)."""
    fr = 0.04
    ex = np.clip(np.minimum(np.arange(width), width - 1 - np.arange(width)) / (fr * width), 0, 1)
    ey = np.clip(np.minimum(np.arange(height), height - 1 - np.arange(height)) / (fr * height), 0, 1)
    return ex, ey


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-8:])
        raise RuntimeError(f"command failed: {' '.join(cmd[:2])} ...\n{tail}")


def _render_variant(
    elev: np.ndarray,
    spec: dict,
    dat_path: Path,
    width: int,
    height: int,
    px_m: float,
    ex: np.ndarray,
    ey: np.ndarray,
) -> None:
    """Colour one theme's relief into a disk-backed raw RGBA raster, strip by strip.

    Recomputes the (cheap) shared hillshade + alpha per strip rather than holding
    full-frame copies, so peak RAM is one ``STRIP_ROWS`` band. The output is a flat
    pixel-interleaved (BIP) uint8 buffer — exactly the C layout of an ``(H, W, 4)``
    numpy memmap — which a raw VRT then hands to GDAL without re-reading it into RAM.
    """
    out = np.memmap(dat_path, dtype=np.uint8, mode="w+", shape=(height, width, 4))
    ev = np.array([s[0] for s in spec["ramp"]], np.float32)
    ramp_ch = [np.array([s[i] for s in spec["ramp"]], np.float32) for i in (1, 2, 3)]
    shade = spec["shade"]
    for r0 in range(0, height, STRIP_ROWS):
        r1 = min(r0 + STRIP_ROWS, height)
        h0, h1 = max(0, r0 - 1), min(height, r1 + 1)  # 1-row halo for the gradient
        hs = _hillshade_strip(elev[h0:h1], px_m)[r0 - h0:r0 - h0 + (r1 - r0)]
        e = elev[r0:r1]
        tint = np.stack([np.interp(e, ev, ch) for ch in ramp_ch], -1)
        f = (1 - shade * (1 - hs))[..., None]  # darken-only: lit faces keep true ramp
        rgb = np.clip(tint * f, 0, 255)
        a = (np.clip((e - VALLEY_M) / ALPHA_FADE, 0, 1) ** 0.85) \
            * np.minimum(ey[r0:r1, None], ex[None, :]) * 255.0
        out[r0:r1] = np.dstack([rgb, a]).astype(np.uint8)
    out.flush()
    del out


def _raw_vrt(dat_path: Path, width: int, height: int, ullr: tuple) -> str:
    """A GDAL VRT describing the BIP raw RGBA ``.dat`` as a georeferenced raster, so
    GDAL streams it straight to tiles with no giant PNG decode in RAM."""
    ulx, uly, lrx, lry = ullr
    gt = (ulx, (lrx - ulx) / width, 0.0, uly, 0.0, (lry - uly) / height)
    line_off = 4 * width
    interps = ("Red", "Green", "Blue", "Alpha")
    bands = "\n".join(
        f'  <VRTRasterBand dataType="Byte" band="{b + 1}" subClass="VRTRawRasterBand">\n'
        f"    <ColorInterp>{interps[b]}</ColorInterp>\n"
        f'    <SourceFilename relativeToVRT="0">{dat_path}</SourceFilename>\n'
        f"    <ImageOffset>{b}</ImageOffset>\n"
        f"    <PixelOffset>4</PixelOffset>\n"
        f"    <LineOffset>{line_off}</LineOffset>\n"
        f"  </VRTRasterBand>"
        for b in range(4)
    )
    return (
        f'<VRTDataset rasterXSize="{width}" rasterYSize="{height}">\n'
        f"  <SRS>EPSG:3857</SRS>\n"
        f"  <GeoTransform>{', '.join(repr(v) for v in gt)}</GeoTransform>\n"
        f"{bands}\n"
        f"</VRTDataset>\n"
    )


def _dat_to_pmtiles(dat_path: Path, width: int, height: int, out_pmtiles: Path, ullr: tuple) -> int:
    """Slice the raw RGBA raster into a raster PMTiles pyramid.

    Wraps the ``.dat`` in a VRT (no copy), builds an MBTiles + overviews (the lower
    zooms), then converts to PMTiles. Returns the max zoom level. Needs the GDAL CLI
    (gdal_translate, gdaladdo) on PATH.
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        vrt, mb = tmp / "r.vrt", tmp / "r.mbtiles"
        vrt.write_text(_raw_vrt(dat_path, width, height, ullr), encoding="utf-8")
        _run(["gdal_translate", "-q", "-of", "MBTILES", "-co", "TILE_FORMAT=PNG", str(vrt), str(mb)])
        _run(["gdaladdo", "-q", "-r", "average", str(mb), "2", "4", "8", "16", "32"])
        con = sqlite3.connect(mb)
        maxzoom = int(con.execute("SELECT value FROM metadata WHERE name='maxzoom'").fetchone()[0])
        con.close()
        out_pmtiles.unlink(missing_ok=True)
        mbtiles_to_pmtiles(str(mb), str(out_pmtiles), maxzoom)
    return maxzoom


def build_dem_relief() -> dict:
    """Bake every theme's relief into a raster PMTiles pyramid ``data/dem/dem_<id>.pmtiles``.

    Writes ``dem.json`` (placement + variant list) and returns it. Safe to run
    standalone (no Dagster instance) — see ``scripts/build_dem.py``. Needs GDAL.
    """
    Paths.ensure()
    min_lon, min_lat, max_lon, max_lat = CALI_BBOX
    x0, y0 = _merc(min_lon, min_lat)
    x1, y1 = _merc(max_lon, max_lat)
    width = RENDER_WIDTH
    height = max(1, round(width * (y1 - y0) / (x1 - x0)))
    # GeoTIFF placement: upper-left = (west, north), lower-right = (east, south).
    ullr = (x0, y1, x1, y0)

    elev = _load_elevation(width, height)
    px_m = _px_m(width)
    ex, ey = _edge_factors(width, height)

    variants = []
    # One reusable scratch raster (~0.9 GB at 16000px); overwritten per theme.
    with tempfile.TemporaryDirectory() as td:
        dat = Path(td) / "relief.dat"
        for spec in RELIEF_RAMPS:
            _render_variant(elev, spec, dat, width, height, px_m, ex, ey)
            out = Paths.dem / f"dem_{spec['id']}.pmtiles"
            _dat_to_pmtiles(dat, width, height, out, ullr)
            # Content hash in the URL busts BROWSER cache when the bake changes
            # (dem.json is served no-cache; each versioned pmtiles can still cache).
            ver = hashlib.sha256(out.read_bytes()).hexdigest()[:8]
            variants.append({
                "id": spec["id"],
                "label_es": spec["label_es"],
                "label_en": spec["label_en"],
                "url": f"dem/dem_{spec['id']}.pmtiles?v={ver}",
            })

    # bbox corners (TL, TR, BR, BL) — kept for the viewer's "frame the relief" fit.
    coordinates = [
        [min_lon, max_lat], [max_lon, max_lat], [max_lon, min_lat], [min_lon, min_lat],
    ]
    meta = {
        "coordinates": coordinates,
        "width": width,
        "height": height,
        "default": "original",
        "variants": variants,
    }
    Paths.dem_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


@dg.asset(
    group_name="manifest",
    description="Bake self-hosted DEM relief raster PMTiles from real elevation (one per theme).",
)
def dem_relief(context: AssetExecutionContext) -> dg.MaterializeResult:
    meta = build_dem_relief()
    total = sum((Paths.dem / f"dem_{v['id']}.pmtiles").stat().st_size for v in meta["variants"])
    return dg.MaterializeResult(
        metadata={
            "variants": dg.MetadataValue.json([v["id"] for v in meta["variants"]]),
            "resolution": f"{meta['width']}x{meta['height']}",
            "total_bytes": total,
        }
    )
