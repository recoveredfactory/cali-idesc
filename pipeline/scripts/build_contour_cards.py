"""Print-ready contour cards: each card repeats the Cali contour map on a dark
background and lights up ONE elevation line (``cota``), climbing from the valley
floor upward. A gift concept — a deck where a glowing contour walks up the slope.

Renders with Pillow (supersampled for clean AA) straight to exact print pixels;
no matplotlib. Source layers are already in a projected metric CRS (MAGNA-SIRGAS
Colombia zone), so eastings/northings plot directly with equal aspect.

Two framings are produced so we can compare (see ``VARIANTS``):
  * ``city``  — tight on the urban valley + near western foothills (950..1400 m)
  * ``climb`` — zoomed out to hold the full valley->Farallones climb (950..~4070 m)

Usage:
    python scripts/build_contour_cards.py            # contact sheets + samples
    python scripts/build_contour_cards.py --full      # every card, both variants
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---- paths -----------------------------------------------------------------
HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "raw"
CONTOURS = DATA / "pot_2014__bcs_curvas_nivel.fc.json"
STREETS = DATA / "pot_2014__mov_jerarquizacion_vial.fc.json"
OUT = Path("/mnt/c/Users/david/OneDrive/Pictures/Screenshots/cali-cards")

# ---- print spec ------------------------------------------------------------
CARD_MM = (70.0, 120.0)          # w x h, portrait
DPI = 300
BLEED_MM = 0.0                    # proofs at trim; add bleed when finalizing
SS = 3                            # supersample factor for anti-aliasing

def _px(mm: float) -> int:
    return round((mm + 2 * BLEED_MM) / 25.4 * DPI)

TRIM_W, TRIM_H = _px(CARD_MM[0]), _px(CARD_MM[1])
ASPECT = TRIM_W / TRIM_H          # width / height

# ---- palette (near-black, cool slate contours, warm-gold glow) -------------
BG = (10, 12, 16)
STREET_LOCAL = (92, 102, 118)     # faintest
STREET_MAJOR = (112, 124, 143)
CONTOUR = (120, 136, 158)         # faint slate
HL_GLOW = (255, 196, 96)          # warm amber glow
HL_CORE = (255, 240, 206)         # bright warm-white core

A_STREET_LOCAL = 0.09
A_STREET_MAJOR = 0.16
A_CONTOUR = 0.24

MAJOR_TYPES = {
    "Via Arteria Principal", "Via Arteria Secundaria",
    "Via Colectora", "Via Interegional",  # sic: dataset spelling
}

# line widths in TRIM px (scaled by SS at render)
W_STREET = 0.6
W_CONTOUR = 0.7
W_HL_CORE = 1.7
W_HL_GLOW = 6.0

# card elevation sequences
N_CARDS = 46
STEP_M = 10                       # native contour interval


def blend(fg, a, bg=BG):
    return tuple(round(bg[i] * (1 - a) + fg[i] * a) for i in range(3))


# ---- geometry loading ------------------------------------------------------
def _lines(geom):
    t = geom["type"]
    if t == "MultiLineString":
        return geom["coordinates"]
    if t == "LineString":
        return [geom["coordinates"]]
    return []


def load_contours():
    """cota -> list of polylines (each a list of (x, y))."""
    d = json.loads(CONTOURS.read_text())
    by = {}
    for f in d["features"]:
        cota = f["properties"]["cota"]
        if cota < 900:            # drop 0 m / 500 m artifacts below the valley
            continue
        by.setdefault(cota, []).extend(_lines(f["geometry"]))
    return by


def load_streets():
    """(major_polylines, local_polylines) for the urban zone."""
    d = json.loads(STREETS.read_text())
    major, local = [], []
    for f in d["features"]:
        p = f["properties"]
        if p.get("zona") != "URBANA":
            continue
        polys = _lines(f["geometry"])
        (major if p.get("tipo_via") in MAJOR_TYPES else local).extend(polys)
    return major, local


def bounds_of(polys):
    xs = [x for pl in polys for x, y in pl]
    ys = [y for pl in polys for x, y in pl]
    return min(xs), min(ys), max(xs), max(ys)


def union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def fit_aspect(bnds, aspect, pad=0.04):
    x0, y0, x1, y1 = bnds
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if w / h > aspect:            # too wide -> grow height
        h = w / aspect
    else:                         # too tall -> grow width
        w = h * aspect
    w *= 1 + pad
    h *= 1 + pad
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


# ---- rendering -------------------------------------------------------------
class Frame:
    def __init__(self, bnds):
        self.x0, self.y0, self.x1, self.y1 = bnds
        self.W, self.H = TRIM_W * SS, TRIM_H * SS

    def project(self, poly):
        x0, y0, x1, y1 = self.x0, self.y0, self.x1, self.y1
        W, H = self.W, self.H
        out = []
        for x, y in poly:
            px = (x - x0) / (x1 - x0) * W
            py = (1 - (y - y0) / (y1 - y0)) * H   # y-up world -> y-down image
            out.append((px, py))
        return out


def draw_polys(draw, frame, polys, color, width):
    w = max(1, round(width * SS))
    for pl in polys:
        pts = frame.project(pl)
        if len(pts) >= 2:
            draw.line(pts, fill=color, width=w, joint="curve")


def render_base(frame, streets):
    """Dark bg + faint streets + faint contours (shared across a variant's deck)."""
    major, local = streets
    img = Image.new("RGB", (frame.W, frame.H), BG)
    d = ImageDraw.Draw(img)
    draw_polys(d, frame, local, blend(STREET_LOCAL, A_STREET_LOCAL), W_STREET)
    draw_polys(d, frame, major, blend(STREET_MAJOR, A_STREET_MAJOR), W_STREET)
    return img


def render_all_contours(base, frame, contours):
    d = ImageDraw.Draw(base)
    c = blend(CONTOUR, A_CONTOUR)
    for polys in contours.values():
        draw_polys(d, frame, polys, c, W_CONTOUR)
    return base


def highlight_layer(frame, polys):
    """Glow + bright core for one elevation on a transparent RGBA layer."""
    layer = Image.new("RGBA", (frame.W, frame.H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(layer)
    draw_polys(gd, frame, polys, HL_GLOW + (150,), W_HL_GLOW)
    layer = layer.filter(ImageFilter.GaussianBlur(radius=W_HL_GLOW * SS * 0.9))
    cd = ImageDraw.Draw(layer)
    draw_polys(cd, frame, polys, HL_CORE + (255,), W_HL_CORE)
    return layer


def render_card(base_rgba, frame, contours, cota, downscale=True):
    card = base_rgba.copy()
    card.alpha_composite(highlight_layer(frame, contours.get(cota, [])))
    if downscale:
        card = card.convert("RGB").resize((TRIM_W, TRIM_H), Image.LANCZOS)
    return card


# ---- variants --------------------------------------------------------------
def card_levels(contours, mode):
    levels = sorted(contours)
    if mode == "city":
        return [lv for lv in levels if lv >= 950][:N_CARDS]
    # climb: N_CARDS spread from valley floor to the top, snapped to real levels
    lo, hi = 950, max(levels)
    picks = []
    for i in range(N_CARDS):
        target = lo + (hi - lo) * i / (N_CARDS - 1)
        picks.append(min(levels, key=lambda lv: abs(lv - target)))
    # dedupe while preserving order (coarse steps near the sparse top may collide)
    seen, out = set(), []
    for lv in picks:
        if lv not in seen:
            seen.add(lv); out.append(lv)
    return out


def frame_from(cx, cy, span_h):
    """Frame centred at (cx, cy) with a given vertical span (metres)."""
    w = span_h * ASPECT
    return Frame((cx - w / 2, cy - span_h / 2, cx + w / 2, cy + span_h / 2))


def urban_center(streets):
    b = bounds_of(streets[0] + streets[1])
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


# vertical spans (metres) for the zoom ladder — tight -> loose
LADDER_SPANS = [18000, 26000, 34000, 46000]
LADDER_LEVELS = [950, 1150]        # valley loop + a foothill line
# nudge frame north/west of the pure city centroid (metres): +x east, +y north
LADDER_SHIFT = (-1500, 2000)


def zoom_ladder(contours, streets):
    """Filmstrip: columns = zoom tightness, rows = elevation level."""
    cx, cy = urban_center(streets)
    cx += LADDER_SHIFT[0]; cy += LADDER_SHIFT[1]
    grid = {}  # (lv, span) -> thumb
    for span in LADDER_SPANS:
        frame = frame_from(cx, cy, span)
        base_rgba = render_all_contours(
            render_base(frame, streets), frame, contours).convert("RGBA")
        for lv in LADDER_LEVELS:
            card = render_card(base_rgba, frame, contours, lv, downscale=False)
            grid[(lv, span)] = card.convert("RGB").resize(
                (300, round(300 / ASPECT)), Image.LANCZOS)
    cells, labels = [], []
    for lv in LADDER_LEVELS:               # row per level
        for span in LADDER_SPANS:          # column per zoom
            cells.append(grid[(lv, span)])
            labels.append(f"{span // 1000} km tall  •  {lv} m")
    return contact_sheet(cells, labels, cols=len(LADDER_SPANS))


# fixed city framing (locked from the zoom ladder): 26 km tall, centred on the
# 950..1400 m subject band, nudged to balance the composition.
CITY_SPAN = 26000
CITY_SHIFT = (300, -1500)          # +x east, +y north (metres)


def frames(contours, streets):
    major, local = streets
    urban = bounds_of(major + local)
    city_levels = [lv for lv in contours if 950 <= lv <= 1400]
    city_pts = [pl for lv in city_levels for pl in contours[lv]]
    cx0, cy0, cx1, cy1 = bounds_of(city_pts)
    ccx = (cx0 + cx1) / 2 + CITY_SHIFT[0]
    ccy = (cy0 + cy1) / 2 + CITY_SHIFT[1]
    all_pts = [pl for polys in contours.values() for pl in polys]
    climb_src = union(urban, bounds_of(all_pts))
    return {
        "city": frame_from(ccx, ccy, CITY_SPAN),
        "climb": Frame(fit_aspect(climb_src, ASPECT)),
    }


# ---- contact sheet ---------------------------------------------------------
def _font(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def contact_sheet(thumbs, labels, cols=8):
    tw, th = thumbs[0].size
    pad, lab_h = 10, 20
    rows = (len(thumbs) + cols - 1) // cols
    cell_w, cell_h = tw + pad, th + pad + lab_h
    sheet = Image.new("RGB", (cols * cell_w + pad, rows * cell_h + pad), (20, 22, 26))
    d = ImageDraw.Draw(sheet)
    f = _font(13)
    for i, (thumb, lab) in enumerate(zip(thumbs, labels)):
        r, c = divmod(i, cols)
        x, y = pad + c * cell_w, pad + r * cell_h
        sheet.paste(thumb, (x, y))
        d.text((x + 2, y + th + 3), lab, fill=(210, 215, 225), font=f)
    return sheet


# ---- main ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="render every card too")
    ap.add_argument("--ladder", action="store_true", help="only the zoom ladder")
    ap.add_argument("--variant", choices=["city", "climb"], default=None,
                    help="render only one framing (default: both)")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    print(f"trim {TRIM_W}x{TRIM_H}px  ({CARD_MM[0]}x{CARD_MM[1]}mm @ {DPI}dpi)  SS={SS}")
    print("loading geometry...")
    contours = load_contours()
    streets = load_streets()

    if args.ladder:
        zoom_ladder(contours, streets).save(OUT / "zoom_ladder.png")
        print("done -> zoom_ladder.png")
        return

    fr = frames(contours, streets)
    if args.variant:
        fr = {args.variant: fr[args.variant]}

    for mode, frame in fr.items():
        levels = card_levels(contours, mode)
        print(f"[{mode}] {len(levels)} cards  {levels[0]}..{levels[-1]}m  "
              f"frame {int(frame.x1 - frame.x0)}x{int(frame.y1 - frame.y0)}m")
        base = render_all_contours(render_base(frame, streets), frame, contours)
        base_rgba = base.convert("RGBA")

        # thumbnails for a contact sheet (fast: composite at SS, shrink small)
        thumbs, labels = [], []
        for lv in levels:
            card = render_card(base_rgba, frame, contours, lv, downscale=False)
            thumbs.append(card.convert("RGB").resize((160, round(160 / ASPECT)), Image.LANCZOS))
            labels.append(f"{lv} m")
        sheet = contact_sheet(thumbs, labels)
        sheet.save(OUT / f"contact_{mode}.png")
        print(f"  -> contact_{mode}.png  ({sheet.size[0]}x{sheet.size[1]})")

        # a few full-res sample cards across the range
        picks = [levels[0], levels[len(levels) // 2], levels[-1]]
        for lv in picks:
            card = render_card(base_rgba, frame, contours, lv)
            card.save(OUT / f"card_{mode}_{lv:04d}m.png")
        print(f"  -> sample cards: {picks} m")

        if args.full:
            deck = OUT / f"deck_{mode}"
            deck.mkdir(exist_ok=True)
            for i, lv in enumerate(levels, 1):
                render_card(base_rgba, frame, contours, lv).save(
                    deck / f"card_{i:02d}_{lv:04d}m.png")
            print(f"  -> {len(levels)} full cards in deck_{mode}/")

    print("done ->", OUT)


if __name__ == "__main__":
    main()
