#!/usr/bin/env bash
# Build the Open Graph share card -> static/og.png (1200x630).
#
# The dark map silhouette sits centered; the brand lockup is overlaid in the
# middle over a soft dark glow — "Mapas Cali" in the Dancing Script wordmark,
# a one-line ES description, and the URL in Lato. ES-only by design (crawlers
# don't run our i18n).
#
#   ./scripts/build-og.sh [source-screenshot.png]   # default: scripts/og-source.png
#
# Rendered at 2x and downscaled (Lanczos) so the text stays crisp. Needs
# ImageMagick `convert` + `woff2_decompress`. Regenerate after swapping
# og-source.png for a fresh screenshot.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$ROOT/scripts/og-source.png}"
OUT="$ROOT/static/og.jpg"
WOFF2="$ROOT/static/fonts/dancing-script-600-latin.woff2"
LATO=/usr/share/fonts/truetype/lato/Lato-Regular.ttf
LATO_SEMI=/usr/share/fonts/truetype/lato/Lato-Semibold.ttf

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
cp "$WOFF2" "$tmp/ds.woff2"; woff2_decompress "$tmp/ds.woff2"   # -> $tmp/ds.ttf
DS="$tmp/ds.ttf"

# Everything is built at 2x (canvas 2400x1260) then resized 50% at the end.
# Map: trim the black border so the relief fills more of the frame, fit inside
# a box, center on the black canvas (its black bg blends seamlessly).
convert "$SRC" -fuzz 6% -trim +repage -resize 1760x1180 "$tmp/map.png"

# Brand + copy layers (transparent), assembled into a center-aligned stack.
convert -background none -fill '#f4efe1' -font "$DS" -pointsize 232 \
        label:'Mapas Cali' "$tmp/word.png"
convert -background none -fill '#dde4e8' -font "$LATO" -pointsize 50 -kerning 1 \
        label:'El catálogo geográfico abierto de Santiago de Cali' "$tmp/desc.png"
convert -background none -fill '#86e2c1' -font "$LATO_SEMI" -pointsize 38 -kerning 6 \
        label:'cali.recoveredfactory.net' "$tmp/url.png"

convert -size 8x30 xc:none "$tmp/s1.png"   # word -> desc
convert -size 8x30 xc:none "$tmp/s2.png"   # desc -> url
convert -background none -gravity center \
        "$tmp/word.png" "$tmp/s1.png" "$tmp/desc.png" "$tmp/s2.png" "$tmp/url.png" \
        -append "$tmp/text.png"

# Glow for legibility over the busy map: a soft dark elliptical scrim behind the
# whole lockup, plus a dark halo hugging the letters.
convert -size 2400x1260 xc:none -fill 'rgba(0,0,0,0.74)' \
        -draw 'ellipse 1200,630 820,400 0,360' -blur 0x110 "$tmp/scrim.png"
convert "$tmp/text.png" -background black -shadow 95x20+0+0 +repage "$tmp/halo.png"

# Composite at 2x, downscale (Lanczos) for crisp text, and write a high-quality
# JPEG — the photographic relief makes PNG ~1MB; JPEG q90 (no chroma subsampling,
# so the thin colored streets stay sharp) is ~80KB and OG-friendly.
convert -size 2400x1260 xc:'#000000' \
        "$tmp/map.png"   -gravity center -composite \
        "$tmp/scrim.png" -gravity center -composite \
        "$tmp/halo.png"  -gravity center -composite \
        "$tmp/halo.png"  -gravity center -composite \
        "$tmp/text.png"  -gravity center -composite \
        -filter Lanczos -resize 1200x630 \
        -quality 90 -sampling-factor 4:4:4 -strip \
        "$OUT"

echo "wrote $OUT ($(identify -format '%wx%h, %B bytes' "$OUT"))"
