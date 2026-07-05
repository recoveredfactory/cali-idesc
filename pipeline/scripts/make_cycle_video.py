"""The light-cards cycle as a smooth day/night loop: the SAME framed view of the
Farallones + Cali with the light MOVING moon -> late -> dawn -> ... -> nightfall
-> (wrap back to the moon). Every frame is a real render at an interpolated sun/
moon position (see cycle_frames in build_light_cards) — the shadows genuinely
sweep, no cross-fade ghosting — so the same ~100 gradations also become the flip
book's pages.

Run from pipeline/:
    .venv/bin/python scripts/make_cycle_video.py                 # 100-frame preview loop
    .venv/bin/python scripts/make_cycle_video.py --frames 120 --fps 20
    .venv/bin/python scripts/make_cycle_video.py --paper glossy  # match a print stock
    .venv/bin/python scripts/make_cycle_video.py --no-ease       # constant speed (no settle-on-phase)
Writes cali_cycle.mp4 + cali_cycle_strip.png next to the card outputs (needs ffmpeg).
"""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SCRATCH = Path("/tmp/claude-1000/-home-eads-projects-cali-idesc/"
               "ae45de7c-5c13-4380-bffe-8ac9eaa94388/scratchpad/cycle_frames")

VID_H = 1440                       # portrait; width follows the card aspect
PREVIEW_H = 1600                   # DEM working height for a fast preview render


def _load_module():
    spec = importlib.util.spec_from_file_location("blc", HERE / "build_light_cards.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


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


def render_frames(m, n, paper, ease, label, full):
    """Render n real frames around the loop. full -> print-res cards (flip book);
    else a downscaled DEM window for a quick preview. Returns (frames, vid_w)."""
    win, px_m, streets, water = m.prep_scene(target_h=None if full else PREVIEW_H)
    vid_w = round(VID_H * m.TRIM_W / m.TRIM_H) // 2 * 2          # even width, card aspect
    specs = m.cycle_frames(n, ease=ease, smooth_light=True)   # the video's sun never stalls
    frames = []
    for i, spec in enumerate(specs):
        card = m.render_card(win, px_m, streets, water, spec, to_trim=full, paper=paper)
        card = card.resize((vid_w, VID_H), Image.LANCZOS)
        if label:
            card = _label(m, card, spec["label"])
        frames.append(card)
        if (i + 1) % 10 == 0 or i + 1 == n:
            print(f"  frame {i + 1}/{n}")
    return frames, vid_w


def write_frames(frames):
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    for idx, fr in enumerate(frames):
        fr.save(SCRATCH / f"f_{idx:04d}.png")
    return len(frames)


def encode(out_path, fps):
    cmd = ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(SCRATCH / "f_%04d.png"),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
           "-movflags", "+faststart", str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True)


def strip(frames, out_path, cols=12):
    """A single contact strip of evenly-spaced frames, so the gradation is legible
    at a glance without playing the video."""
    n = len(frames)
    picks = [frames[round(i * (n - 1) / (cols - 1))] for i in range(cols)]
    w = 150
    h = round(w * picks[0].size[1] / picks[0].size[0])
    pad = 6
    sheet = Image.new("RGB", (cols * (w + pad) + pad, h + 2 * pad), (24, 24, 28))
    for i, fr in enumerate(picks):
        sheet.paste(fr.resize((w, h), Image.LANCZOS), (pad + i * (w + pad), pad))
    sheet.save(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=100, help="gradations around the loop")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--format", default="tall", help="card aspect: tall / tarot / fat")
    ap.add_argument("--paper", default="screen", help="render correction (screen is truest on a monitor)")
    ap.add_argument("--no-ease", dest="ease", action="store_false", help="constant speed (no settle-on-phase)")
    ap.add_argument("--label", action="store_true", help="overlay the nearest phase name")
    ap.add_argument("--full", action="store_true", help="print-res frames (flip book), slower")
    args = ap.parse_args()

    m = _load_module()
    m.use_format(args.format)
    m.OUT.mkdir(parents=True, exist_ok=True)
    print(f"rendering {args.frames} frames (format={args.format}, paper={args.paper}, "
          f"ease={args.ease}, full={args.full}) ...")
    tag = "" if args.format == "tall" else f"_{args.format}"
    frames, vid_w = render_frames(m, args.frames, args.paper, args.ease, args.label, args.full)
    strip_path = m.OUT / f"cali_cycle_strip{tag}.png"
    strip(frames, strip_path)
    write_frames(frames)
    out = m.OUT / f"cali_cycle{tag}.mp4"
    dur = len(frames) / args.fps
    print(f"{len(frames)} frames @ {vid_w}x{VID_H}, {args.fps}fps ({dur:.1f}s loop) -> encoding ...")
    encode(out, args.fps)
    print(f"-> {out}\n-> {strip_path}")


if __name__ == "__main__":
    main()
