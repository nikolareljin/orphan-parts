#!/usr/bin/env bash
# A silent animatic of the main video: the cards and titles at the storyboard's
# times, a dark frame with the shot number where a take goes, the captions burned in. A timing
# check, not footage.
#
# Usage: video/animatic.sh        (writes video/out/animatic-main.mp4; run render.sh first)
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$here/out"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
command -v ffmpeg >/dev/null 2>&1 || { echo "animatic: ffmpeg is not installed" >&2; exit 1; }
mkdir -p "$out"

# shot|seconds|picture (a PNG under video/, or "take")|title PNG under titles/ (or -)
shots="S01|6|take|-
S02|6|take|-
S03|5|brand/card-open.png|-
S04|7|take|t01-story-a
S05|8|take|t21-which-device
S06|5|take|t22-label
S07|7|take|t23-device-read
S08|16|take|t24-search-web
S09|8|take|t25-decide
S10|6|take|t08-story-b
S11|9|take|t09-preferences
S12|9|take|t10-propose
S13|8|take|t11-select
S14|7|take|t26-draw
S15|8|take|t12-marketplace
S16|6|take|t13-pack
S17|6|take|t30-value
S18|11|take|t31-sell
S19|6|take|t27-phone
S20|6|brand/card-models.png|-
S21|13|take|t28-gallery
S22|9|brand/card-close.png|-"

: >"$work/list.txt"
while IFS='|' read -r shot secs picture title; do
  inputs=()
  if [[ "$picture" == take ]]; then
    inputs+=(-f lavfi -t "$secs" -i "color=c=0x0e131d:s=1920x1080:r=30")
  else
    inputs+=(-loop 1 -t "$secs" -framerate 30 -i "$here/$picture")
  fi
  filter="[0:v]scale=1920:1080,format=yuv420p[base]"
  last="base"
  if [[ "$title" != - ]]; then
    inputs+=(-loop 1 -t "$secs" -framerate 30 -i "$here/titles/$title.png")
    filter+=";[base][1:v]overlay=0:0:enable='lt(t,4)'[v1]"
    last="v1"
  fi
  if [[ "$picture" == take ]]; then
    filter+=";[$last]drawtext=text='${shot:0:3}  take goes here':font='Noto Sans':fontsize=40:fontcolor=0x94a3b8:x=(w-tw)/2:y=(h-th)/2[v2]"
    last="v2"
  fi
  ffmpeg -nostdin -loglevel error -y "${inputs[@]}" -filter_complex "$filter" -map "[$last]" \
    -t "$secs" -r 30 -c:v libx264 -pix_fmt yuv420p "$work/$shot.mp4"
  echo "file '$work/$shot.mp4'" >>"$work/list.txt"
done <<<"$shots"

ffmpeg -nostdin -loglevel error -y -f concat -safe 0 -i "$work/list.txt" \
  -vf "subtitles=$here/scripts/main.srt" -c:v libx264 -pix_fmt yuv420p "$out/animatic-main.mp4"
echo "animatic: $out/animatic-main.mp4"
