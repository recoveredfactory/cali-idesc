"""Print-ready "light cycle" cards: an Oblique-Strategies-style deck (a personal
gift) where every card is the SAME view of the Farallones + Cali, rendered under
a different light — the sun climbing dawn -> midday -> dusk, then the MOON
carrying the night. Drawn at random; each card stands alone. The cycle opens on
the moon and returns to her.

Why this and not the earlier contour-climb (build_contour_cards.py): a single
highlighted contour in isolation just reads as a squiggle. Here the whole terrain
is the subject and *light* is what changes card to card — which works standalone,
which is what an Oblique-Strategies deck needs.

Render model (organic + illustrated, not a tinted B&W photo):
    out = albedo(elevation) * (ambient_light + direct_light * hillshade)
  * albedo   = green hypsometric ramp (the viewer's DEM look), by real metres
  * hillshade= gradient/slope/aspect vs a moving sun/moon (az, alt)
  * ambient  = cool skylight (shadows keep colour); direct = warm sun / cool moon
A soft highlight rolloff keeps bright valleys from clipping to paper-white.

Data (both LOCAL + gitignored, regenerable via the Dagster pipeline):
  * DEM: AWS terrarium elevation tiles, fetched over the Cali bbox (cached .npy)
  * Streets: data/geojson/pot_2014__mov_jerarquizacion_vial.geojson — already
    reprojected EPSG:6249 -> EPSG:4326, so it projects to the DEM's Web-Mercator
    card window with no CRS math.

Usage:
    uv run python scripts/build_light_cards.py            # contact sheet + samples
    uv run python scripts/build_light_cards.py --full     # every card at print res
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---- paths -----------------------------------------------------------------
HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
STREETS_LL = DATA / "geojson" / "pot_2014__mov_jerarquizacion_vial.geojson"
DEM_CACHE = DATA / "dem" / "cards_dem_z{z}.npy"          # gitignored (data/)
OUT = Path("/mnt/c/Users/david/OneDrive/Pictures/Screenshots/cali-cards")

# ---- print spec ------------------------------------------------------------
CARD_MM = (70.0, 120.0)          # w x h, portrait
DPI = 300
def _px(mm): return round(mm / 25.4 * DPI)
TRIM_W, TRIM_H = _px(CARD_MM[0]), _px(CARD_MM[1])

# ---- geography -------------------------------------------------------------
Z = 13                            # terrarium tile zoom (~19 m/px here)
FETCH = (-76.72, -76.40, 3.64, 3.16)          # W,E,N,S bbox to fetch (Farallones+city)
# portrait card window (lon/lat) ~ 70x120 aspect; Farallones fill left, city right
WINDOW = (-76.655, -76.445, 3.58, 3.22)       # CW, CE, CN, CS
ZF = 1.7                          # vertical exaggeration

# ---- albedo (green hypsometric ramp by elevation m -> RGB) -----------------
RAMP = [(850, 240, 236, 220), (1050, 200, 214, 172), (1500, 142, 184, 120),
        (2200, 88, 152, 96), (3000, 48, 116, 70), (4200, 30, 88, 56)]

# ---- the cycle: (label, azimuth, altitude, ambient_rgb, direct_rgb) --------
# light given as multipliers of albedo. opens on the moon, returns to night.
CYCLE = [
    ("moon",      180, 52, (0.30, 0.37, 0.52), (0.48, 0.58, 0.82)),
    ("late",      250, 24, (0.26, 0.32, 0.46), (0.42, 0.52, 0.80)),
    ("dawn",       82, 12, (0.42, 0.44, 0.56), (1.20, 0.82, 0.54)),
    ("morning",   118, 34, (0.50, 0.52, 0.55), (1.16, 1.00, 0.76)),
    ("midday",    176, 58, (0.56, 0.58, 0.58), (0.92, 0.92, 0.86)),
    ("afternoon", 238, 34, (0.52, 0.50, 0.52), (1.22, 0.96, 0.66)),
    ("dusk",      288, 12, (0.40, 0.36, 0.46), (1.38, 0.72, 0.46)),
    ("nightfall", 312, 18, (0.34, 0.34, 0.48), (0.72, 0.60, 0.86)),
]
NIGHT = {"moon", "late", "nightfall"}

# ---- streets ---------------------------------------------------------------
ST_ARTERIAL = {"Via Arteria Principal", "Via Interegional"}   # sic: dataset spelling
ST_COLLECTOR = {"Via Arteria Secundaria", "Via Colectora"}

# ---- web-mercator helpers --------------------------------------------------
R = 6378137.0
def mx(lon): return R * math.radians(lon)
def my(lat): return R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
def lon2tx(lon, z): return (lon + 180.0) / 360.0 * (1 << z)
def lat2ty(lat, z):
    s = math.sin(math.radians(lat)); return (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * (1 << z)
def tx2mx(tx, z): return (tx / (1 << z)) * 2 * math.pi * R - math.pi * R
def ty2my(ty, z): return math.pi * R - (ty / (1 << z)) * 2 * math.pi * R


# ---- DEM -------------------------------------------------------------------
def load_elev(z=Z):
    cache = Path(str(DEM_CACHE).format(z=z))
    if cache.exists():
        d = np.load(cache, allow_pickle=True).item()
        return d["elev"], d["ext"]
    w, e, n, s = FETCH
    tx0, tx1 = int(math.floor(lon2tx(w, z))), int(math.floor(lon2tx(e, z)))
    ty0, ty1 = int(math.floor(lat2ty(n, z))), int(math.floor(lat2ty(s, z)))
    nx, ny = tx1 - tx0 + 1, ty1 - ty0 + 1
    print(f"fetching {nx}x{ny}={nx*ny} terrarium tiles z{z}...")
    mosaic = np.zeros((ny * 256, nx * 256), np.float32)

    def fetch(tx, ty):
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{tx}/{ty}.png"
        req = urllib.request.Request(url, headers={"User-Agent": "cali-cards/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            a = np.asarray(Image.open(io.BytesIO(r.read())).convert("RGB")).astype(np.float32)
        return tx, ty, a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768

    with ThreadPoolExecutor(max_workers=16) as ex:
        for tx, ty, el in ex.map(lambda t: fetch(*t),
                                 [(x, y) for x in range(tx0, tx1 + 1) for y in range(ty0, ty1 + 1)]):
            mosaic[(ty - ty0) * 256:(ty - ty0) * 256 + 256, (tx - tx0) * 256:(tx - tx0) * 256 + 256] = el
    ext = (tx2mx(tx0, z), tx2mx(tx1 + 1, z), ty2my(ty0, z), ty2my(ty1 + 1, z))  # x0,x1,yN,yS
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, {"elev": mosaic, "ext": ext})
    return mosaic, ext


def crop_window(elev, ext):
    x0, x1, yN, yS = ext
    H, W = elev.shape
    cw, ce, cn, cs = WINDOW
    c0 = int((mx(cw) - x0) / (x1 - x0) * W); c1 = int((mx(ce) - x0) / (x1 - x0) * W)
    r0 = int((yN - my(cn)) / (yN - yS) * H); r1 = int((yN - my(cs)) / (yN - yS) * H)
    return elev[r0:r1, c0:c1]


# ---- rendering -------------------------------------------------------------
def albedo(elev):
    ev = np.array([s[0] for s in RAMP], np.float32)
    return np.stack([np.interp(elev, ev, np.array([s[i] for s in RAMP], np.float32))
                     for i in (1, 2, 3)], -1)


def hillshade(elev, az, alt, px_m):
    gy, gx = np.gradient(elev * ZF, px_m)
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gy, gx)
    azr, altr = math.radians(az), math.radians(alt)
    hs = np.sin(altr) * np.sin(slope) + np.cos(altr) * np.cos(slope) * np.cos((azr - math.pi / 2) - aspect)
    return np.clip(hs, 0, 1)


def soft_clip(v, knee=205.0):
    """Roll highlights off toward 255 instead of hard-clipping to paper-white."""
    v = np.asarray(v, np.float32)
    span = 255.0 - knee
    hi = v > knee
    v = v.copy()
    v[hi] = knee + span * (1.0 - np.exp(-(v[hi] - knee) / span))
    return np.clip(v, 0, 255)


def relief(win, px_m, az, alt, ambient, direct):
    hs = hillshade(win, az, alt, px_m)[..., None]
    illum = np.array(ambient, np.float32)[None, None] + np.array(direct, np.float32)[None, None] * hs
    return soft_clip(albedo(win) * illum).astype(np.uint8)


# ---- streets ---------------------------------------------------------------
def load_streets():
    d = json.load(open(STREETS_LL))
    tiers = {"arterial": [], "collector": [], "local": []}
    for f in d["features"]:
        p = f["properties"]
        if p.get("zona") != "URBANA":
            continue
        t = p.get("tipo_via")
        key = ("arterial" if t in ST_ARTERIAL else
               "collector" if t in ST_COLLECTOR else "local")
        g = f["geometry"]
        if not g:
            continue
        if g["type"] == "MultiLineString":
            tiers[key].extend(g["coordinates"])
        elif g["type"] == "LineString":
            tiers[key].append(g["coordinates"])
    return tiers


def project(lines, shp):
    cw, ce, cn, cs = WINDOW
    x0, x1, yN, yS = mx(cw), mx(ce), my(cn), my(cs)
    H, W = shp
    return [[((mx(lo) - x0) / (x1 - x0) * W, (yN - my(la)) / (yN - yS) * H) for lo, la in ln]
            for ln in lines]


def draw_grid(card, streets_px, night, scale=1.0):
    ov = Image.new("RGBA", card.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    if night:
        cols = {"local": (78, 200, 194, 60), "collector": (110, 216, 208, 110),
                "arterial": (150, 232, 222, 185)}
    else:
        cols = {"local": (34, 150, 146, 72), "collector": (26, 140, 136, 122),
                "arterial": (18, 128, 124, 195)}
    wid = {"local": max(1, round(1 * scale)), "collector": max(1, round(2 * scale)),
           "arterial": max(1, round(3 * scale))}
    for tier in ("local", "collector", "arterial"):
        for pts in streets_px[tier]:
            if len(pts) >= 2:
                d.line(pts, fill=cols[tier], width=wid[tier], joint="curve")
    return Image.alpha_composite(card.convert("RGBA"), ov).convert("RGB")


def render_card(win, px_m, streets_px, spec, to_trim=True):
    lab, az, alt, amb, dr = spec
    scale = win.shape[0] / TRIM_H            # street widths tuned in trim px
    card = Image.fromarray(relief(win, px_m, az, alt, amb, dr), "RGB")
    card = draw_grid(card, streets_px, lab in NIGHT, scale=scale)
    if to_trim:
        card = card.resize((TRIM_W, TRIM_H), Image.LANCZOS)
    return card


# ---- contact sheet ---------------------------------------------------------
def _font(sz):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", sz)
    except OSError:
        return ImageFont.load_default()


def contact_sheet(cards, cols=4, w=340):
    aspect = TRIM_W / TRIM_H
    h = round(w / aspect)
    pad, lab_h = 12, 22
    rows = (len(cards) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + pad) + pad, rows * (h + lab_h + pad) + pad), (232, 230, 224))
    d = ImageDraw.Draw(sheet); f = _font(15)
    for i, (lab, img) in enumerate(cards):
        r, c = divmod(i, cols)
        x, y = pad + c * (w + pad), pad + r * (h + lab_h + pad)
        sheet.paste(img.resize((w, h), Image.LANCZOS), (x, y))
        d.text((x + 3, y + h + 3), f"{i + 1}. {lab}", fill=(50, 48, 54), font=f)
    return sheet


# ---- main ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="render every card at print res")
    ap.add_argument("--z", type=int, default=Z, help="terrarium tile zoom")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"trim {TRIM_W}x{TRIM_H}px  ({CARD_MM[0]}x{CARD_MM[1]}mm @ {DPI}dpi)")
    elev, ext = load_elev(args.z)
    win = crop_window(elev, ext)
    print(f"card window {win.shape}  elev {win.min():.0f}..{win.max():.0f}m")
    cw, ce, cn, cs = WINDOW
    px_m = (mx(ce) - mx(cw)) / win.shape[1] * math.cos(math.radians((cn + cs) / 2))
    streets_px = {k: project(v, win.shape) for k, v in load_streets().items()}

    cards = [(spec[0], render_card(win, px_m, streets_px, spec)) for spec in CYCLE]
    contact_sheet(cards).save(OUT / "cmp_final.png")
    print(f"-> cmp_final.png ({len(cards)} cards)")

    for lab, img in cards:
        if lab in ("moon", "midday", "dusk"):
            img.save(OUT / f"card_{lab}.png")
    print("-> sample cards: moon, midday, dusk")

    if args.full:
        deck = OUT / "deck_light"; deck.mkdir(exist_ok=True)
        for i, (lab, img) in enumerate(cards, 1):
            img.save(deck / f"card_{i:02d}_{lab}.png")
        print(f"-> {len(cards)} full cards in deck_light/")


if __name__ == "__main__":
    main()
