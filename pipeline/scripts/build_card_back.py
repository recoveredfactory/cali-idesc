"""Card BACKS for the light-cards deck — the shared reverse every card carries.

The deck's front is a rich, high-res terrain image (my language: precise, digital).
The back leans the other way on purpose — toward line art, illustrated, esoteric
(her language) — but drawn from the SAME real Farallones data, so it's line art
that could only come from this map. Handwritten lettering goes on top (matte side).

Concepts (see the comparison sheet cmp_backs.png):
  A  moon-over-ridge   the Farallones skyline (DEM silhouette) under a fine moon,
                       open field below to write in
  B  contour-field     the real curvas de nivel (pot_2014__bcs_curvas_nivel),
                       faint, filling the mountains; the valley stays open
  C  contour-zoom      the same contours zoomed into an abstract, swirling patch
                       of ridgeline — esoteric organic line art
  D  joy-division      stacked E-W elevation profiles of a rugged patch, the
                       Unknown-Pleasures ridgeline stack, straight from the DEM

Each renders in two tones: `ink` (dark line on warm cream — takes any pen) and
`night` (pale line on deep ink — a white/gold gel pen, matches the night deck).

Run from pipeline/:
    .venv/bin/python scripts/build_card_back.py            # comparison sheet
    .venv/bin/python scripts/build_card_back.py --full     # + full-res PNGs
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("blc", HERE / "build_light_cards.py")
blc = importlib.util.module_from_spec(spec); spec.loader.exec_module(blc)
blc.use_format("tarot")                                   # the chosen deck size

DATA = HERE.parent / "data"
CURVAS = DATA / "geojson" / "pot_2014__bcs_curvas_nivel.geojson"   # real contour lines (cota m)

# abstract, rugged patches of the Farallones for the zoomed concepts:
# high relief, dense contours, no city grid — reads as pure landform.
ZOOM = (-76.700, -76.560, 3.470, 3.300)                   # C: dense swirling contours
ZOOM_JOY = (-76.660, -76.545, 3.455, 3.300)               # D: transects that cross ridges
WELL = (0.50, 0.62, 0.34, 0.26)                           # writing panel: cx,cy,rx,ry (frac of W,H)

# moon-over-ridge (concept A) geometry, as fractions of W/H:
MOON = (0.70, 0.175, 0.115)                               # cx, cy, radius — held FIXED
RIDGE_BASE = 0.68                                         # horizon line, lowered = more open sky
RIDGE_AMP = 0.20                                          # silhouette height

# two tonal families
TONES = {
    "ink":   dict(bg=(237, 232, 221), line=(58, 52, 46), faint=(120, 110, 100), moon=(70, 62, 54)),
    "night": dict(bg=(12, 14, 21),    line=(228, 224, 210), faint=(120, 130, 150), moon=(232, 230, 214)),
}


# ---- projection (explicit bbox, so the zoomed concepts get their own window) --
def project_ll(lines, bbox, W, H):
    w, e, n, s = bbox
    x0, x1, yN, yS = blc.mx(w), blc.mx(e), blc.my(n), blc.my(s)
    return [[((blc.mx(lo) - x0) / (x1 - x0) * W, (yN - blc.my(la)) / (yN - yS) * H)
             for lo, la in ln] for ln in lines]


def crop_bbox(elev, ext, bbox):
    x0, x1, yN, yS = ext
    H, W = elev.shape
    w, e, n, s = bbox
    c0 = max(0, int((blc.mx(w) - x0) / (x1 - x0) * W)); c1 = min(W, int((blc.mx(e) - x0) / (x1 - x0) * W))
    r0 = max(0, int((yN - blc.my(n)) / (yN - yS) * H)); r1 = min(H, int((yN - blc.my(s)) / (yN - yS) * H))
    return elev[r0:r1, c0:c1]


# ---- contour lines (real curvas de nivel) ----------------------------------
_CONTOURS = None
def load_contours():
    """[(cota_m, [(lon,lat),...]), ...] — parsed once (the file is ~140MB)."""
    global _CONTOURS
    if _CONTOURS is None:
        d = json.load(open(CURVAS))
        out = []
        for f in d["features"]:
            g = f.get("geometry")
            if not g:
                continue
            cota = f["properties"].get("cota", 0)
            if g["type"] == "LineString":
                out.append((cota, g["coordinates"]))
            elif g["type"] == "MultiLineString":
                out += [(cota, ln) for ln in g["coordinates"]]
        _CONTOURS = out
    return _CONTOURS


def _in(bbox, ln):
    w, e, n, s = bbox
    return any(w <= lo <= e and s <= la <= n for lo, la in ln)


# ---- concept renderers (each returns an RGB card at W x H) -----------------
def _blur1d(a, r):
    if r < 1:
        return a
    k = np.ones(2 * r + 1) / (2 * r + 1)
    return np.convolve(np.pad(a, r, mode="edge"), k, mode="valid")


def back_moon(W, H, t, elev, ext, base=None, amp=None):
    """A — Farallones skyline under a fine full moon; the moon is FIXED and the ridge
    can drop (base -> 1.0) to open up sky to write/draw in."""
    base = (RIDGE_BASE if base is None else base) * H
    amp = (RIDGE_AMP if amp is None else amp) * H
    img = Image.new("RGB", (W, H), t["bg"]); d = ImageDraw.Draw(img, "RGBA")
    crop = crop_bbox(elev, ext, blc.WINDOW)
    sky = crop.max(axis=0)                                 # per-column silhouette of the highest land
    sky = _blur1d(sky, max(2, crop.shape[1] // 120))
    xs = np.linspace(0, W, len(sky))
    lo, hi = sky.min(), sky.max()
    ys = base - (sky - lo) / (hi - lo + 1e-6) * amp
    pts = list(zip(xs, ys))
    d.polygon([(0, H), *pts, (W, H)], fill=(*t["line"], 16))   # barely-there fill under the ridge
    d.line(pts, fill=(*t["line"], 235), width=max(2, W // 340), joint="curve")
    # full moon in the open sky, upper area away from the high (left) ridge
    mcx, mcy, mr = MOON
    r, cx, cy = W * mr, W * mcx, H * mcy
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*t["moon"], 235), width=max(2, W // 380))
    d.ellipse([cx - r * 0.86, cy - r * 0.86, cx + r * 0.86, cy + r * 0.86],
              outline=(*t["moon"], 70), width=max(1, W // 700))   # faint inner ring
    return img


def moon_study(elev, ext, out):
    """Ink moon-over-ridge at a few horizon heights (moon fixed) so the exact ridge
    drop can be chosen by eye."""
    bases = [0.52, 0.60, 0.68, 0.76]
    th_h = 1200; th_w = round(th_h * blc.TRIM_W / blc.TRIM_H)
    pad = 16; f = blc._font(22)
    W = len(bases) * (th_w + pad) + pad; Ht = th_h + 2 * pad + 34
    s = Image.new("RGB", (W, Ht), (30, 30, 34)); d = ImageDraw.Draw(s)
    for i, b in enumerate(bases):
        im = back_moon(th_w, th_h, TONES["ink"], elev, ext, base=b)
        x0 = pad + i * (th_w + pad); s.paste(im, (x0, pad))
        d.text((x0 + 4, pad + th_h + 5), f"ridge base {b:.2f}", fill=(215, 215, 215), font=f)
    s.save(out); print("->", out)


def _fade_well(layer, well):
    """Fade an RGBA line layer's alpha to 0 inside an elliptical panel (with a soft
    feathered edge), so handwriting has an open field while the art frames it."""
    W, H = layer.size
    cx, cy, rx, ry = well[0] * W, well[1] * H, well[2] * W, well[3] * H
    a = np.asarray(layer).astype(np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    dd = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    m = np.clip((dd - 0.70) / 0.55, 0.0, 1.0)             # clear inside 0.70r, full art by 1.25r
    a[..., 3] *= m
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def back_contour_field(W, H, t, bbox=None, index_every=200, minor_a=48, index_a=120, well=None):
    """B/C — real curvas de nivel; index contours a touch heavier. bbox None = the
    deck window (mountains contoured, valley open); a tight bbox = the zoom. `well`
    fades an open writing panel into the line art."""
    bbox = bbox or blc.WINDOW
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    lines = [(c, ln) for c, ln in load_contours() if _in(bbox, ln)]
    proj = project_ll([ln for _, ln in lines], bbox, W, H)
    lw = max(1, W // 520)
    for (cota, _), pts in zip(lines, proj):
        if len(pts) < 2:
            continue
        idx = (cota % index_every == 0)
        d.line(pts, fill=(*t["line"], index_a if idx else minor_a),
               width=lw + (1 if idx else 0), joint="curve")
    if well:
        layer = _fade_well(layer, well)
    return Image.alpha_composite(Image.new("RGBA", (W, H), (*t["bg"], 255)), layer).convert("RGB")


def back_joy(W, H, t, elev, ext, n_lines=46, overlap=3.6):
    """D — stacked E-W elevation profiles of the rugged zoom; nearer ridges occlude
    farther ones (the Unknown-Pleasures look), straight from the DEM. Each profile
    rises from its OWN base so ridges read as peaks, not a single tilted slope."""
    img = Image.new("RGB", (W, H), t["bg"]); d = ImageDraw.Draw(img, "RGBA")
    crop = crop_bbox(elev, ext, ZOOM_JOY)
    crop = blc.smooth(crop, 1.0)
    rows = np.linspace(0, crop.shape[0] - 1, n_lines).astype(int)
    cols = np.linspace(0, crop.shape[1] - 1, min(360, crop.shape[1])).astype(int)
    grel = float(crop.max() - crop.min()) * 0.62           # shared vertical scale (exaggerated)
    mx, mtop, mbot = W * 0.11, H * 0.14, H * 0.16
    step = (H - mtop - mbot) / (n_lines - 1)
    amp = step * overlap
    xs = np.linspace(mx, W - mx, len(cols))
    lw = max(1, W // 560)
    for i, r in enumerate(rows):                           # back (top) -> front (bottom)
        prof = crop[r][cols].astype(np.float32)
        prof = prof - prof.min()                           # each ridge from its own valley floor
        base = mtop + i * step
        ys = base - np.clip(prof / (grel + 1e-6), 0, 1.6) * amp
        pts = list(zip(xs, ys))
        d.polygon([(xs[0], base + amp), *pts, (xs[-1], base + amp)], fill=(*t["bg"], 255))  # occlude
        d.line(pts, fill=(*t["line"], 240), width=lw, joint="curve")
    return img


# ---- comparison sheet ------------------------------------------------------
CONCEPTS = [
    ("A moon-over-ridge", "moon"),
    ("B contour-field",   "field"),
    ("C contour-zoom",    "zoom"),
    ("C+ zoom+well",      "zoomwell"),
    ("D joy-division",    "joy"),
]


def render(kind, W, H, tone, elev, ext):
    t = TONES[tone]
    if kind == "moon":
        return back_moon(W, H, t, elev, ext)
    if kind == "field":
        return back_contour_field(W, H, t)
    if kind == "zoom":
        return back_contour_field(W, H, t, bbox=ZOOM, index_every=100, minor_a=70, index_a=150)
    if kind == "zoomwell":
        return back_contour_field(W, H, t, bbox=ZOOM, index_every=100, minor_a=70, index_a=150, well=WELL)
    if kind == "joy":
        return back_joy(W, H, t, elev, ext)
    raise ValueError(kind)


def sheet(elev, ext, out):
    th_h = 620
    th_w = round(th_h * blc.TRIM_W / blc.TRIM_H)
    pad, lab = 16, 26
    cols, rows = len(CONCEPTS), len(TONES)
    W = cols * (th_w + pad) + pad
    Ht = lab + rows * (th_h + lab + pad) + pad
    s = Image.new("RGB", (W, Ht), (30, 30, 34)); d = ImageDraw.Draw(s); f = blc._font(18)
    for ri, tone in enumerate(TONES):
        y0 = lab + ri * (th_h + lab + pad) + pad
        d.text((pad, y0 - 22), f"tone: {tone}", fill=(220, 220, 220), font=f)
        for ci, (name, kind) in enumerate(CONCEPTS):
            x0 = pad + ci * (th_w + pad)
            im = render(kind, th_w, th_h, tone, elev, ext)
            s.paste(im, (x0, y0))
            d.text((x0 + 3, y0 + th_h + 3), name, fill=(210, 210, 210), font=f)
    s.save(out)
    print("->", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="also dump full-res PNGs of every concept/tone")
    ap.add_argument("--moon-study", action="store_true", help="ink moon back at a few ridge heights")
    args = ap.parse_args()
    blc.OUT.mkdir(parents=True, exist_ok=True)
    elev, ext = blc.load_elev()
    if args.moon_study:                                    # no contours needed for concept A
        moon_study(elev, ext, blc.OUT / "cmp_moon_study.png")
        return
    print("contours: loading (~140MB) ...")
    print(f"contours: {len(load_contours())} polylines")
    sheet(elev, ext, blc.OUT / "cmp_backs.png")
    if args.full:
        TW, TH = blc.TRIM_W, blc.TRIM_H
        for name, kind in CONCEPTS:
            for tone in TONES:
                im = render(kind, TW, TH, tone, elev, ext)
                p = blc.OUT / f"back_{kind}_{tone}.png"
                im.save(p); print("->", p)


if __name__ == "__main__":
    main()
