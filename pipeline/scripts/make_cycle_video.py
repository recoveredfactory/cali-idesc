"""Quick cycle video: the light-cards deck as a looping day/night animation — the
SAME framed view of the Farallones + Cali with the light moving moon -> late ->
dawn -> ... -> nightfall -> (loop back to the moon). Crossfades the 8 rendered
cards with a brief hold on each and a small phase label. Just for previewing.

Run from pipeline/:  .venv/bin/python scripts/make_cycle_video.py
                     .venv/bin/python scripts/make_cycle_video.py --paper glossy
Writes cali_cycle.mp4 next to the card outputs (needs ffmpeg on PATH).
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SCRATCH = Path("/tmp/claude-1000/-home-eads-projects-cali-idesc/"
               "fa56f71f-96ce-43eb-a9eb-80acafb2513c/scratchpad/cycle_frames")

# ---- video knobs -----------------------------------------------------------
VID_H = 1440                       # portrait; width follows the card aspect
FPS = 24
HOLD = 18                          # frames held on each card (~0.75s)
FADE = 18                          # crossfade frames between cards (~0.75s)


def _load_module():
    spec = importlib.util.spec_from_file_location("blc", HERE / "build_light_cards.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def render_cards(m, paper):
    elev, ext = m.load_elev(m.Z)
    win = m.smooth(m.crop_window(elev, ext), m.BLUR_SIGMA)
    cw, ce, cn, cs = m.WINDOW
    px_m = (m.mx(ce) - m.mx(cw)) / win.shape[1] * math.cos(math.radians((cn + cs) / 2))
    streets = {k: m.project(v, win.shape) for k, v in m.load_streets().items()}
    water = {k: m.project(v, win.shape) for k, v in m.load_water().items()}
    vid_w = round(VID_H * m.TRIM_W / m.TRIM_H) // 2 * 2      # even width
    cards = []
    for spec in m.CYCLE:
        card = m.render_card(win, px_m, streets, water, spec, paper=paper)
        card = card.resize((vid_w, VID_H), Image.LANCZOS)
        cards.append((spec["label"], _label(m, card, spec["label"])))
    return cards, vid_w


def _label(m, img, text):
    """Small translucent pill + phase name, bottom-left."""
    img = img.convert("RGB")
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f = m._font(34)
    x0, y0 = 26, img.size[1] - 78
    tb = d.textbbox((x0 + 18, y0 + 12), text, font=f)
    d.rounded_rectangle((x0, y0, tb[2] + 18, tb[3] + 12), radius=16, fill=(12, 14, 20, 150))
    d.text((x0 + 18, y0 + 12), text, fill=(238, 236, 228, 235), font=f)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def write_frames(cards):
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    n = len(cards)
    idx = 0
    for i in range(n):
        cur = cards[i][1]
        nxt = cards[(i + 1) % n][1]              # wrap: nightfall -> moon (seamless loop)
        for _ in range(HOLD):
            cur.save(SCRATCH / f"f_{idx:04d}.png"); idx += 1
        for k in range(1, FADE + 1):
            Image.blend(cur, nxt, k / (FADE + 1)).save(SCRATCH / f"f_{idx:04d}.png"); idx += 1
    return idx


def encode(out_path):
    cmd = ["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(SCRATCH / "f_%04d.png"),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
           "-movflags", "+faststart", str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", default="screen", help="render correction (screen is truest on a monitor)")
    args = ap.parse_args()
    m = _load_module()
    m.OUT.mkdir(parents=True, exist_ok=True)
    print(f"rendering 8 cards (paper={args.paper}) ...")
    cards, vid_w = render_cards(m, args.paper)
    frames = write_frames(cards)
    out = m.OUT / "cali_cycle.mp4"
    print(f"{frames} frames @ {vid_w}x{VID_H}, {FPS}fps ({frames/FPS:.1f}s) -> encoding ...")
    encode(out)
    print(f"-> {out}")


if __name__ == "__main__":
    main()
