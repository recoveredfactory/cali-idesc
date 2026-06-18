#!/usr/bin/env bash
# Build the Open Graph share card -> static/og.jpg (1200x630).
#
# The dark map silhouette sits centered, floating over a very subtle reversed
# vertical gradient (near-black at the top, a faint cool lift at the bottom).
# The brand lockup is overlaid in the center over a soft dark glow — "Mapas
# Cali" in the Dancing Script wordmark, with a one-line ES description and the
# URL set in URW Gothic. ES-only by design (crawlers don't run our i18n).
#
#   ./scripts/build-og.sh [source-screenshot.png]   # default: scripts/og-source.png
#
# Rendered at 2x and downscaled (Lanczos) for crisp text; a touch of noise is
# added at final size to dither away gradient banding. Output is a high-quality
# JPEG (~90KB) — the photographic relief makes PNG ~1MB. Needs ImageMagick
# `convert` + `woff2_decompress`. Regenerate after swapping og-source.png.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$ROOT/scripts/og-source.png}"
OUT="${OUT:-$ROOT/static/og.jpg}"
WOFF2="$ROOT/static/fonts/dancing-script-600-latin.woff2"
URW=/usr/share/fonts/opentype/urw-base35
SANS="$URW/URWGothic-Book.otf"
SANS_SEMI="$URW/URWGothic-Demi.otf"

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
cp "$WOFF2" "$tmp/ds.woff2"; woff2_decompress "$tmp/ds.woff2"   # -> $tmp/ds.ttf
DS="$tmp/ds.ttf"

# Built at 2x (canvas 2400x1260), downscaled 50% at the end.

# Background: reversed vertical gradient — near-black top, faint cool lift below.
convert -size 2x1260 gradient:'#050608'-'#11161c' -resize 2400x1260\! "$tmp/bg.png"

# Sharp, centered map; knock out the pure-black surround so the relief floats
# over the gradient with no hard rectangle edge.
convert "$SRC" -fuzz 6% -trim +repage -resize 1760x1180 \
        -fuzz 8% -transparent black "$tmp/map.png"

# Brand + copy layers (transparent), assembled into a center-aligned stack.
convert -background none -fill '#f4efe1' -font "$DS" -pointsize 267 \
        label:'Mapas Cali' "$tmp/word.png"
convert -background none -fill '#dde4e8' -font "$SANS" -pointsize 88 -kerning 1 \
        label:'Un catálogo geográfico abierto' "$tmp/desc.png"
convert -background none -fill '#86e2c1' -font "$SANS_SEMI" -pointsize 61 -kerning 6 \
        label:'cali.recoveredfactory.net' "$tmp/url.png"
convert -size 8x42 xc:none "$tmp/s1.png"
convert -size 8x32 xc:none "$tmp/s2.png"
convert -background none -gravity center \
        "$tmp/word.png" "$tmp/s1.png" "$tmp/desc.png" "$tmp/s2.png" "$tmp/url.png" \
        -append "$tmp/text.png"

# Glow for legibility over the map: a soft dark elliptical scrim behind the
# lockup + a halo hugging the letters.
convert -size 2400x1260 xc:none -fill 'rgba(0,0,0,0.5)' \
        -draw 'ellipse 1200,630 880,430 0,360' -blur 0x120 "$tmp/scrim.png"
convert "$tmp/text.png" -background black -shadow 88x22+0+0 +repage "$tmp/halo.png"

convert "$tmp/bg.png" \
        "$tmp/map.png"   -gravity center -composite \
        "$tmp/scrim.png" -gravity center -composite \
        "$tmp/halo.png"  -gravity center -composite \
        "$tmp/text.png"  -gravity center -composite \
        -filter Lanczos -resize 1200x630 \
        -attenuate 0.14 +noise Gaussian \
        -quality 92 -sampling-factor 4:4:4 -strip \
        "$OUT"

echo "wrote $OUT ($(identify -format '%wx%h, %B bytes' "$OUT"))"
