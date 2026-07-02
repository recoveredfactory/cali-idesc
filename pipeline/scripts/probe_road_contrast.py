"""Probe: how legible is the street grid, EVERYWHERE around the light cycle?

The road washout keeps coming back (dawn once, then dusk): the street grey
drifts to the same lightness as the lit valley floor and the grid dissolves —
often BETWEEN keyframes, where nobody was looking. This measures it instead of
eyeballing it:

  * renders N interpolated frames (ease=False -> uniform coverage; with N a
    multiple of 8 every N/8th frame IS a keyframe) at a medium working res,
    each twice: WITH streets and WITHOUT (ink=0 — same light, same water)
  * per tier, over the street-core pixels, in OKLab lightness L:
      - dL_under = L(drawn line) - L(ground beneath it, from the no-street render)
      - dL_adj   = L(drawn line) - L(adjacent ground ring, in the full render)
    signed: positive = line lighter than ground (night glow), negative = darker
  * the ground's own mottling (std of L in the ring) — the NOISE FLOOR the line
    has to beat: |dL| at or below the mottling means the grid drowns in terrain
  * downtown "grey mass" spill: mean |RGB shift| over NON-road pixels in the
    dense centro box — how much the halo/casing blurs leak onto the ground

Outputs (next to the cards): road_contrast_chart.png (curves + noise band +
the L-crossing view), road_contrast_strip.png (downtown crops around the
cycle), road_contrast.json (all numbers), and a printed keyframe table.

Run from pipeline/:  .venv/bin/python scripts/probe_road_contrast.py
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
blc.use_format("tarot")

N = 48                       # frames around the loop (6 per segment; keyframes at i%6==0)
TARGET_H = 1100              # working res (contrast is a value question, not a res question)
DOWNTOWN = (-76.545, -76.490, 3.475, 3.420)   # W,E,N,S — the dense centro grid
TIERS = ("local", "collector", "arterial")


def okL(rgb_u8):
    """Vectorised OKLab lightness of an HxWx3 uint8 image, in [0,1]."""
    a = rgb_u8.astype(np.float32) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    r, g, b = lin[..., 0], lin[..., 1], lin[..., 2]
    l = np.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m = np.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = np.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s


def rast_lines(lines, width, shape):
    im = Image.new("L", (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(im)
    for pts in lines:
        if len(pts) >= 2:
            d.line(pts, fill=255, width=width, joint="curve")
    return np.asarray(im) > 0


def rast_water(water_px, shape, queb_w):
    im = Image.new("L", (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(im)
    for poly in water_px["humedales"] + water_px["rios"]:
        if len(poly) >= 3:
            d.polygon(poly, fill=255)
    for ln in water_px["quebradas"]:
        if len(ln) >= 2:
            d.line(ln, fill=255, width=queb_w)
    return np.asarray(im) > 0


def dilate(mask, r):
    if r < 1:
        return mask
    im = Image.fromarray(mask.astype(np.uint8) * 255)
    return np.asarray(im.filter(ImageFilter.MaxFilter(2 * r + 1))) > 0


def bbox_px(bbox, shape):
    w, e, n, s = bbox
    cw, ce, cn, cs = blc.WINDOW
    x0, x1, yN, yS = blc.mx(cw), blc.mx(ce), blc.my(cn), blc.my(cs)
    H, W = shape
    c0 = int((blc.mx(w) - x0) / (x1 - x0) * W); c1 = int((blc.mx(e) - x0) / (x1 - x0) * W)
    r0 = int((yN - blc.my(n)) / (yN - yS) * H); r1 = int((yN - blc.my(s)) / (yN - yS) * H)
    return max(0, r0), min(H, r1), max(0, c0), min(W, c1)


# ---- chart drawing (no matplotlib in this venv) ------------------------------
def _panel(d, x0, y0, w, h, title, series, ylim, keyx, keylabels, f, fs,
           hline=None, band=None):
    """One line-plot panel. series = [(name, color, ys)]; band = (lo[], hi[]) grey fill."""
    d.rectangle([x0, y0, x0 + w, y0 + h], outline=(90, 90, 96), width=1)
    d.text((x0, y0 - 24), title, fill=(230, 230, 230), font=f)
    lo, hi = ylim
    def X(i, n): return x0 + i / (n - 1) * w
    def Y(v): return y0 + h - (min(max(v, lo), hi) - lo) / (hi - lo) * h
    for kx, kl in zip(keyx, keylabels):                     # keyframe verticals
        d.line([(X(kx, N), y0), (X(kx, N), y0 + h)], fill=(70, 70, 78), width=1)
        d.text((X(kx, N) + 3, y0 + h - 16), kl, fill=(150, 150, 158), font=fs)
    for gy in np.linspace(lo, hi, 5):                       # horizontal grid + labels
        d.line([(x0, Y(gy)), (x0 + w, Y(gy))], fill=(55, 55, 62), width=1)
        d.text((x0 - 46, Y(gy) - 7), f"{gy:+.2f}" if lo < 0 else f"{gy:.2f}",
               fill=(150, 150, 158), font=fs)
    if band is not None:
        blo, bhi = band
        for i in range(N - 1):
            d.polygon([(X(i, N), Y(blo[i])), (X(i + 1, N), Y(blo[i + 1])),
                       (X(i + 1, N), Y(bhi[i + 1])), (X(i, N), Y(bhi[i]))],
                      fill=(110, 110, 118, 60))
    if hline is not None:
        d.line([(x0, Y(hline)), (x0 + w, Y(hline))], fill=(160, 160, 170), width=2)
    for name, col, ys in series:
        pts = [(X(i, len(ys)), Y(v)) for i, v in enumerate(ys)]
        d.line(pts, fill=col, width=2, joint="curve")
    ly = y0 + 6
    for name, col, ys in series:
        d.line([(x0 + w - 150, ly + 7), (x0 + w - 128, ly + 7)], fill=col, width=3)
        d.text((x0 + w - 122, ly), name, fill=(220, 220, 220), font=fs)
        ly += 18


def main():
    global N
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=N)
    args = ap.parse_args()
    N = args.frames

    blc.OUT.mkdir(parents=True, exist_ok=True)
    win, px_m, streets_px, water_px = blc.prep_scene(target_h=TARGET_H)
    H, W = win.shape
    scale = H / blc.TRIM_H
    print(f"probe grid {W}x{H}  scale {scale:.3f}  frames {N}")

    wid = {t: max(1, round(blc._px(blc.ST_W_MM[t]) * scale)) for t in TIERS}
    core = {t: rast_lines(streets_px[t], wid[t], win.shape) for t in TIERS}
    water = rast_water(water_px, win.shape, max(1, round(blc._px(blc.QUEB_W_MM) * scale)))
    allr = core["local"] | core["collector"] | core["arterial"]
    roads_pad = dilate(allr, 2)                             # core + AA fringe + casing pad
    ring = {t: dilate(core[t], wid[t] + 4) & ~roads_pad & ~water for t in TIERS}
    r0, r1, c0, c1 = bbox_px(DOWNTOWN, win.shape)
    dt_free = ~roads_pad[r0:r1, c0:c1] & ~water[r0:r1, c0:c1]  # downtown non-road ground
    for t in TIERS:
        print(f"  {t}: width {wid[t]}px, {core[t].sum()} core px, {ring[t].sum()} ring px")

    specs = blc.cycle_frames(N, ease=False)
    rows, strip_crops = [], []
    for i, sp in enumerate(specs):
        full = np.asarray(blc.render_card(win, px_m, streets_px, water_px, sp, to_trim=False))
        bare = np.asarray(blc.render_card(win, px_m, streets_px, water_px,
                                          dict(sp, ink=0.0), to_trim=False))
        Lf, Lb = okL(full), okL(bare)
        row = dict(i=i, u=i / N * len(blc.CYCLE), label=sp["label"],
                   street=[round(v, 1) for v in sp["street"]],
                   ink=round(sp["ink"], 3), glow=round(sp["glow"], 3), case=round(sp["case"], 3))
        for t in TIERS:
            row[t] = dict(
                dL_under=float(np.median(Lf[core[t]]) - np.median(Lb[core[t]])),
                dL_adj=float(np.median(Lf[core[t]]) - np.median(Lf[ring[t]])),
                L_line=float(np.median(Lf[core[t]])),
                L_ground=float(np.median(Lb[core[t]])),
                noise=float(np.std(Lb[ring[t]])),
            )
        row["spill"] = float(np.mean(np.abs(full[r0:r1, c0:c1].astype(np.float32)
                                            - bare[r0:r1, c0:c1].astype(np.float32))[dt_free]))
        rows.append(row)
        if i % (N // 12) == 0:
            strip_crops.append((i, sp["label"], Image.fromarray(full[r0:r1, c0:c1])))
        if (i + 1) % 6 == 0 or i == N - 1:
            print(f"  frame {i + 1}/{N}  ({sp['label']})")

    with open(blc.OUT / "road_contrast.json", "w") as fp:
        json.dump(rows, fp, indent=1)

    # ---- keyframe table -------------------------------------------------------
    kf = len(blc.CYCLE)
    print("\nkeyframe    |dL_adj| loc/col/art   vs noise   spill")
    for r in rows:
        if r["i"] % (N // kf) == 0:
            vals = "/".join(f"{abs(r[t]['dL_adj']):.3f}" for t in TIERS)
            print(f"{r['label']:>10}  {vals}   n={r['local']['noise']:.3f}   {r['spill']:.1f}")

    # ---- charts ---------------------------------------------------------------
    CW, PH, PAD = 1500, 240, 70
    img = Image.new("RGB", (CW, 3 * (PH + PAD) + PAD), (28, 28, 32))
    d = ImageDraw.Draw(img, "RGBA")
    f, fs = blc._font(19), blc._font(14)
    keyx = [i for i in range(N) if i % (N // kf) == 0]
    keylabels = [rows[i]["label"] for i in keyx]
    x0, w = 60, CW - 90
    cols = {"local": (140, 170, 255), "collector": (255, 180, 90), "arterial": (255, 100, 110)}

    # 1: signed adjacent contrast per tier, vs the +-noise band (the floor to beat)
    noise = [r["local"]["noise"] for r in rows]
    _panel(d, x0, PAD, w, PH,
           "signed line-vs-adjacent-ground contrast dL_adj (OKLab L) — grey band = ground mottling (drown zone)",
           [(t, cols[t], [r[t]["dL_adj"] for r in rows]) for t in TIERS],
           (-0.20, 0.30), keyx, keylabels, f, fs, hline=0.0,
           band=([-n for n in noise], noise))

    # 2: the crossing view — line L vs ground L (why it washes out where it does)
    _panel(d, x0, 2 * PAD + PH, w, PH,
           "lightness of the drawn ARTERIAL/LOCAL line vs the ground beneath (lines cross = washout)",
           [("art line", cols["arterial"], [r["arterial"]["L_line"] for r in rows]),
            ("art ground", (255, 200, 200), [r["arterial"]["L_ground"] for r in rows]),
            ("loc line", cols["local"], [r["local"]["L_line"] for r in rows]),
            ("loc ground", (200, 210, 255), [r["local"]["L_ground"] for r in rows])],
           (0.0, 1.0), keyx, keylabels, f, fs)

    # 3: downtown grey-mass spill (halo/casing leakage onto non-road ground)
    _panel(d, x0, 3 * PAD + 2 * PH, w, PH,
           "downtown non-road spill: mean |RGB shift| streets-on vs streets-off (grey-mass pressure)",
           [("spill", (170, 230, 170), [r["spill"] for r in rows])],
           (0.0, max(8.0, max(r["spill"] for r in rows) * 1.15), ), keyx, keylabels, f, fs)

    img.save(blc.OUT / "road_contrast_chart.png")
    print(f"-> road_contrast_chart.png")

    # ---- downtown strip ---------------------------------------------------------
    tw = 300
    th = round(tw * (r1 - r0) / (c1 - c0))
    pad, lab = 8, 20
    sheet = Image.new("RGB", (6 * (tw + pad) + pad, 2 * (th + lab + pad) + pad), (28, 28, 32))
    ds = ImageDraw.Draw(sheet)
    for j, (i, label, crop) in enumerate(strip_crops[:12]):
        rr, cc = divmod(j, 6)
        x, y = pad + cc * (tw + pad), pad + rr * (th + lab + pad)
        sheet.paste(crop.resize((tw, th), Image.LANCZOS), (x, y))
        ds.text((x + 2, y + th + 2), f"f{i}  {label}", fill=(210, 210, 210), font=fs)
    sheet.save(blc.OUT / "road_contrast_strip.png")
    print(f"-> road_contrast_strip.png + road_contrast.json")


if __name__ == "__main__":
    main()
