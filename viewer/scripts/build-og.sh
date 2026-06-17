#!/usr/bin/env bash
# Build the Open Graph share card -> static/og.png (1200x630).
#
# Brand lockup on the left (Dancing Script wordmark + tagline + one ES line),
# the dark map silhouette bleeding off the right edge. The screenshot's black
# background blends into the black canvas, so the irregular relief just floats.
# ES-only by design (crawlers don't run our i18n).
#
#   ./scripts/build-og.sh [source-screenshot.png]   # default: scripts/og-source.png
#
# Needs: ImageMagick `convert` + `woff2_decompress` (to render the real brand
# font). Regenerate after swapping og-source.png for a fresh screenshot.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$ROOT/scripts/og-source.png}"
OUT="$ROOT/static/og.png"
WOFF2="$ROOT/static/fonts/dancing-script-600-latin.woff2"
SANS=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
SANSB=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
cp "$WOFF2" "$tmp/ds.woff2"; woff2_decompress "$tmp/ds.woff2"   # -> $tmp/ds.ttf
DS="$tmp/ds.ttf"

# Map scaled to 600px tall; its black bg is invisible on the black canvas.
convert "$SRC" -resize x600 "$tmp/map.png"

# Text layers (transparent, assembled into a left-aligned stack).
convert -background none -fill '#f3edde' -font "$DS"   -pointsize 120 \
        label:'Mapas Cali' "$tmp/word.png"
convert -background none -fill '#7ce3bd' -font "$DS"   -pointsize 56 \
        label:'lo demás es mapa' "$tmp/tag.png"
convert -background none -fill '#aab4bd' -font "$SANS"  -pointsize 29 -size 460x \
        caption:'El catálogo geográfico abierto de Santiago de Cali' "$tmp/desc.png"
convert -background none -fill '#62807a' -font "$SANSB" -pointsize 23 \
        label:'cali.recoveredfactory.net' "$tmp/url.png"

convert -size 8x4  xc:none "$tmp/s1.png"
convert -size 8x40 xc:none "$tmp/s2.png"
convert -size 8x14 xc:none "$tmp/s3.png"
convert -background none -gravity west \
        "$tmp/word.png" "$tmp/s1.png" "$tmp/tag.png" "$tmp/s2.png" \
        "$tmp/desc.png" "$tmp/s3.png" "$tmp/url.png" -append "$tmp/stack.png"

convert -size 1200x630 xc:'#000000' \
        "$tmp/map.png"   -gravity east -geometry +8+0  -composite \
        "$tmp/stack.png" -gravity west -geometry +72+0 -composite \
        "$OUT"

echo "wrote $OUT ($(identify -format '%wx%h, %B bytes' "$OUT"))"
