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
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---- paths -----------------------------------------------------------------
HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
STREETS_LL = DATA / "geojson" / "pot_2014__mov_jerarquizacion_vial.geojson"
DEM_CACHE = DATA / "dem" / "cards_dem_z{z}.npy"          # gitignored (data/)
OUT = Path("/mnt/c/Users/david/OneDrive/Pictures/Screenshots/cali-cards")

# ---- print spec ------------------------------------------------------------
CARD_MM = (70.0, 120.0)          # w x h, portrait
DPI = 600                         # inkjet resolves this; the earlier fuzziness was screen-only
def _px(mm): return round(mm / 25.4 * DPI)
TRIM_W, TRIM_H = _px(CARD_MM[0]), _px(CARD_MM[1])

# ---- geography -------------------------------------------------------------
Z = 14                            # terrarium tile zoom (~9.5 m/px here) — finer for print
FETCH = (-76.72, -76.40, 3.64, 3.16)          # W,E,N,S bbox to fetch (Farallones+city)
# portrait card window (lon/lat) ~ 70x120 aspect; Farallones fill left, city right
WINDOW = (-76.655, -76.445, 3.58, 3.22)       # CW, CE, CN, CS
ZF = 1.45                         # vertical exaggeration (gentler = less intense)
BLUR_SIGMA = 1.0                  # just kill terrarium stair-stepping; keep detail for print
# soften the illumination so it reads subtle, not posterized:
AMB_LIFT = 0.08                   # lift shadows
DIR_GAIN = 0.78                   # pull the direct light back
DESAT = 0.16                      # a touch toward grey

# ---- albedo (deep cloud-forest hypsometric ramp by elevation m -> RGB) ------
# The Farallones really are deep green; muted/forest, not neon-GIS. Extra stops
# keep the gradient smooth (less banding).
RAMP = [(850, 226, 222, 205), (1100, 176, 190, 150), (1500, 120, 150, 108),
        (2000, 82, 120, 84), (2600, 56, 96, 70), (3200, 40, 74, 58),
        (4200, 34, 62, 52)]

# ---- the cycle -------------------------------------------------------------
# Each stop carries its own LIGHT (sun/moon az+alt, ambient + direct as albedo
# multipliers) AND its own STREET character (colour, ink = how present, glow =
# halo strength). The streets trace a full day: silvery-yellow city lights at
# night -> rust at dawn -> teal-grey through the day -> gold at dusk -> back to
# night. Opens on the moon, returns to her.
#   amb/dir  = RGB multipliers of albedo (cool skylight vs warm sun / cool moon)
#   street   = base line colour; ink scales presence; glow adds a blurred halo
CYCLE = [
    dict(label="moon",      az=180, alt=52, amb=(0.14, 0.17, 0.23), dir=(0.36, 0.40, 0.49),
         street=(232, 228, 196), ink=0.50, glow=0.50),   # dim silver, streets a soft silvery-yellow glow
    dict(label="late",      az=250, alt=22, amb=(0.13, 0.16, 0.22), dir=(0.32, 0.36, 0.44),
         street=(232, 228, 196), ink=0.34, glow=0.32),   # dimmer, same shade, less street light
    dict(label="dawn",      az= 82, alt=12, amb=(0.50, 0.48, 0.48), dir=(1.02, 0.84, 0.66),
         street=( 96,  64,  50), ink=1.00, glow=0.00),   # creamy first light, deep rust streets for contrast
    dict(label="morning",   az=118, alt=34, amb=(0.48, 0.50, 0.52), dir=(0.86, 0.86, 0.82),
         street=(120, 140, 136), ink=0.72, glow=0.00),   # lower-contrast day base, rust -> teal-grey
    dict(label="midday",    az=196, alt=50, amb=(0.42, 0.43, 0.44), dir=(0.72, 0.73, 0.72),
         street=( 96, 124, 122), ink=0.72, glow=0.00),   # neutral web-map look, not blown out
    dict(label="afternoon", az=238, alt=34, amb=(0.52, 0.50, 0.52), dir=(1.22, 0.96, 0.66),
         street=( 92, 124, 120), ink=0.90, glow=0.00),   # "right on" — warm low sun, greyed-teal streets
    dict(label="dusk",      az=288, alt=12, amb=(0.30, 0.27, 0.34), dir=(1.32, 0.96, 0.50),
         street=(248, 224, 164), ink=0.60, glow=0.30),   # golden + richer; brighter gold lights, crisper
    dict(label="nightfall", az=300, alt=16, amb=(0.18, 0.19, 0.25), dir=(0.50, 0.52, 0.60),
         street=(208, 200, 178), ink=0.45, glow=0.40),   # dusk fading to night — cooling toward the moon
]

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


def smooth(a, sigma):
    """Gaussian-soften the elevation grid (the web relief is blurrier, and it
    reads better than the z13 DEM's harsh micro-relief)."""
    if sigma <= 0:
        return a
    try:
        from scipy.ndimage import gaussian_filter
        return gaussian_filter(a.astype(np.float32), sigma, mode="reflect")
    except Exception:                        # dependency-free separable fallback
        r = max(1, int(sigma * 3))
        x = np.arange(-r, r + 1)
        k = np.exp(-(x ** 2) / (2 * sigma * sigma)); k /= k.sum()
        b = np.pad(a.astype(np.float32), ((0, 0), (r, r)), mode="reflect")
        b = np.stack([np.convolve(row, k, mode="valid") for row in b])
        b = np.pad(b, ((r, r), (0, 0)), mode="reflect")
        return np.stack([np.convolve(col, k, mode="valid") for col in b.T]).T


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
    amb = np.array(ambient, np.float32)[None, None] + AMB_LIFT
    dr = np.array(direct, np.float32)[None, None] * DIR_GAIN
    rgb = albedo(win) * (amb + dr * hs)
    if DESAT > 0:                                   # ease off the intensity
        rgb = rgb * (1 - DESAT) + rgb.mean(-1, keepdims=True) * DESAT
    return soft_clip(rgb).astype(np.uint8)


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


# tier presence: arterials read strongest, locals faintest (alpha at ink=1)
ST_ALPHA = {"local": 60, "collector": 120, "arterial": 200}
# physical stroke widths (mm on the trim card) — DPI-independent, so raising DPI
# sharpens the streets instead of halving their width
ST_W_MM = {"local": 0.085, "collector": 0.17, "arterial": 0.255}
GLOW_MM = 0.30                    # halo blur radius, in mm on the trim card


def draw_grid(card, streets_px, street_rgb, ink, glow, scale=1.0):
    """Draw the city grid in a single per-phase colour. `ink` scales how present
    the streets are; `glow` (>0) lays a blurred halo underneath so night/dusk
    lights actually glow instead of reading as flat lines."""
    wid = {t: max(1, round(_px(ST_W_MM[t]) * scale)) for t in ST_W_MM}
    base = card.convert("RGBA")

    if glow > 0:                                     # blurred halo, under the crisp lines
        halo = Image.new("RGBA", card.size, (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo)
        for tier in ("local", "collector", "arterial"):
            a = int(ST_ALPHA[tier] * ink * glow * 0.55)
            if a <= 0:
                continue
            w = wid[tier] * 3 + 2
            for pts in streets_px[tier]:
                if len(pts) >= 2:
                    hd.line(pts, fill=(*street_rgb, a), width=w, joint="curve")
        halo = halo.filter(ImageFilter.GaussianBlur(radius=max(2.0, _px(GLOW_MM) * scale)))
        base = Image.alpha_composite(base, halo)

    ov = Image.new("RGBA", card.size, (0, 0, 0, 0))  # crisp lines on top
    d = ImageDraw.Draw(ov)
    for tier in ("local", "collector", "arterial"):
        a = min(255, int(ST_ALPHA[tier] * ink))
        if a <= 0:
            continue
        for pts in streets_px[tier]:
            if len(pts) >= 2:
                d.line(pts, fill=(*street_rgb, a), width=wid[tier], joint="curve")
    return Image.alpha_composite(base, ov).convert("RGB")


def render_card(win, px_m, streets_px, spec, to_trim=True):
    scale = win.shape[0] / TRIM_H            # street widths tuned in trim px
    card = Image.fromarray(
        relief(win, px_m, spec["az"], spec["alt"], spec["amb"], spec["dir"]), "RGB")
    card = draw_grid(card, streets_px, spec["street"], spec["ink"], spec["glow"], scale=scale)
    if to_trim:
        card = card.resize((TRIM_W, TRIM_H), Image.LANCZOS)
    return card


# ---- contact sheet ---------------------------------------------------------
def _font(sz):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", sz)
    except OSError:
        return ImageFont.load_default()


def _crop_marks(d, x, y, w, h, ln=28, gap=8, col=(150, 150, 150)):
    """L-ticks just outside each trim corner, so a card can be cut to size."""
    for cx, cy, sx, sy in ((x, y, -1, -1), (x + w, y, 1, -1),
                           (x, y + h, -1, 1), (x + w, y + h, 1, 1)):
        d.line([(cx + sx * gap, cy), (cx + sx * (gap + ln), cy)], fill=col, width=2)
        d.line([(cx, cy + sy * gap), (cx, cy + sy * (gap + ln))], fill=col, width=2)


def build_proof(cards, page_mm=(210.0, 297.0), cols=2, rows=2):
    """True-size (70x120mm @300dpi) cards on printable pages with crop marks, so
    the colours/darkness can be checked on actual paper. Returns a list of pages."""
    pw, ph = _px(page_mm[0]), _px(page_mm[1])
    per = cols * rows
    gx = (pw - cols * TRIM_W) // (cols + 1)
    gy = (ph - rows * TRIM_H) // (rows + 1)
    f = _font(20)
    pages = []
    for p0 in range(0, len(cards), per):
        page = Image.new("RGB", (pw, ph), (255, 255, 255))
        d = ImageDraw.Draw(page)
        for j, (lab, img) in enumerate(cards[p0:p0 + per]):
            r, c = divmod(j, cols)
            x, y = gx + c * (TRIM_W + gx), gy + r * (TRIM_H + gy)
            page.paste(img, (x, y))
            _crop_marks(d, x, y, TRIM_W, TRIM_H)
            d.text((x, y - 26), lab, fill=(140, 140, 140), font=f)
        pages.append(page)
    return pages


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
    ap.add_argument("--proof", action="store_true", help="true-size proof pages + PDF for a print test")
    ap.add_argument("--z", type=int, default=Z, help="terrarium tile zoom")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"trim {TRIM_W}x{TRIM_H}px  ({CARD_MM[0]}x{CARD_MM[1]}mm @ {DPI}dpi)")
    elev, ext = load_elev(args.z)
    win = smooth(crop_window(elev, ext), BLUR_SIGMA)
    print(f"card window {win.shape}  elev {win.min():.0f}..{win.max():.0f}m")
    cw, ce, cn, cs = WINDOW
    px_m = (mx(ce) - mx(cw)) / win.shape[1] * math.cos(math.radians((cn + cs) / 2))
    streets_px = {k: project(v, win.shape) for k, v in load_streets().items()}

    cards = [(spec["label"], render_card(win, px_m, streets_px, spec)) for spec in CYCLE]
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

    if args.proof:
        pages = build_proof(cards)
        pages[0].save(OUT / "proof_deck.pdf", "PDF", resolution=DPI,
                      save_all=True, append_images=pages[1:])
        for i, pg in enumerate(pages, 1):
            pg.save(OUT / f"proof_p{i}.png")
        print(f"-> proof_deck.pdf + {len(pages)} proof page PNGs (print at 100%)")


if __name__ == "__main__":
    main()
