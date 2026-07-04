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

The PDF pages come out in duplex print order — BACK first, then front, per
sheet (sheet 1 back, sheet 1 front, ...): hand-fed stock prints the matte back
side first, then the glossy front lands on the untouched coated side. Print at
100% scale, flip on long edge.

Run from pipeline/:
    .venv/bin/python scripts/build_deck_proof.py                     # sample: cards 1-4 (all before midday)
    .venv/bin/python scripts/build_deck_proof.py --cards all         # the 8 keyframe cards
    .venv/bin/python scripts/build_deck_proof.py --cards 1,5,dusk    # numbers and/or labels
    .venv/bin/python scripts/build_deck_proof.py --paper glossy --back-paper matte

FULL DECK (the real print run): --deck N samples N cards around the eased cycle
(the flip-book gradations) and STREAMS them into duplex sheet PDFs — screen
master always, plus the stock-corrected PDF when --paper/--back-paper are set.
The lunar month walks the backs (one whole month per ~28 cards, whole months
per deck so the wrap is seamless); back-ink warmth follows the front's light.
    .venv/bin/python scripts/build_deck_proof.py --deck 112 --format fat --paper glossy --back-paper matte
"""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("bcb", HERE / "build_card_back.py")
bcb = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(bcb)
blc = bcb.blc                     # the one shared build_light_cards instance (format lives here)

# back-line temperature anchors (0 = coolest night ink, 1 = warmest day sepia),
# one per CYCLE keyframe, tracking the FRONT's light so each back quietly
# matches its card; interpolated between keyframes for a sampled deck
WARMTH_ANCHORS = [0.02, 0.05, 0.60, 0.55, 0.60, 0.85, 0.95, 0.12]


def warmth_at(u, ease=True):
    """Back-line warmth at cycle position u (in keyframe units, wraps), eased
    the same way cycle_frames eases the specs so back and front stay in step."""
    m = len(blc.CYCLE)
    seg = int(u) % m
    t = u - int(u)
    if ease:
        t = blc._ease(t)
    return blc._lerp(WARMTH_ANCHORS[seg], WARMTH_ANCHORS[(seg + 1) % m], t)


def lunar_phase(i, n):
    """The back's moon for card i (0-based) of an n-card deck: one step per
    card, one lunar month per ~28 cards, rounded to WHOLE months around the
    deck so the wrap is seamless. Returns (label, illum, wax)."""
    months = max(1, round(n / 28))
    m = (i * months / float(n)) % 1.0
    illum = 1.0 - abs(1.0 - 2.0 * m)
    wax = m < 0.5
    name = ("new" if illum < 0.06 else "crescent" if illum < 0.38 else
            "quarter" if illum < 0.62 else "gibbous" if illum < 0.94 else "full")
    if name not in ("new", "full"):
        name = ("waxing " if wax else "waning ") + name
    return name, illum, wax


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


def sheet_pages(items, sheet_no, cols=2, rows=2, page_mm=(210.0, 297.0), bare=False):
    """ONE physical sheet (up to cols*rows cards) -> [(name, back_page),
    (name, front_page)] — back FIRST, so a hand-fed duplex run prints the matte
    side before the glossy side. The back page mirrors COLUMNS (long-edge flip),
    images stay upright; rows stay put. items = [(num, label, front, back)].
    bare = full-bleed onto card stock: no header, labels or crop marks (the page
    IS the card — nothing to cut)."""
    pw, ph = blc._px(page_mm[0]), blc._px(page_mm[1])
    gx = (pw - cols * blc.TRIM_W) // (cols + 1)
    gy = (ph - rows * blc.TRIM_H) // (rows + 1)
    f, fh = blc._font(20), blc._font(26)
    pages = []
    for side in ("back", "front"):        # matte back first — hand-fed duplex
        page = Image.new("RGB", (pw, ph), (255, 255, 255))
        d = ImageDraw.Draw(page)
        if not bare:
            d.text((gx, gy // 2 - 16),
                   f"cali deck — sheet {sheet_no} · {side}s · print 100% · duplex: flip on LONG edge",
                   fill=(120, 120, 120), font=fh)
        for j, (num, lab, front, back) in enumerate(items):
            r, c = divmod(j, cols)
            if side == "back":
                c = cols - 1 - c                           # what the long-edge flip undoes
            x, y = gx + c * (blc.TRIM_W + gx), gy + r * (blc.TRIM_H + gy)
            page.paste(front if side == "front" else back, (x, y))
            if not bare:
                blc._crop_marks(d, x, y, blc.TRIM_W, blc.TRIM_H)
                d.text((x, y - 26), f"{num} · {lab}" if side == "front" else f"{num} · back",
                       fill=(140, 140, 140), font=f)
        pages.append((f"s{sheet_no}_{side}", page))
    return pages


def duplex_pages(items, cols=2, rows=2, page_mm=(210.0, 297.0), bare=False):
    """All sheets in memory (fine for a handful of cards — the proof path)."""
    per = cols * rows
    pages = []
    for p0 in range(0, len(items), per):
        pages += sheet_pages(items[p0:p0 + per], p0 // per + 1, cols, rows, page_mm, bare)
    return pages


def page_layout(args):
    """(cols, rows, page_mm, bare) for --page: 'a4' = 2x2 cards on A4 with crop
    marks; 'card' = ONE full-bleed card per page, page size = the format's trim
    (print borderless straight onto card stock — nothing to cut)."""
    if args.page == "card":
        return 1, 1, blc.CARD_MM, True
    return 2, 2, (210.0, 297.0), False


def _merge_pdfs(parts, out):
    """Concatenate per-sheet PDFs into one. PIL's own incremental append
    (save(..., append=True)) corrupts its trailer chain after a few appends
    ('trailer loop found'), so every sheet saves as its own 2-page PDF and
    poppler joins them losslessly (ghostscript as fallback)."""
    if shutil.which("pdfunite"):
        subprocess.run(["pdfunite", *map(str, parts), str(out)], check=True)
    elif shutil.which("gs"):
        subprocess.run(["gs", "-dBATCH", "-dNOPAUSE", "-q", "-sDEVICE=pdfwrite",
                        f"-sOutputFile={out}", *map(str, parts)], check=True)
    else:
        raise RuntimeError("need pdfunite (poppler-utils) or ghostscript to join the sheet PDFs")


def bake_deck(n, args):
    """The FULL deck: n cards sampled around the eased cycle, streamed into
    printable duplex sheet PDF(s) — each sheet saves as a small 2-page PDF and
    the parts merge once at the end, so memory stays flat (~one sheet) instead
    of ~5GB for 25 sheets of pages.

    Always writes the `screen` (master) PDF; when --paper/--back-paper name a
    stock, a second corrected PDF bakes in the same pass — print that one, and
    compare against the screen master when chasing colour."""
    fmt_sfx = ("" if args.format == "tall" else f"_{args.format}") + \
              ("_card" if args.page == "card" else "")
    cols, rows, page_mm, bare = page_layout(args)
    variants = [("", "screen", "screen")]
    if (args.paper, args.back_paper) != ("screen", "screen"):
        p_sfx = ("" if args.paper == "screen" else f"_{args.paper}") + \
                ("" if args.back_paper == "screen" else f"_b{args.back_paper}")
        variants.append((p_sfx, args.paper, args.back_paper))
    pdfs = {sfx: blc.OUT / f"deck_print{fmt_sfx}{sfx}_n{n}.pdf" for sfx, _, _ in variants}

    elev, ext = blc.load_elev()
    win, px_m, streets_px, water_px = blc.prep_scene()
    specs = blc.cycle_frames(n, ease=True)
    dump = blc.OUT / f"deck_light{fmt_sfx}_n{n}" if args.dump_cards else None
    if dump:
        dump.mkdir(exist_ok=True)

    per = cols * rows                                      # 2x2 per A4, or 1 per card page
    n_sheets = (n + per - 1) // per
    print(f"deck: {n} cards -> {n_sheets} duplex sheets; PDFs: "
          + ", ".join(p.name for p in pdfs.values()))
    with tempfile.TemporaryDirectory(prefix="cali_deck_") as tmp:
        tmp = Path(tmp)
        for s0 in range(0, n, per):
            sheet_no = s0 // per + 1
            items = {sfx: [] for sfx, _, _ in variants}
            for i in range(s0, min(s0 + per, n)):
                spec = specs[i]
                u = i / n * len(blc.CYCLE)
                tone = bcb.ink_tone(warmth_at(u)) if args.tone == "ink" else bcb.TONES[args.tone]
                ph_lab, illum, wax = lunar_phase(i, n)
                front = blc.render_card(win, px_m, streets_px, water_px, spec)   # screen master
                back = bcb.stamp_number(
                    bcb.back_moon(blc.TRIM_W, blc.TRIM_H, tone, elev, ext,
                                  **bcb.RIDGE_LAYERED, illum=illum, wax=wax), tone, i + 1)
                if dump:
                    front.save(dump / f"card_{i + 1:03d}_{spec['label']}.png")
                for sfx, pf, pb in variants:
                    items[sfx].append((i + 1, spec["label"],
                                       blc.apply_paper(front, pf), blc.apply_paper(back, pb)))
            for vi, (sfx, _, _) in enumerate(variants):
                pages = [page for _, page in
                         sheet_pages(items[sfx], sheet_no, cols, rows, page_mm, bare)]
                pages[0].save(tmp / f"v{vi}_s{sheet_no:03d}.pdf", "PDF",
                              resolution=blc.DPI, save_all=True, append_images=pages[1:])
            print(f"  sheet {sheet_no}/{n_sheets} (cards {s0 + 1}-{min(s0 + per, n)}) done")
        for vi, (sfx, _, _) in enumerate(variants):
            _merge_pdfs(sorted(tmp.glob(f"v{vi}_s*.pdf")), pdfs[sfx])
    for p in pdfs.values():
        print(f"-> {p.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", default="pre-midday",
                    help="'pre-midday' (default), 'all', or e.g. '1-3,dusk'")
    ap.add_argument("--deck", type=int, default=0, metavar="N",
                    help="bake the FULL deck instead: N cards sampled around the "
                         "eased cycle, streamed to printable duplex sheet PDFs")
    ap.add_argument("--dump-cards", action="store_true",
                    help="(with --deck) also save each front as a PNG")
    ap.add_argument("--format", choices=list(blc.FORMATS), default="tarot")
    ap.add_argument("--page", choices=("a4", "card"), default="a4",
                    help="a4 = 2x2 cards per sheet with crop marks; card = one "
                         "full-bleed card per page at the format's trim size "
                         "(print borderless straight onto card stock)")
    ap.add_argument("--tone", choices=list(bcb.TONES), default="ink",
                    help="back tone (ink = the matte/handwritten side)")
    ap.add_argument("--paper", choices=list(blc.PAPER), default="screen",
                    help="output correction for the FRONT (glossy side of the stock)")
    ap.add_argument("--back-paper", choices=list(blc.PAPER), default="screen",
                    help="output correction for the BACK (matte side of the stock)")
    args = ap.parse_args()
    blc.use_format(args.format)
    blc.OUT.mkdir(parents=True, exist_ok=True)
    if args.deck:
        bake_deck(args.deck, args)
        return
    nums = parse_cards(args.cards)
    sfx = ("" if args.format == "tall" else f"_{args.format}") + \
          ("_card" if args.page == "card" else "") + \
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
        t = (bcb.ink_tone(warmth_at(n - 1.0)) if args.tone == "ink"
             else bcb.TONES[args.tone])                    # ink backs track the front's warmth
        phase_lab, illum, wax = bcb.PHASES[(n - 1) % len(bcb.PHASES)]
        print(f"  card {n} · front {spec['label']} · back {phase_lab} ...")
        front = blc.render_card(win, px_m, streets_px, water_px, spec, paper=args.paper)
        back = bcb.back_moon(blc.TRIM_W, blc.TRIM_H, t, elev, ext,
                             **bcb.RIDGE_LAYERED, illum=illum, wax=wax)
        back = blc.apply_paper(bcb.stamp_number(back, t, n), args.back_paper)
        items.append((n, spec["label"], front, back))

    cols, rows, page_mm, bare = page_layout(args)
    pages = duplex_pages(items, cols, rows, page_mm, bare)
    pdf = blc.OUT / f"proof_duplex{sfx}.pdf"
    pages[0][1].save(pdf, "PDF", resolution=blc.DPI, save_all=True,
                     append_images=[p for _, p in pages[1:]])
    for name, pg in pages:
        pg.save(blc.OUT / f"proof_duplex{sfx}_{name}.png")
    print(f"-> {pdf.name} + {len(pages)} page PNGs (duplex print order)")


if __name__ == "__main__":
    main()
