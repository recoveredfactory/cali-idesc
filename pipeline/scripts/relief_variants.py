#!/usr/bin/env python3
"""Bake several real-DEM relief LOOKS for side-by-side comparison.

Same approach as ``relief_realdem_preview.py`` (public AWS terrarium tiles ->
elevation -> gentle WEST hillshade -> hypsometric ramp -> coverage alpha), but:
  * the expensive download + resample is CACHED to /tmp, so re-coloring is instant
  * it bakes a NAMED SET of variants (different ramps / warmth) in one run
  * a `warmth` dial nudges the west-LIT faces toward gold without killing the green

West light is held at the gentle setting David picked (az 295, alt 42, zf 1.6).

Run:  python3 relief_variants.py [out_dir]   (default ./relief_out)
Each variant -> <out_dir>/dem_<name>.png  (4000-wide RGBA, irregular Cali shape)
"""
import math, io, sys, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image

OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("relief_out")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# --- gentle WEST light (locked) ---------------------------------------------
AZ, ALT, ZF, SHADE = 295.0, 42.0, 1.6, 0.7
Z, WIDTH = 12, 4000
WEST, EAST, NORTH, SOUTH = -77.2, -76.0, 4.0, 2.9
CACHE = Path(f"/tmp/cali_relief_elev_{WIDTH}.npy")

# --- variant LOOKS to compare -----------------------------------------------
# ramp: (elev_m, R, G, B) keyed on real metres (valley ~950m -> Farallones ~4000m)
# warmth: 0..1 golden bias applied only to west-LIT faces.
# shade: per-variant west-light strength (more = deeper darks / more form).
#
# Round 3 (David: "too neon; doesn't need HIGHER contrast"). The neon came from the
# hillshade BRIGHTENING lit faces (green * >1 -> lime). Now `shade` is DARKEN-ONLY
# depth: lit faces show the true (deep, muted) ramp colour, shadows just go darker.
# Greens are muted/forest, not lime. Modest contrast.
# Round 6 — house style locked (olive-pale-soft: shade 0.38, fade 150). Drop topo.
# David: slate relief was too dark + dark relief too light -> SWAP the lightness
# ("like what we had before"): slate = LIGHT pale-medium blue on the pale base;
# oscuro = DEEP navy on black. Same hillshade for all (no per-theme relight needed).
#   original (default) = soft pale OLIVE       (bg #f0ebda)
#   slate  = light, BLUER pale-medium blue     (bg #eef2f6)
#   oscuro = deep navy mountains on black      (bg #000)
OLIVE = [(900, 220, 218, 200), (1050, 176, 178, 148), (1500, 132, 146, 110),
         (2200, 96, 120, 88), (3000, 66, 92, 66), (4200, 46, 70, 52)]
SLATE = [(900, 226, 233, 241), (1050, 192, 210, 230), (1500, 156, 184, 216),
         (2200, 120, 156, 202), (3000, 92, 132, 188), (4200, 70, 110, 172)]
# desaturated deep slate (was too blue) — only a hint of cool, stays dark on #000
OSCURO = [(900, 46, 49, 55), (1050, 55, 59, 66), (1500, 68, 73, 82),
          (2200, 85, 92, 102), (3000, 104, 112, 124), (4200, 124, 134, 148)]

VARIANTS = [
    {"name": "original", "ramp": OLIVE,  "warmth": 0.0, "shade": 0.38, "fade": 150},
    {"name": "slate",    "ramp": SLATE,  "warmth": 0.0, "shade": 0.40, "fade": 150},
    {"name": "oscuro",   "ramp": OSCURO, "warmth": 0.0, "shade": 0.50, "fade": 150},
]
GOLD = np.array([34, 12, -26], np.float32)  # +R +G -B additive nudge toward gold

_R = 6378137.0
def mx(lon): return _R * math.radians(lon)
def my(lat): return _R * math.log(math.tan(math.pi/4 + math.radians(lat)/2))
def lon2tx(lon, z): return (lon + 180.0) / 360.0 * (1 << z)
def lat2ty(lat, z):
    s = math.sin(math.radians(lat))
    return (0.5 - math.log((1+s)/(1-s)) / (4*math.pi)) * (1 << z)


def load_elev():
    """Resampled elevation grid (H x WIDTH), cached to disk after first build."""
    if CACHE.exists():
        e = np.load(CACHE)
        print(f"elev cache hit {CACHE} {e.shape}")
        return e
    tx0, tx1 = int(math.floor(lon2tx(WEST, Z))), int(math.floor(lon2tx(EAST, Z)))
    ty0, ty1 = int(math.floor(lat2ty(NORTH, Z))), int(math.floor(lat2ty(SOUTH, Z)))
    nx, ny = tx1 - tx0 + 1, ty1 - ty0 + 1
    print(f"fetching {nx*ny} terrarium tiles z{Z}...")
    mosaic = np.zeros((ny*256, nx*256), np.float32)

    def fetch(tx, ty):
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{tx}/{ty}.png"
        req = urllib.request.Request(url, headers={"User-Agent": "cali-relief/1.0"})
        last = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    a = np.asarray(Image.open(io.BytesIO(r.read())).convert("RGB")).astype(np.float32)
                return tx, ty, a[..., 0]*256 + a[..., 1] + a[..., 2]/256 - 32768
            except Exception as e:  # transient network: back off and retry
                last = e
        raise RuntimeError(f"tile {tx}/{ty} failed after retries: {last}")

    with ThreadPoolExecutor(max_workers=16) as ex:
        for tx, ty, elev in ex.map(lambda t: fetch(*t),
                                   [(x, y) for x in range(tx0, tx1+1) for y in range(ty0, ty1+1)]):
            mosaic[(ty-ty0)*256:(ty-ty0)*256+256, (tx-tx0)*256:(tx-tx0)*256+256] = elev

    def tx2mx(tx, z): return (tx/(1 << z))*2*math.pi*_R - math.pi*_R
    def ty2my(ty, z): return math.pi*_R - (ty/(1 << z))*2*math.pi*_R
    mosX0, mosX1 = tx2mx(tx0, Z), tx2mx(tx1+1, Z)
    mosY0, mosY1 = ty2my(ty0, Z), ty2my(ty1+1, Z)

    H = round(WIDTH * (my(NORTH)-my(SOUTH)) / (mx(EAST)-mx(WEST)))
    ox = np.linspace(mx(WEST), mx(EAST), WIDTH)
    oy = np.linspace(my(NORTH), my(SOUTH), H)
    fx = (ox - mosX0) / (mosX1 - mosX0) * (mosaic.shape[1]-1)
    fy = (mosY0 - oy) / (mosY0 - mosY1) * (mosaic.shape[0]-1)
    ix = np.clip(fx, 0, mosaic.shape[1]-1).astype(int)
    iy = np.clip(fy, 0, mosaic.shape[0]-1).astype(int)
    elev = mosaic[np.ix_(iy, ix)]
    np.save(CACHE, elev)
    print(f"elev built + cached {elev.shape} -> {CACHE}")
    return elev


def coverage_alpha(elev, valley=1015.0, fade=230.0):
    """Alpha keyed on elevation-above-valley so the flat valley/city dissolves to
    transparent (basemap shows through, no bbox rectangle) and the mountains read
    opaque. Smaller `fade` = FASTER gradient into the base layer. A border feather
    guarantees no hard cut where terrain meets the bbox."""
    a = np.clip((elev - valley) / fade, 0, 1) ** 0.85
    H, W = elev.shape
    fr = 0.04                              # feather the outer 4% of each edge
    ex = np.clip(np.minimum(np.arange(W), W - 1 - np.arange(W)) / (fr * W), 0, 1)
    ey = np.clip(np.minimum(np.arange(H), H - 1 - np.arange(H)) / (fr * H), 0, 1)
    edge = np.minimum(ey[:, None], ex[None, :])
    return (a * edge * 255).astype(np.float32)


def hillshade(elev):
    px_m = (mx(EAST)-mx(WEST)) / WIDTH * math.cos(math.radians((NORTH+SOUTH)/2))
    gy, gx = np.gradient(elev * ZF, px_m)
    slope = np.pi/2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gy, gx)
    azr, altr = math.radians(AZ), math.radians(ALT)
    hs = np.sin(altr)*np.sin(slope) + np.cos(altr)*np.cos(slope)*np.cos((azr - math.pi/2) - aspect)
    return np.clip(hs, 0, 1)


def bake(elev, hs, spec):
    ev = np.array([s[0] for s in spec["ramp"]], np.float32)
    tint = np.stack([np.interp(elev, ev, np.array([s[i] for s in spec["ramp"]], np.float32))
                     for i in (1, 2, 3)], -1)
    sh = spec.get("shade", SHADE)
    f = (1 - sh*(1 - hs))[..., None]               # DARKEN-only: lit=true colour, east faces darker
    out = tint * f
    if spec["warmth"] > 0:                          # gold only on lit faces
        lit = np.clip((hs - 0.5) * 2, 0, 1)[..., None]
        out = out + spec["warmth"] * lit * GOLD
    out = np.clip(out, 0, 255)
    alpha = coverage_alpha(elev, spec.get("valley", 1015.0), spec.get("fade", 230.0))
    img = np.dstack([out, alpha]).astype(np.uint8)
    path = OUT_DIR / f"dem_{spec['name']}.png"
    Image.fromarray(img, "RGBA").save(path)
    return path


elev = load_elev()
H = elev.shape[0]
hs = hillshade(elev)
print(f"grid {WIDTH}x{H}  elev {elev.min():.0f}..{elev.max():.0f}m  variants: {len(VARIANTS)}")
for spec in VARIANTS:
    p = bake(elev, hs, spec)
    print(f"  baked {spec['name']:16s} shade={spec.get('shade')} fade={spec.get('fade', 230)} -> {p}")
