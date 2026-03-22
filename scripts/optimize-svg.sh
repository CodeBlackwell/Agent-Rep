#!/usr/bin/env bash
set -euo pipefail

SVG="src/static/background.svg"
ORIGINAL_SIZE=$(stat -c%s "$SVG")

echo "Original: $(numfmt --to=iec "$ORIGINAL_SIZE")"

# SVGO: lossless optimization — shorten coords, inline styles→attrs, collapse groups
# Skip mergePaths (OOM risk on 75K+ path elements)
npx svgo@latest "$SVG" --config="scripts/svgo.config.mjs"

NEW_SIZE=$(stat -c%s "$SVG")
echo "Optimized: $(numfmt --to=iec "$NEW_SIZE")"
echo "Reduction: $(( (ORIGINAL_SIZE - NEW_SIZE) * 100 / ORIGINAL_SIZE ))%"

# Pre-compress for Caddy precompressed serving
echo ""
echo "Pre-compressing..."
brotli -Zf "$SVG"
gzip -kf9 "$SVG"

BR_SIZE=$(stat -c%s "${SVG}.br")
GZ_SIZE=$(stat -c%s "${SVG}.gz")
echo "Brotli:  $(numfmt --to=iec "$BR_SIZE")"
echo "Gzip:    $(numfmt --to=iec "$GZ_SIZE")"
