#!/usr/bin/env bash
# Render every PNG in the video kit from its SVG source: the logo, the cards, the overlays,
# the titles and the diagrams. Re-run after replacing brand/logo.svg; nothing else changes.
#
# Usage: video/render.sh
# Needs inkscape or rsvg-convert, and the Noto Sans font for the text.
set -euo pipefail
shopt -s nullglob

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
max_bytes=$((2 * 1024 * 1024))

if command -v inkscape >/dev/null 2>&1; then
  renderer=inkscape
elif command -v rsvg-convert >/dev/null 2>&1; then
  renderer=rsvg
else
  echo "export: neither inkscape nor rsvg-convert is installed (sudo apt install inkscape)" >&2
  exit 1
fi

families="$(fc-list : family 2>/dev/null || true)"
if [[ "$families" != *"Noto Sans"* ]]; then
  echo "export: Noto Sans is not installed (sudo apt install fonts-noto-core); text falls back" >&2
fi

# render <svg> <png> [width]
render() {
  local src="$1" out="$2" width="${3:-}"
  if [[ "$renderer" == inkscape ]]; then
    inkscape "$src" --export-type=png --export-filename="$out" ${width:+--export-width="$width"} >/dev/null 2>&1
  else
    rsvg-convert ${width:+--width="$width" --keep-aspect-ratio} -o "$out" "$src"
  fi
  local size
  size="$(stat -c %s "$out")"
  if ((size > max_bytes)); then
    echo "export: $out is $size bytes, over 2 MB" >&2
    exit 1
  fi
  echo "  ${out#"$here"/} ($((size / 1024)) KB)"
}

echo "rendering with $renderer"
render "$here/brand/logo.svg" "$here/brand/logo.png" 2048
for name in logo-plate card-open card-close card-models corner-overlay corner-overlay-plate; do
  render "$here/brand/$name.svg" "$here/brand/$name.png"
done
for src in "$here"/titles/*.svg "$here"/diagrams/*.svg; do
  render "$src" "${src%.svg}.png"
done
