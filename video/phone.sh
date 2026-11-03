#!/usr/bin/env bash
# The phone scene (S19) on a connected Android phone or a running emulator, for
# video/generate.sh: the app reaches the generator's stack through adb reverse, the access
# code is typed into the Backend tab before the recording starts (the field hides it, and the
# tab is never on camera), then screenrecord takes Capture, two photos of the agitator from the
# gallery, a name, Send, and the Captures tab with Read it now. Afterwards the pushed photos are
# deleted, the reverse ports removed and the app's data cleared (it stays installed).
#
# Usage: video/phone.sh <out.mp4>
#   VIDEO_PHONE_SERIAL  the device (adb devices); required, nothing else is touched
#   FRONTEND_PORT, DEMO_ACCESS_CODE  from generate.sh
# The phone must be unlocked with the screen on (Developer options, Stay awake); a locked
# phone is refused, never unlocked from here.
set -euo pipefail

out="${1:?usage: video/phone.sh <out.mp4>}"
serial="${VIDEO_PHONE_SERIAL:?set VIDEO_PHONE_SERIAL to the phone's serial (adb devices)}"
port="${FRONTEND_PORT:?FRONTEND_PORT is not set}"
app=com.orphanparts.lens
dir=/sdcard/Pictures/opl-demo
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
photos="$here/../demo/photos"
work="$(mktemp -d)"
a() { adb -s "$serial" "$@"; }

cleanup() {
  a shell "pkill -INT screenrecord" >/dev/null 2>&1 || true
  a shell rm -rf "$dir" /sdcard/opl-take.mp4 /sdcard/opl-ui.xml >/dev/null 2>&1 || true
  a shell content call --method scan_volume --uri content://media --arg external_primary >/dev/null 2>&1 || true
  a reverse --remove-all >/dev/null 2>&1 || true
  a shell pm clear "$app" >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT

a get-state >/dev/null 2>&1 || { echo "phone: $serial is not connected" >&2; exit 1; }
a shell pm path "$app" >/dev/null 2>&1 || { echo "phone: the app ($app) is not installed on $serial" >&2; exit 1; }
if a shell dumpsys window | grep -q 'isKeyguardShowing=true'; then
  echo "phone: $serial is locked; unlock it and turn on Stay awake (it is never unlocked from here)" >&2
  exit 1
fi

# tap <text>: the middle of the first node whose text or description starts with it
tap() {
  local want="$1" xy
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    a shell uiautomator dump /sdcard/opl-ui.xml >/dev/null 2>&1 || true
    a shell cat /sdcard/opl-ui.xml >"$work/ui.xml" 2>/dev/null || true
    xy="$(python3 - "$work/ui.xml" "$want" <<'EOF'
import re, sys, xml.etree.ElementTree as ET
try:
    root = ET.parse(sys.argv[1]).getroot()
except Exception:
    sys.exit(0)
want = sys.argv[2]
for n in root.iter("node"):
    t = (n.get("text") or "") + "|" + (n.get("content-desc") or "")
    if any(part.startswith(want) for part in t.split("|")):
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", n.get("bounds")))
        print((x1 + x2) // 2, (y1 + y2) // 2)
        break
EOF
)"
    if [[ -n "$xy" ]]; then
      # shellcheck disable=SC2086
      a shell input tap $xy
      sleep 1.2
      return 0
    fi
    sleep 1
  done
  echo "phone: nothing on screen reads \"$want\"" >&2
  return 1
}

type_text() { a shell input text "$(printf '%s' "$1" | sed 's/ /%s/g')"; sleep 0.6; }

# the stack, as localhost on the phone
a reverse "tcp:$port" "tcp:$port" >/dev/null
# two photos of the agitator in the gallery, in their own folder
a shell mkdir -p "$dir"
for p in agitator-head.jpg agitator-coupling.jpg; do a push "$photos/$p" "$dir/$p" >/dev/null; done
a shell content call --method scan_volume --uri content://media --arg external_primary >/dev/null 2>&1 || true

# the backend, off camera: the address and the code typed into the Backend tab
a shell pm clear "$app" >/dev/null
a shell am start -W -n "$app/.MainActivity" >/dev/null
sleep 2
tap "Backend"
tap "Backend URL"
type_text "http://localhost:$port"
tap "Access code"
a shell input text "$DEMO_ACCESS_CODE"
a shell input keyevent 4 >/dev/null 2>&1 || true
tap "Save"
tap "Capture"
sleep 1

# on camera
a shell screenrecord --bit-rate 8000000 --time-limit 60 /sdcard/opl-take.mp4 &
rec=$!
sleep 1.5
tap "Photos from the gallery"
sleep 2
# the system photo picker: the two newest photos, then its add button
tap "Photo taken" || tap "Photo"
tap "Photo taken" || true
tap "Add" || tap "Done" || true
sleep 1.5
tap "Name, if you know it"
type_text "Frappe maker agitator"
a shell input keyevent 4 >/dev/null 2>&1 || true
tap "Send"
sleep 3
tap "Captures"
sleep 2
tap "Read it now" || true
sleep 6
a shell "pkill -INT screenrecord" >/dev/null 2>&1 || true
wait "$rec" 2>/dev/null || true
sleep 1
a pull /sdcard/opl-take.mp4 "$out" >/dev/null
echo "phone: $out"
