#!/usr/bin/env bash
# A silent animatic of the main video: the cards, diagrams and titles at the storyboard's
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
S03|6|brand/card-open.png|-
S04|8|take|t01-story-a
S05|6|take|t02-capture
S06|5|take|t03-read
S07|5|take|t04-measure
S08|13|take|t05-find
S09|8|take|t08-story-b
S10|9|take|t09-preferences
S11|8|take|t10-propose
S12|7|take|t11-select
S13|9|take|t12-marketplace
S14|6|take|t13-pack
S15|5|diagrams/arcade-connections.png|t14-connections
S16|5|diagrams/arcade-placement.png|t15-placement
S17|12|diagrams/arcade-swap.png|t16-swap
S18|11|take|t17-brackets
S19|7|brand/card-models.png|-
S20|9|take|t18-candidates
S21|9|take|t19-eval
S22|10|brand/card-close.png|-"

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
    filter+=";[$last]drawtext=text='$shot  take goes here':font='Noto Sans':fontsize=40:fontcolor=0x94a3b8:x=(w-tw)/2:y=(h-th)/2[v2]"
    last="v2"
  fi
  ffmpeg -nostdin -loglevel error -y "${inputs[@]}" -filter_complex "$filter" -map "[$last]" \
    -t "$secs" -r 30 -c:v libx264 -pix_fmt yuv420p "$work/$shot.mp4"
  echo "file '$work/$shot.mp4'" >>"$work/list.txt"
done <<<"$shots"

ffmpeg -nostdin -loglevel error -y -f concat -safe 0 -i "$work/list.txt" \
  -vf "subtitles=$here/scripts/main.srt" -c:v libx264 -pix_fmt yuv420p "$out/animatic-main.mp4"
echo "animatic: $out/animatic-main.mp4"
