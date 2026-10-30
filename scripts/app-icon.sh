#!/usr/bin/env bash
# app-icon.sh: the app's icon, cut from docs/assets/logo.svg: the Android launcher icons (rendered
# with Inkscape) and the web header's mark.
#
# The adaptive icon (Android 8.0 and newer, what every supported phone shows) is two layers on a
# 108dp canvas of which a launcher shows the middle 72dp or so under its own mask:
#
#   background   a solid color, the middle of the logo's dark gradient (values/ic_launcher_background.xml)
#   foreground   the logo's viewfinder, cropped around its center so the outer ring spans RING_DP
#                of the canvas (inside the 66dp safe zone, so no launcher mask cuts it), on the
#                logo's own gradient bled to the edges, so that no frame or seam shows
#
# The legacy icons (ic_launcher.png, ic_launcher_round.png) are the same composition clipped to a
# rounded square and a circle, with the usual 2dp margin of a 48dp icon. The web header's mark
# (frontend/public/brand.svg) is that rounded square without the margin, kept as SVG; the browser
# tab keeps the whole logo (favicon.svg).
#
#   app-icon.sh [--check]    write the PNGs under android/app/src/main/res/mipmap-*/ and
#                            frontend/public/brand.svg; --check only says whether Inkscape is there
#
# Environment:
#   ROOT       the repository (default: the parent of this script's directory)
#   INKSCAPE   the command (default: inkscape; tests point it at a stand-in)
set -euo pipefail

root="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
fail() { printf 'app-icon: %s\n' "$*" >&2; exit 1; }
say() { printf 'app-icon: %s\n' "$*"; }

case "${1:-}" in
  ""|--check) ;;
  *) printf 'app-icon: usage: app-icon.sh [--check]\n' >&2; exit 2 ;;
esac

logo="$root/docs/assets/logo.svg"
res="$root/android/app/src/main/res"
web="$root/frontend/public"
inkscape="${INKSCAPE:-inkscape}"
[[ -f "$logo" ]] || fail "no logo at $logo"
[[ -d "$res" ]] || fail "no app resources at $res"
[[ -d "$web" ]] || fail "no web assets at $web"
command -v "$inkscape" >/dev/null 2>&1 || fail "inkscape is not installed (apt install inkscape)"
[[ "${1:-}" == "--check" ]] && { say "inkscape $("$inkscape" --version 2>/dev/null | head -1 | cut -d' ' -f2)"; exit 0; }

# The logo's geometry: the viewfinder is centered at (CX, CY) and its outer ring, stroke
# included, reaches RING units from there.
CX=256
CY=240
RING=187
RING_DP=66           # the ring's diameter on the 108dp canvas
CANVAS_DP=108        # the adaptive icon's canvas
VISIBLE_DP=72        # what a launcher shows of it, the legacy icons' content
LEGACY_DP=48         # the legacy icon's canvas
LEGACY_INNER_DP=44   # the legacy icon's shape, 2dp in from each edge

# One number per expression, with awk so the script needs nothing beyond coreutils.
calc() { awk "BEGIN { printf \"%.4f\", $1 }"; }

unit_per_dp="$(calc "2 * $RING / $RING_DP")"      # logo units per dp

# A crop of the logo: a square of side_dp dp around the center, the frame replaced with the
# gradient bled to the edges, optionally clipped to a shape (SVG fragment, in logo units).
crop() {
  local side_dp="$1" clip="${2:-}" side x0 y0 open close
  side="$(calc "$side_dp * $unit_per_dp")"
  x0="$(calc "$CX - $side / 2")"
  y0="$(calc "$CY - $side / 2")"
  open=""; close=""
  if [[ -n "$clip" ]]; then
    open="<clipPath id=\"icon-shape\">$clip</clipPath></defs><g clip-path=\"url(#icon-shape)\">"
    close="</g></svg>"
  fi
  sed -e "s|viewBox=\"0 0 512 512\"|viewBox=\"$x0 $y0 $side $side\"|" \
      -e '/^  <rect$/,/id="rect51" \/>/d' \
      -e "s|</defs>|${open:-</defs>}<rect x=\"$x0\" y=\"$y0\" width=\"$side\" height=\"$side\" fill=\"url(#bgGrad)\" />|" \
      -e "s|</svg>|${close:-</svg>}|" \
      "$logo"
}

render() {  # render <svg> <png> <px>
  "$inkscape" --export-type=png --export-filename="$2" --export-width="$3" --export-height="$3" \
    --export-background-opacity=0 "$1" >/dev/null 2>&1 || fail "inkscape could not render $2"
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

crop "$CANVAS_DP" > "$work/foreground.svg"
inner="$(calc "$VISIBLE_DP * $unit_per_dp")"
ix="$(calc "$CX - $inner / 2")"
iy="$(calc "$CY - $inner / 2")"
legacy_side="$(calc "$VISIBLE_DP * $LEGACY_DP / $LEGACY_INNER_DP")"
crop "$legacy_side" "<rect x=\"$ix\" y=\"$iy\" width=\"$inner\" height=\"$inner\" rx=\"$(calc "$inner / 5")\" />" > "$work/square.svg"
crop "$legacy_side" "<circle cx=\"$CX\" cy=\"$CY\" r=\"$(calc "$inner / 2")\" />" > "$work/round.svg"
crop "$VISIBLE_DP" "<rect x=\"$ix\" y=\"$iy\" width=\"$inner\" height=\"$inner\" rx=\"$(calc "$inner / 5")\" />" > "$web/brand.svg"
say "web: frontend/public/brand.svg"

# density: pixels per dp
for density in mdpi:1 hdpi:1.5 xhdpi:2 xxhdpi:3 xxxhdpi:4; do
  name="${density%%:*}"
  scale="${density##*:}"
  dir="$res/mipmap-$name"
  mkdir -p "$dir"
  render "$work/foreground.svg" "$dir/ic_launcher_foreground.png" "$(calc "$CANVAS_DP * $scale" | cut -d. -f1)"
  render "$work/square.svg" "$dir/ic_launcher.png" "$(calc "$LEGACY_DP * $scale" | cut -d. -f1)"
  render "$work/round.svg" "$dir/ic_launcher_round.png" "$(calc "$LEGACY_DP * $scale" | cut -d. -f1)"
  say "$name: $(calc "$CANVAS_DP * $scale" | cut -d. -f1)px foreground, $(calc "$LEGACY_DP * $scale" | cut -d. -f1)px legacy"
done
say "done: the ring spans ${RING_DP}dp of the ${CANVAS_DP}dp canvas"
