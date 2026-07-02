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
HYD_RIOS = DATA / "geojson" / "pot_2014__bcs_hid_rios.geojson"        # named river polygons (incl. Cauca)
HYD_QUEB = DATA / "geojson" / "pot_2014__bcs_hid_quebradas.geojson"   # streams (thousands; filter by jerarquia)
HYD_HUM = DATA / "geojson" / "pot_2014__bcs_hid_humedales.geojson"    # wetlands / lagoons (polygons)
QUEB_MAIN = {"1"}                                                     # quebrada jerarquia levels to draw (1 = main)
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
    dict(label="moon",      az=180, alt=52, amb=(0.100, 0.130, 0.180), dir=(0.30, 0.34, 0.44),
         street=(232, 228, 196), ink=0.40, glow=0.42, tiers=(0.30, 0.75, 1.0), water=( 66,  92, 124)),   # darker night; mostly big roads
    dict(label="late",      az=250, alt=22, amb=(0.075, 0.095, 0.140), dir=(0.26, 0.30, 0.40),
         street=(232, 228, 196), ink=0.24, glow=0.24, tiers=(0.10, 0.52, 1.0), water=( 48,  68,  98)),   # deeper; small roads nearly gone
    dict(label="dawn",      az= 82, alt=12, amb=(0.500, 0.480, 0.480), dir=(1.02, 0.84, 0.66),
         street=( 96,  64,  50), ink=1.00, glow=0.00, water=(104, 122, 144)),   # creamy first light, deep rust streets
    dict(label="morning",   az=118, alt=34, amb=(0.500, 0.510, 0.470), dir=(0.88, 0.87, 0.80),
         street=(108, 100,  90), ink=0.82, glow=0.00, water=( 92, 138, 156)),   # fresh green day, warm-grey streets
    dict(label="midday",    az=196, alt=50, amb=(0.440, 0.430, 0.400), dir=(0.75, 0.73, 0.69),
         street=( 98,  92,  84), ink=0.82, glow=0.00, water=(104, 156, 176)),   # bright neutral green, warm-grey streets
    dict(label="afternoon", az=238, alt=34, amb=(0.530, 0.500, 0.470), dir=(1.22, 0.96, 0.66),
         street=(122, 112,  98), ink=0.90, glow=0.00, water=( 96, 144, 160)),   # golden-green, warm-grey streets
    dict(label="dusk",      az=288, alt=12, amb=(0.300, 0.270, 0.340), dir=(1.32, 0.96, 0.50),
         street=(248, 224, 164), ink=0.60, glow=0.30, water=(104, 120, 138)),   # golden + richer; cool water contrast
    dict(label="nightfall", az=300, alt=16, amb=(0.180, 0.190, 0.250), dir=(0.50, 0.52, 0.60),
         street=(208, 200, 178), ink=0.45, glow=0.40, tiers=(0.50, 0.90, 1.0), water=( 70,  92, 120)),   # dusk fading toward the moon
]


# ---- interpolating the cycle (smooth gradations) ---------------------------
# The 8 stops above are keyframes. For a moving-light animation (and for the
# flip book, which wants ~100 pages), we interpolate BETWEEN them and re-render
# each in-between properly — so the sun/moon genuinely moves and its shadows
# sweep, instead of cross-fading two fixed renders (which just ghosts).
def _lerp(a, b, t): return a + (b - a) * t
def _lerp_rgb(a, b, t): return tuple(_lerp(x, y, t) for x, y in zip(a, b))
def _lerp_int(a, b, t): return tuple(int(round(_lerp(x, y, t))) for x, y in zip(a, b))
def _lerp_ang(a, b, t):
    """Interpolate an azimuth along the SHORTEST arc (so late->dawn swings the
    short way across the sky, not a full spin)."""
    d = ((b - a + 180.0) % 360.0) - 180.0
    return (a + d * t) % 360.0
def _ease(t): return t * t * (3.0 - 2.0 * t)      # smoothstep: settle onto each phase


def interp_spec(k0, k1, t):
    """Blend two cycle keyframes at t in [0,1]. Light multipliers (amb/dir/tiers)
    stay float; colours that go to PIL (street/water) round to int."""
    d0 = k0.get("tiers", (1.0, 1.0, 1.0)); d1 = k1.get("tiers", (1.0, 1.0, 1.0))
    return dict(
        label=k0["label"] if t < 0.5 else k1["label"],
        az=_lerp_ang(k0["az"], k1["az"], t), alt=_lerp(k0["alt"], k1["alt"], t),
        amb=_lerp_rgb(k0["amb"], k1["amb"], t), dir=_lerp_rgb(k0["dir"], k1["dir"], t),
        street=_lerp_int(k0["street"], k1["street"], t), water=_lerp_int(k0["water"], k1["water"], t),
        ink=_lerp(k0["ink"], k1["ink"], t), glow=_lerp(k0["glow"], k1["glow"], t),
        tiers=_lerp_rgb(d0, d1, t),
    )


def cycle_frames(n, ease=True, cycle=CYCLE):
    """N specs evenly around the loop (seamless: frame n would equal frame 0, so
    nightfall wraps back to the moon). `ease` settles gently onto each named phase;
    off = constant angular speed. Use this for the video AND the flip-book pages."""
    m = len(cycle)
    out = []
    for i in range(n):
        u = (i / n) * m                              # position along the loop, in segments
        seg = int(math.floor(u)) % m
        t = u - math.floor(u)
        out.append(interp_spec(cycle[seg], cycle[(seg + 1) % m], _ease(t) if ease else t))
    return out

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


# ---- water (rivers, streams, lagoons) --------------------------------------
def _exterior_rings(geom):
    t, c = geom["type"], geom["coordinates"]
    if t == "Polygon":
        return [c[0]]
    if t == "MultiPolygon":
        return [poly[0] for poly in c]
    return []


def _lines_of(geom):
    t, c = geom["type"], geom["coordinates"]
    if t == "LineString":
        return [c]
    if t == "MultiLineString":
        return list(c)
    return []


def load_water():
    """Rivers + lagoons as filled polygons; main quebradas (jerarquia 1) as lines."""
    rios, hum, queb = [], [], []
    for f in json.load(open(HYD_RIOS))["features"]:
        if f.get("geometry"):
            rios += _exterior_rings(f["geometry"])
    for f in json.load(open(HYD_HUM))["features"]:
        if f.get("geometry"):
            hum += _exterior_rings(f["geometry"])
    for f in json.load(open(HYD_QUEB))["features"]:
        g = f.get("geometry")
        if g and f["properties"].get("jerarquia") in QUEB_MAIN:
            queb += _lines_of(g)
    return {"rios": rios, "humedales": hum, "quebradas": queb}


# tier presence: arterials read strongest, locals faintest (alpha at ink=1)
ST_ALPHA = {"local": 60, "collector": 120, "arterial": 200}
# physical stroke widths (mm on the trim card) — DPI-independent, so raising DPI
# sharpens the streets instead of halving their width
ST_W_MM = {"local": 0.085, "collector": 0.17, "arterial": 0.255}
GLOW_MM = 0.30                    # halo blur radius, in mm on the trim card


# water stroke widths (mm on the trim card)
RIO_W_MM = 0.30                   # river ribbons (thicken thin river polygons so they read)
QUEB_W_MM = 0.13                  # main streams


def draw_water(card, water_px, water_rgb, scale=1.0):
    """Lay the hydrography under the streets: lagoons + river bodies as filled
    water, main quebradas as thin streams. One per-phase water colour."""
    ov = Image.new("RGBA", card.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    rio_w = max(1, round(_px(RIO_W_MM) * scale))
    queb_w = max(1, round(_px(QUEB_W_MM) * scale))

    for poly in water_px["humedales"]:               # valley lagoons / wetlands
        if len(poly) >= 3:
            d.polygon(poly, fill=(*water_rgb, 140))
    for ln in water_px["quebradas"]:                 # streams off the Farallones
        if len(ln) >= 2:
            d.line(ln, fill=(*water_rgb, 150), width=queb_w, joint="curve")
    for poly in water_px["rios"]:                     # the named rivers (incl. Cauca)
        if len(poly) >= 3:
            d.polygon(poly, fill=(*water_rgb, 195))
            d.line(poly, fill=(*water_rgb, 205), width=rio_w, joint="curve")  # thicken narrow rivers
    return Image.alpha_composite(card.convert("RGBA"), ov).convert("RGB")


def draw_grid(card, streets_px, street_rgb, ink, glow, tiers=(1.0, 1.0, 1.0), scale=1.0):
    """Draw the city grid in a single per-phase colour. `ink` scales how present
    the streets are; `tiers` = (local, collector, arterial) per-tier multipliers so
    small roads can recede at night; `glow` (>0) lays a blurred halo underneath so
    night/dusk lights actually glow instead of reading as flat lines."""
    wid = {t: max(1, round(_px(ST_W_MM[t]) * scale)) for t in ST_W_MM}
    tmul = {"local": tiers[0], "collector": tiers[1], "arterial": tiers[2]}
    base = card.convert("RGBA")

    if glow > 0:                                     # blurred halo, under the crisp lines
        halo = Image.new("RGBA", card.size, (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo)
        for tier in ("local", "collector", "arterial"):
            a = int(ST_ALPHA[tier] * ink * tmul[tier] * glow * 0.55)
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
        a = min(255, int(ST_ALPHA[tier] * ink * tmul[tier]))
        if a <= 0:
            continue
        for pts in streets_px[tier]:
            if len(pts) >= 2:
                d.line(pts, fill=(*street_rgb, a), width=wid[tier], joint="curve")
    return Image.alpha_composite(base, ov).convert("RGB")


# ---- paper profiles --------------------------------------------------------
# A small output correction per print stock, applied to the finished card. The
# master render is "screen"; GLOSSY is punchy (deep Dmax, boosted saturation) so
# we lift the black point a touch to keep shadow detail from plugging, pull the
# highlight back a hair against glare, and ease saturation; MATTE is flat so it
# lifts muddy shadows and adds saturation back.
PAPER = {
    "screen": dict(black=0,  white=255, gamma=1.00, sat=1.00),
    "glossy": dict(black=9,  white=249, gamma=1.05, sat=0.95),
    "matte":  dict(black=20, white=255, gamma=1.10, sat=1.07),
}


def apply_paper(img, name):
    p = PAPER.get(name)
    if p is None or name == "screen":
        return img
    a = np.asarray(img, np.float32) / 255.0
    if p["gamma"] != 1.0:
        a = np.power(a, 1.0 / p["gamma"])                     # lift midtones
    a = p["black"] / 255.0 + a * ((p["white"] - p["black"]) / 255.0)   # levels
    if p["sat"] != 1.0:
        grey = a.mean(-1, keepdims=True)
        a = grey + (a - grey) * p["sat"]
    return Image.fromarray(np.clip(a * 255.0, 0, 255).astype(np.uint8), "RGB")


def prep_scene(z=Z, target_h=None):
    """Load the DEM window + project streets/water once. `target_h` downscales the
    working grid (relief + vector overlays) for a fast preview render; leave None
    for full print resolution. Returns (win, px_m, streets_px, water_px)."""
    elev, ext = load_elev(z)
    win = smooth(crop_window(elev, ext), BLUR_SIGMA)
    if target_h and target_h < win.shape[0]:
        sc = target_h / win.shape[0]
        win = np.asarray(Image.fromarray(win).resize(
            (round(win.shape[1] * sc), target_h), Image.BILINEAR), np.float32)
    cw, ce, cn, cs = WINDOW
    px_m = (mx(ce) - mx(cw)) / win.shape[1] * math.cos(math.radians((cn + cs) / 2))
    streets_px = {k: project(v, win.shape) for k, v in load_streets().items()}
    water_px = {k: project(v, win.shape) for k, v in load_water().items()}
    return win, px_m, streets_px, water_px


def render_card(win, px_m, streets_px, water_px, spec, to_trim=True, paper="screen"):
    scale = win.shape[0] / TRIM_H            # street widths tuned in trim px
    card = Image.fromarray(
        relief(win, px_m, spec["az"], spec["alt"], spec["amb"], spec["dir"]), "RGB")
    card = draw_water(card, water_px, spec["water"], scale=scale)      # water under the streets
    card = draw_grid(card, streets_px, spec["street"], spec["ink"], spec["glow"],
                     tiers=spec.get("tiers", (1.0, 1.0, 1.0)), scale=scale)
    if to_trim:
        card = card.resize((TRIM_W, TRIM_H), Image.LANCZOS)
    return apply_paper(card, paper)


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
    ap.add_argument("--paper", choices=list(PAPER), default="screen",
                    help="output correction for the print stock (glossy/matte/screen)")
    ap.add_argument("--z", type=int, default=Z, help="terrarium tile zoom")
    args = ap.parse_args()
    sfx = "" if args.paper == "screen" else f"_{args.paper}"   # keep paper variants separate

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"trim {TRIM_W}x{TRIM_H}px  ({CARD_MM[0]}x{CARD_MM[1]}mm @ {DPI}dpi)  paper={args.paper}")
    elev, ext = load_elev(args.z)
    win = smooth(crop_window(elev, ext), BLUR_SIGMA)
    print(f"card window {win.shape}  elev {win.min():.0f}..{win.max():.0f}m")
    cw, ce, cn, cs = WINDOW
    px_m = (mx(ce) - mx(cw)) / win.shape[1] * math.cos(math.radians((cn + cs) / 2))
    streets_px = {k: project(v, win.shape) for k, v in load_streets().items()}
    water_px = {k: project(v, win.shape) for k, v in load_water().items()}
    print(f"water: {len(water_px['rios'])} rivers, {len(water_px['quebradas'])} streams, "
          f"{len(water_px['humedales'])} lagoons")

    cards = [(spec["label"], render_card(win, px_m, streets_px, water_px, spec, paper=args.paper))
             for spec in CYCLE]
    contact_sheet(cards).save(OUT / f"cmp_final{sfx}.png")
    print(f"-> cmp_final{sfx}.png ({len(cards)} cards)")

    for lab, img in cards:
        if lab in ("moon", "midday", "dusk"):
            img.save(OUT / f"card_{lab}{sfx}.png")
    print("-> sample cards: moon, midday, dusk")

    if args.full:
        deck = OUT / f"deck_light{sfx}"; deck.mkdir(exist_ok=True)
        for i, (lab, img) in enumerate(cards, 1):
            img.save(deck / f"card_{i:02d}_{lab}.png")
        print(f"-> {len(cards)} full cards in deck_light{sfx}/")

    if args.proof:
        pages = build_proof(cards)
        pages[0].save(OUT / f"proof_deck{sfx}.pdf", "PDF", resolution=DPI,
                      save_all=True, append_images=pages[1:])
        for i, pg in enumerate(pages, 1):
            pg.save(OUT / f"proof_p{i}{sfx}.png")
        print(f"-> proof_deck{sfx}.pdf + {len(pages)} proof page PNGs (print at 100%)")


if __name__ == "__main__":
    main()
