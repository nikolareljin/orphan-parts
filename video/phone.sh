#!/usr/bin/env bash
# The phone scene (S19) on a connected Android phone or a running emulator, for
# video/generate.sh: the app reaches the generator's stack through adb reverse, the access
# code is typed into the Backend tab before the recording starts (the field hides it, and the
# tab is never on camera). The take is two recordings cut together: the Capture tab, then the
# system photo picker already opened on the demo photos' own album (its first page, the phone's
# whole gallery, is never on camera), the two agitator photos, Done, a name, Send, and the
# Captures tab. In fixture mode the take stops at the Captures list: the phone re-encodes the
# photos, so no recorded answer matches its capture. With VIDEO_RECORD=1 (generate.sh --record
# --phone, live) Read it now is tapped too and the take runs until the read is back.
# Afterwards the pushed photos are deleted, the reverse ports removed, the status bar given back
# and the app's data cleared (it stays installed).
#
# Usage: video/phone.sh <out.mp4>
#   VIDEO_PHONE_SERIAL  the device (adb devices); required, nothing else is touched
#   FRONTEND_PORT, DEMO_ACCESS_CODE, VIDEO_RECORD  from generate.sh
# The phone must be unlocked with the screen on (Developer options, Stay awake); a locked
# phone is refused, never unlocked from here. During the take the status bar shows no
# notifications (System UI demo mode) and heads-up notifications are off; both are restored.
set -euo pipefail

out="${1:?usage: video/phone.sh <out.mp4>}"
serial="${VIDEO_PHONE_SERIAL:?set VIDEO_PHONE_SERIAL to the serial adb devices lists}"
port="${FRONTEND_PORT:?FRONTEND_PORT is not set}"
: "${DEMO_ACCESS_CODE:?DEMO_ACCESS_CODE is not set}"
live="${VIDEO_RECORD:-0}"
app=com.orphanparts.lens
album=opl-demo
dir="/sdcard/Pictures/$album"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
photos="$here/../demo/photos"
work="$(mktemp -d)"
a() { adb -s "$serial" "$@"; }

command -v ffmpeg >/dev/null || { echo "phone: ffmpeg is needed to cut the take" >&2; exit 1; }

demo_allowed="" heads_up=""
setting_restore() { # <name> <value read before>
  if [[ -z "$2" || "$2" == null ]]; then a shell settings delete global "$1" >/dev/null 2>&1 || true
  else a shell settings put global "$1" "$2" >/dev/null 2>&1 || true; fi
}
stop_rec() { a shell "pkill -INT screenrecord" >/dev/null 2>&1 || true; }

cleanup() {
  stop_rec
  if [[ -n "$demo_allowed" ]]; then
    a shell am broadcast -a com.android.systemui.demo -e command exit >/dev/null 2>&1 || true
    setting_restore sysui_demo_allowed "$demo_allowed"
  fi
  [[ -z "$heads_up" ]] || setting_restore heads_up_notifications_enabled "$heads_up"
  a shell rm -rf "$dir" /sdcard/opl-take-a.mp4 /sdcard/opl-take-b.mp4 /sdcard/opl-ui.xml >/dev/null 2>&1 || true
  a shell content call --method scan_volume --uri content://media --arg external_primary >/dev/null 2>&1 || true
  a reverse --remove-all >/dev/null 2>&1 || true
  a shell pm clear "$app" >/dev/null 2>&1 || true
  a shell input keyevent 3 >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

a get-state >/dev/null 2>&1 || { echo "phone: $serial is not connected" >&2; exit 1; }
a shell pm path "$app" >/dev/null 2>&1 || { echo "phone: the app ($app) is not installed on $serial" >&2; exit 1; }
if a shell dumpsys window | grep -q 'isKeyguardShowing=true'; then
  echo "phone: $serial is locked; unlock it and turn on Stay awake (it is never unlocked from here)" >&2
  exit 1
fi

# find.py <ui.xml> <want>...: the first want that is on screen, as "x y". A want is
# desc=<prefix> (content description), text=<prefix>, or a bare prefix of either. The tap
# goes to the middle of the smallest clickable node around the match (a field around its
# label, a button around its text), else to the match itself.
cat >"$work/find.py" <<'PY'
import re, sys, xml.etree.ElementTree as ET
try:
    nodes = list(ET.parse(sys.argv[1]).getroot().iter("node"))
except Exception:
    sys.exit(0)
def box(n):
    return tuple(map(int, re.findall(r"\d+", n.get("bounds") or "[0,0][0,0]")))
def hit(n, want):
    kind, _, word = want.partition("=")
    if not _:
        kind, word = "any", want
    text, desc = n.get("text") or "", n.get("content-desc") or ""
    return (kind in ("any", "text") and text.startswith(word)) or (kind in ("any", "desc") and desc.startswith(word))
clickable = [box(n) for n in nodes if n.get("clickable") == "true"]
every = sys.argv[2] == "--all"
for want in sys.argv[3 if every else 2:]:
    for n in nodes:
        if not hit(n, want):
            continue
        x1, y1, x2, y2 = box(n)
        if x2 <= x1 or y2 <= y1:
            continue
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        around = [b for b in clickable if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]]
        if around:
            b = min(around, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
            cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
        print(cx, cy)
        if not every:
            sys.exit(0)
PY

dump() {
  a shell uiautomator dump /sdcard/opl-ui.xml >/dev/null 2>&1 || true
  a shell cat /sdcard/opl-ui.xml >"$work/ui.xml" 2>/dev/null || true
}
# at <want>...: where the first of them is on screen now, empty if none is; seen: the same in
# the last dump (no new one, which takes the phone two seconds)
at() { dump; seen "$@"; }
seen() { python3 "$work/find.py" "$work/ui.xml" "$@"; }
# press <x y>: a tap where an earlier dump found something
press() {
  [[ -n "$1" ]] || { echo "phone: $2 was not found" >&2; return 1; }
  # shellcheck disable=SC2086
  a shell input tap $1
  sleep "${3:-0.8}"
}

# tap <want>...: the first of them on screen, waiting up to ten seconds for one to show
tap() {
  local xy
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    xy="$(at "$@")"
    if [[ -n "$xy" ]]; then
      # shellcheck disable=SC2086
      a shell input tap $xy
      sleep 0.8
      return 0
    fi
    sleep 1
  done
  echo "phone: nothing on screen reads \"$*\"" >&2
  return 1
}

# seek <want>...: like tap, scrolling the page up to find one below the fold
seek() {
  local xy
  for _ in 1 2 3 4 5 6; do
    xy="$(at "$@")"
    if [[ -n "$xy" ]]; then
      # shellcheck disable=SC2086
      a shell input tap $xy
      sleep 0.8
      return 0
    fi
    a shell input swipe 540 1700 540 1000 350
    sleep 0.8
  done
  echo "phone: nothing on screen or below reads \"$*\"" >&2
  return 1
}

# wait_for <seconds> <want>...: until one of them is on screen
wait_for() {
  local secs="$1"; shift
  local end=$((SECONDS + secs))
  while ((SECONDS < end)); do
    [[ -z "$(at "$@")" ]] || return 0
    sleep 1
  done
  echo "phone: \"$*\" did not show in ${secs}s" >&2
  return 1
}

type_text() { a shell input text "$(printf '%s' "$1" | sed 's/ /%s/g')"; sleep 0.5; }
keyboard_off() { a shell input keyevent 4 >/dev/null 2>&1 || true; sleep 0.8; }

# rec <name> <seconds>: screenrecord in the background into /sdcard/<name>.mp4
rec_pid=""
rec() {
  a shell screenrecord --bit-rate 8000000 --time-limit "$2" "/sdcard/$1.mp4" &
  rec_pid=$!
  sleep 1
}
rec_stop() {
  sleep "${1:-0}"
  stop_rec
  wait "$rec_pid" 2>/dev/null || true
  rec_pid=""
  sleep 1
}

# the stack, as localhost on the phone
a reverse "tcp:$port" "tcp:$port" >/dev/null
# two photos of the agitator in the gallery, in an album of their own
a shell mkdir -p "$dir"
for p in agitator-head.jpg agitator-coupling.jpg; do a push "$photos/$p" "$dir/$p" >/dev/null; done
a shell content call --method scan_volume --uri content://media --arg external_primary >/dev/null 2>&1 || true

# a status bar without notifications for the take, heads-up notifications off
heads_up="$(a shell settings get global heads_up_notifications_enabled | tr -d '\r')"
a shell settings put global heads_up_notifications_enabled 0 >/dev/null
demo_allowed="$(a shell settings get global sysui_demo_allowed | tr -d '\r')"
a shell settings put global sysui_demo_allowed 1 >/dev/null
a shell am broadcast -a com.android.systemui.demo -e command enter >/dev/null
a shell am broadcast -a com.android.systemui.demo -e command notifications -e visible false >/dev/null
a shell cmd statusbar collapse >/dev/null 2>&1 || true

# the backend, off camera: the address and the code typed into the Backend tab, then saved
# and the stack answering before anything is recorded
a shell pm clear "$app" >/dev/null
a shell am start -W -n "$app/.MainActivity" >/dev/null
sleep 2
tap "text=Backend"
tap "text=Backend URL"
type_text "http://localhost:$port"
keyboard_off
tap "text=Access code"
a shell input text "$DEMO_ACCESS_CODE"
keyboard_off
tap "text=Save"
wait_for 30 "text=localhost:$port · recorded" "text=localhost:$port · live" || { echo "phone: the app does not reach the stack" >&2; exit 1; }
tap "text=Capture"
wait_for 10 "text=Photos from the gallery"
# the tabs stay where they are; the Captures tab is tapped on camera from here
captures_tab="$(seen "text=Captures")"

# on camera, first part: the Capture tab
rec opl-take-a 10
rec_stop 1.5

# off camera: the picker, opened on the demo photos' album, the two photos found
tap "text=Photos from the gallery"
tap "desc=Collections"
seek "text=From this device"
seek "text=$album"
wait_for 10 "desc=Photo taken" "desc=Photo"
mapfile -t thumbs < <(seen --all "desc=Photo taken")
[[ ${#thumbs[@]} -ge 2 ]] || mapfile -t thumbs < <(seen --all "desc=Photo")
[[ ${#thumbs[@]} -ge 2 ]] || { echo "phone: the $album album does not show two photos" >&2; exit 1; }

# on camera, second part: the two photos, Done, a name, Send, the Captures tab; as few dumps
# as can be, each one is two seconds of a still screen
rec opl-take-b 180
press "${thumbs[0]}" photo 0.6
press "${thumbs[1]}" photo 0.6
tap "text=Done" "text=Add" "desc=Done"
sleep 1.2
a shell input swipe 540 1700 540 1000 350
sleep 0.6
seek "text=Name, if you know it"
send="$(seen "text=Send")"
type_text "Frappe maker agitator"
keyboard_off
press "$send" Send 2.5
press "$captures_tab" "the Captures tab" 2.5
if [[ "$live" == 1 ]]; then
  tap "text=Read it now"
  # the read, live: until the card is no longer reading
  sleep 2
  end=$((SECONDS + 150))
  while ((SECONDS < end)) && [[ -n "$(at "text=Reading")" ]]; do sleep 2; done
  rec_stop 1
else
  rec_stop 0.5
fi
# what the take should end on, checked off camera
wait_for 5 "text=2 photo(s) · Frappe maker agitator" || { echo "phone: the capture is not on the Captures tab" >&2; exit 1; }

a pull /sdcard/opl-take-a.mp4 "$work/a.mp4" >/dev/null
a pull /sdcard/opl-take-b.mp4 "$work/b.mp4" >/dev/null
# the two parts cut together at a steady frame rate. screenrecord writes a frame only when the
# screen changes, so a still screen ends a recording early: the first part is its one frame
# held for two seconds, and the last frame of the second (the Captures list) is held too
ffmpeg -nostdin -loglevel error -y -i "$work/a.mp4" -i "$work/b.mp4" -filter_complex \
  "[0:v]select=eq(n\\,0),loop=loop=59:size=1:start=0,setpts=N/30/TB,format=yuv420p[a];[1:v]fps=30,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=2.5,format=yuv420p[b];[a][b]concat=n=2:v=1:a=0[v]" \
  -map "[v]" -c:v libx264 -preset medium -crf 18 -movflags +faststart "$out"
echo "phone: $out"
