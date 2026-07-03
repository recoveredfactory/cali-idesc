"""Two-sided (duplex) proof pages for the light deck: FRONTS + their numbered
moon-phase BACKS, laid out so one double-sided print — flipped on the LONG edge
— lands each card's back squarely behind its front, upright.

The deck pairing: card i's front is cycle keyframe i, its back carries lunar
phase i (PHASES) — the moon walks her month around the deck while the sun walks
the day — plus the card number, tiny, in the lower-right of the matte side.

Page layout matches build_light_cards.build_proof (A4, 2x2 true-size cards,
crop marks); the BACK sheet mirrors the columns, which is exactly what a
long-edge duplex pass undoes. Card k's front and back therefore share the same
physical rectangle, so the crop marks on both sides should coincide — hold a
printed sheet up to the light to check the printer's duplex registration.

The PDF pages come out in duplex print order (sheet 1 front, sheet 1 back, ...):
print it double-sided at 100% scale, flip on long edge.

Run from pipeline/:
    .venv/bin/python scripts/build_deck_proof.py                     # sample: cards 1-4 (all before midday)
    .venv/bin/python scripts/build_deck_proof.py --cards all         # the full deck
    .venv/bin/python scripts/build_deck_proof.py --cards 1,5,dusk    # numbers and/or labels
    .venv/bin/python scripts/build_deck_proof.py --paper glossy --back-paper matte
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("bcb", HERE / "build_card_back.py")
bcb = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(bcb)
blc = bcb.blc                     # the one shared build_light_cards instance (format lives here)

# per-card back-line temperature (0 = coolest night ink, 1 = warmest day sepia),
# tracking the FRONT's light so each back quietly matches its card
WARMTH = dict(moon=0.02, late=0.05, dawn=0.60, morning=0.55, midday=0.60,
              afternoon=0.85, dusk=0.95, nightfall=0.12)


def parse_cards(s):
    """'pre-midday' | 'all' | comma list of 1-based numbers, ranges, labels."""
    labs = [k["label"] for k in blc.CYCLE]
    s = s.strip().lower()
    if s == "all":
        return list(range(1, len(labs) + 1))
    if s in ("pre-midday", "sample"):
        s = f"1-{labs.index('midday')}"           # everything before midday
    out = []
    for tok in s.split(","):
        tok = tok.strip()
        if tok in labs:
            out.append(labs.index(tok) + 1)
        elif "-" in tok:
            a, b = tok.split("-", 1)
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(tok))
    return out


def duplex_pages(items, cols=2, rows=2, page_mm=(210.0, 297.0)):
    """items = [(num, label, front_img, back_img)] -> [(name, page), ...] in
    duplex print order. The back sheet mirrors COLUMNS (long-edge flip), images
    stay upright; rows stay put."""
    pw, ph = blc._px(page_mm[0]), blc._px(page_mm[1])
    per = cols * rows
    gx = (pw - cols * blc.TRIM_W) // (cols + 1)
    gy = (ph - rows * blc.TRIM_H) // (rows + 1)
    f, fh = blc._font(20), blc._font(26)
    pages = []
    for p0 in range(0, len(items), per):
        sheet_no = p0 // per + 1
        for side in ("front", "back"):
            page = Image.new("RGB", (pw, ph), (255, 255, 255))
            d = ImageDraw.Draw(page)
            d.text((gx, gy // 2 - 16),
                   f"cali deck proof — sheet {sheet_no} · {side}s · print 100% · duplex: flip on LONG edge",
                   fill=(120, 120, 120), font=fh)
            for j, (num, lab, front, back) in enumerate(items[p0:p0 + per]):
                r, c = divmod(j, cols)
                if side == "back":
                    c = cols - 1 - c                       # what the long-edge flip undoes
                x, y = gx + c * (blc.TRIM_W + gx), gy + r * (blc.TRIM_H + gy)
                page.paste(front if side == "front" else back, (x, y))
                blc._crop_marks(d, x, y, blc.TRIM_W, blc.TRIM_H)
                d.text((x, y - 26), f"{num} · {lab}" if side == "front" else f"{num} · back",
                       fill=(140, 140, 140), font=f)
            pages.append((f"s{sheet_no}_{side}", page))
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", default="pre-midday",
                    help="'pre-midday' (default), 'all', or e.g. '1-3,dusk'")
    ap.add_argument("--format", choices=list(blc.FORMATS), default="tarot")
    ap.add_argument("--tone", choices=list(bcb.TONES), default="ink",
                    help="back tone (ink = the matte/handwritten side)")
    ap.add_argument("--paper", choices=list(blc.PAPER), default="screen",
                    help="output correction for the FRONT (glossy side of the stock)")
    ap.add_argument("--back-paper", choices=list(blc.PAPER), default="screen",
                    help="output correction for the BACK (matte side of the stock)")
    args = ap.parse_args()
    blc.use_format(args.format)
    nums = parse_cards(args.cards)
    sfx = ("" if args.format == "tall" else f"_{args.format}") + \
          ("" if args.paper == "screen" else f"_{args.paper}") + \
          ("" if args.back_paper == "screen" else f"_b{args.back_paper}")

    blc.OUT.mkdir(parents=True, exist_ok=True)
    print(f"duplex proof: cards {nums}  format={args.format}  tone={args.tone}  "
          f"paper={args.paper}/{args.back_paper}")
    elev, ext = blc.load_elev()                            # backs read the raw DEM mosaic
    win, px_m, streets_px, water_px = blc.prep_scene()

    items = []
    for n in nums:
        spec = blc.CYCLE[n - 1]
        t = (bcb.ink_tone(WARMTH[spec["label"]]) if args.tone == "ink"
             else bcb.TONES[args.tone])                    # ink backs track the front's warmth
        phase_lab, illum, wax = bcb.PHASES[(n - 1) % len(bcb.PHASES)]
        print(f"  card {n} · front {spec['label']} · back {phase_lab} ...")
        front = blc.render_card(win, px_m, streets_px, water_px, spec, paper=args.paper)
        back = bcb.back_moon(blc.TRIM_W, blc.TRIM_H, t, elev, ext,
                             **bcb.RIDGE_LAYERED, illum=illum, wax=wax)
        back = blc.apply_paper(bcb.stamp_number(back, t, n), args.back_paper)
        items.append((n, spec["label"], front, back))

    pages = duplex_pages(items)
    pdf = blc.OUT / f"proof_duplex{sfx}.pdf"
    pages[0][1].save(pdf, "PDF", resolution=blc.DPI, save_all=True,
                     append_images=[p for _, p in pages[1:]])
    for name, pg in pages:
        pg.save(blc.OUT / f"proof_duplex{sfx}_{name}.png")
    print(f"-> {pdf.name} + {len(pages)} page PNGs (duplex print order)")


if __name__ == "__main__":
    main()
