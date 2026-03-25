#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATIC="$ROOT/src/static"

echo "=== Installing D3 sub-modules ==="
cd "$ROOT"
npm install --no-audit --no-fund 2>/dev/null

echo "=== Building custom D3 bundle ==="
npx --yes esbuild "$STATIC/d3-bundle.js" \
  --bundle --minify --format=iife --global-name=d3 \
  --outfile="$STATIC/d3.custom.min.js"

echo "=== Minifying JS ==="
for f in "$STATIC"/{fingerprint,graph,repo-tiles,chat,jd}.js; do
  base="$(basename "$f" .js)"
  npx --yes esbuild "$f" --minify --outfile="$STATIC/${base}.min.js"
done

echo "=== Minifying CSS ==="
npx --yes esbuild "$STATIC/style.css" --minify --outfile="$STATIC/style.min.css"

echo "=== Pre-compressing ==="
for f in "$STATIC"/*.min.js "$STATIC"/*.min.css "$STATIC"/d3.custom.min.js; do
  [ -f "$f" ] || continue
  brotli -Zf "$f" 2>/dev/null || true
  gzip -kf9 "$f" 2>/dev/null || true
done

# WebP conversion (if tools available and SVG exists)
if command -v rsvg-convert &>/dev/null && command -v cwebp &>/dev/null && [ -f "$STATIC/background.svg" ]; then
  if [ ! -f "$STATIC/background.webp" ] || [ "$STATIC/background.svg" -nt "$STATIC/background.webp" ]; then
    echo "=== Converting background.svg → WebP ==="
    rsvg-convert -w 3840 "$STATIC/background.svg" -o /tmp/bg_temp.png
    cwebp -q 80 /tmp/bg_temp.png -o "$STATIC/background.webp"
    brotli -Zf "$STATIC/background.webp" 2>/dev/null || true
    gzip -kf9 "$STATIC/background.webp" 2>/dev/null || true
    rm -f /tmp/bg_temp.png
  fi
fi

echo "=== Build complete ==="
ls -lh "$STATIC"/*.min.* "$STATIC"/d3.custom.min.js 2>/dev/null | awk '{print $5, $NF}'
