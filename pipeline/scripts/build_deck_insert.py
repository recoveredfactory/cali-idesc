"""The deck's INSERT sheet — the story of the Estrategias Lunares in a fine
serif, beside an outlined home where the deck physically rests. Inside the
outline, a ghost of the card back (the layered Farallones ridge under a full
moon, in pale warm grey): lift the deck and the moon appears.

White ground — text, one thin outline and whisper-grey ridge lines only, so it
costs almost no ink. A4 landscape, print at 100%.

Run from pipeline/:
    .venv/bin/python scripts/build_deck_insert.py
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("bcb", HERE / "build_card_back.py")
bcb = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(bcb)
blc = bcb.blc

PAGE_MM = (297.0, 210.0)          # A4 landscape
CARD_FORMAT = "fat"               # the deck being printed — outline matches its trim
CORNER_MM = 5.0                   # outline corner radius (the corner rounder's curve)

WIN_FONTS = Path("/mnt/c/Windows/Fonts")
BODY_FONT, TITLE_FONT = "GARA.TTF", "GARAIT.TTF"          # Garamond + italic

INK = (58, 52, 46)                # the deck's own ink (build_card_back TONES)
FAINT = (150, 142, 132)           # outline + title rule
GHOST = dict(bg=(255, 255, 255),  # the lifted-deck reveal: whisper-grey line art
             line=(176, 168, 156), faint=(210, 204, 196), moon=(170, 162, 150))

TITLE = "Estrategias Lunares"
BODY = """\
En los años setenta, el músico Brian Eno y su amigo, el artista Peter Schmidt, solían quedar bloqueados creativamente y atrapados en un ciclo de desilusión. Así que crearon una baraja de cartas, cada una con un desafío creativo: las Estrategias Oblicuas.

Estas son las Estrategias Lunares, inspiradas en ti. Algunas vienen directamente de las originales, otras de tradiciones místicas y espirituales, y otras de ti.

Son 46 cartas, una por cada año que llevo buscando la luna en esta vida. Tres están en blanco, para que escribamos nuestros propios mensajes juntos.

El frente de cada carta traza el recorrido del sol sobre Cali y los farallones: empieza de noche, cuando la luna brilla, y avanza por el amanecer, el mediodía y, por fin, el anochecer, cuando la luna vuelve a brillar. Por ahora, sin embargo, las cartas solo llegan hasta el mediodía. Cada año iremos agregando más, escribiéndonos nuevos consejos a medida que la tarde se convierte lentamente en crepúsculo."""


def _wrap(d, text, font, max_w):
    """Greedy wrap on measured widths -> list of lines ('' = paragraph break)."""
    lines = []
    for para in text.split("\n\n"):
        words, cur = para.split(), ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if d.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                lines.append(cur); cur = w
        lines.append(cur)
        lines.append("")
    return lines[:-1]


def build():
    blc.use_format(CARD_FORMAT)
    pw, ph = blc._px(PAGE_MM[0]), blc._px(PAGE_MM[1])
    page = Image.new("RGB", (pw, ph), (255, 255, 255))
    d = ImageDraw.Draw(page, "RGBA")

    # ---- the deck's home (right): ghost back under a rounded outline --------
    cw, ch = blc.TRIM_W, blc.TRIM_H
    zone_x = blc._px(PAGE_MM[0] - 132)                     # right zone centre line
    cx = zone_x + (blc._px(132) - cw) // 2
    cy = (ph - ch) // 2
    elev, ext = blc.load_elev()
    ghost = bcb.back_moon(cw, ch, GHOST, elev, ext, **bcb.RIDGE_LAYERED, illum=1.0)
    r = blc._px(CORNER_MM)
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=r, fill=255)
    page.paste(ghost, (cx, cy), mask)
    d.rounded_rectangle([cx, cy, cx + cw - 1, cy + ch - 1], radius=r,
                        outline=FAINT, width=max(2, blc._px(0.35)))

    # ---- the story (left), sized to fit the column --------------------------
    mx = blc._px(24)
    col_w = cx - blc._px(16) - mx                          # text stops shy of the card home
    for body_pt in range(12, 8, -1):                       # largest size that fits the page
        fb = ImageFont.truetype(str(WIN_FONTS / BODY_FONT), round(body_pt / 72 * blc.DPI))
        ft = ImageFont.truetype(str(WIN_FONTS / TITLE_FONT), round(body_pt * 2.4 / 72 * blc.DPI))
        lh = round(fb.size * 1.45)
        lines = _wrap(d, BODY, fb, col_w)
        head = round(ft.size * 1.25) + blc._px(7)          # title + rule + air
        h = sum(lh if ln else round(lh * 0.55) for ln in lines)
        if head + h <= ph - 2 * blc._px(18):
            break
    mtop = max(blc._px(18), (ph - head - h) // 2)          # centre the group on the page
    y0 = mtop + head

    d.text((mx, mtop), TITLE, fill=INK, font=ft)
    ry = mtop + round(ft.size * 1.18)
    d.line([(mx, ry), (mx + blc._px(46), ry)], fill=FAINT, width=max(2, blc._px(0.25)))

    y = y0
    for ln in lines:
        if ln:
            d.text((mx, y), ln, fill=INK, font=fb)
            y += lh
        else:
            y += round(lh * 0.55)

    out = blc.OUT / "deck_insert_fat.pdf"
    page.save(out, "PDF", resolution=blc.DPI)
    page.save(blc.OUT / "deck_insert_fat.png")
    print(f"-> {out.name} (A4 landscape, body {body_pt}pt) + preview PNG")


if __name__ == "__main__":
    build()
