#!/usr/bin/env bash
# android.sh <build|test|release|install|smoke>: the app's checks, and a run on a device.
#
#   build    the debug APK (gradlew assembleDebug)
#   test     the unit tests on the JVM (gradlew testDebugUnitTest)
#   release  the release APK: signed with the release key when one is given (KEYSTORE_PATH,
#            KEYSTORE_PASSWORD, KEY_ALIAS, KEY_PASSWORD, or android/keystore.properties),
#            with the debug key otherwise
#   install  the debug APK onto the connected device or the running emulator
#   install-file <apk>  any APK onto the device (./dev phone --release uses it)
#   launch   start the app on the device
#   smoke    install, launch, confirm the app is on screen, keep a screenshot, stop it
#
# Environment:
#   ANDROID_HOME     the SDK (default: ~/Android/Sdk when it exists)
#   ANDROID_SERIAL   which device, when several are connected; without it, one connected
#                    device is used, and several are offered as a numbered list to pick from
#                    (with `dialog` when it is installed and there is a terminal)
#   ANDROID_PICK     the number to pick without asking (tests, scripts)
#   ANDROID_AVD      an emulator to boot headless for the smoke run when no device is connected;
#                    it is stopped afterwards
#   SMOKE_OUT        where the screenshot goes (default: android/app/build/smoke)
#   ADB, GRADLEW     the commands (default: adb from the SDK or PATH, android/gradlew); tests
#                    point them at stand-ins
#   ROOT             the repository (default: the parent of this script's directory)
set -euo pipefail

root="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
what="${1:-}"
case "$what" in
  build|test|release|install|install-file|launch|smoke) ;;
  *) printf 'android: usage: android.sh <build|test|release|install|install-file <apk>|launch|smoke>\n' >&2; exit 2 ;;
esac

fail() { printf 'android: %s\n' "$*" >&2; exit 1; }
say() { printf 'android: %s\n' "$*"; }

app="$root/android"
[[ -f "$app/gradlew" ]] || fail "no app in this tree (android/gradlew)"
if [[ -z "${ANDROID_HOME:-}" && -d "$HOME/Android/Sdk" ]]; then
  export ANDROID_HOME="$HOME/Android/Sdk"
fi
gradlew="${GRADLEW:-$app/gradlew}"
adb="${ADB:-}"
if [[ -z "$adb" ]]; then
  if [[ -n "${ANDROID_HOME:-}" && -x "$ANDROID_HOME/platform-tools/adb" ]]; then
    adb="$ANDROID_HOME/platform-tools/adb"
  else
    adb="adb"
  fi
fi
package="com.orphanparts.lens"
activity="$package/.MainActivity"
debug_apk="$app/app/build/outputs/apk/debug/app-debug.apk"
ALLOW_URL="https://nikolareljin.github.io/orphan-parts/guides/android/#allow-the-phone"
serial="${ANDROID_SERIAL:-}"

gradle() { (cd "$app" && "$gradlew" --quiet "$@"); }

build_debug() {
  say "building the debug APK"
  gradle assembleDebug
  [[ -f "$debug_apk" ]] || fail "no APK at $debug_apk after the build"
  say "$debug_apk"
}

# Every device adb lists: "serial state model" per line (model when adb says it).
devices_table() {
  "$adb" devices -l 2>/dev/null | awk 'NR > 1 && NF >= 2 {
    model = "";
    for (i = 3; i <= NF; i++) if ($i ~ /^model:/) { model = substr($i, 7) }
    print $1, $2, (model == "" ? "-" : model)
  }'
}

# The device every adb call goes to: the one chosen, the one connected, or the one picked.
device() {
  if [[ -n "$serial" ]]; then printf '%s\n' "$serial"; return; fi
  devices_table | awk '$2 == "device" { print $1; exit }'
}

# Choose the device when there are several; say what to do when there is none.
pick_device() {
  local ready unauthorized count
  ready="$(devices_table | awk '$2 == "device"')"
  unauthorized="$(devices_table | awk '$2 == "unauthorized" { print $1 }')"
  if [[ -n "$serial" ]]; then
    grep -q "^$serial device" <<<"$ready" || fail "ANDROID_SERIAL=$serial is not a connected, allowed device"
    return 0
  fi
  count="$(grep -c "" <<<"$ready")"
  [[ -n "$ready" ]] || count=0
  if [[ $count -eq 0 ]]; then
    if [[ -n "$unauthorized" ]]; then
      fail "the phone ($unauthorized) is connected but has not allowed this computer: unlock it and accept the USB debugging prompt, then run again. How to turn it on: $ALLOW_URL"
    fi
    return 1
  fi
  if [[ $count -eq 1 ]]; then
    serial="$(awk '{print $1}' <<<"$ready")"
    return 0
  fi
  local n=0 line choice
  if [[ -n "${ANDROID_PICK:-}" ]]; then
    choice="$ANDROID_PICK"
  elif has_tty && command -v dialog >/dev/null 2>&1; then
    local items=()
    while IFS= read -r line; do n=$((n + 1)); items+=("$n" "$(awk '{print $1 " (" $3 ")"}' <<<"$line")"); done <<<"$ready"
    choice="$(dialog --stdout --title "Which phone?" --menu "Install the app on:" 15 60 "$count" "${items[@]}")" || fail "no device chosen"
  elif has_tty; then
    say "several devices are connected:"
    while IFS= read -r line; do n=$((n + 1)); printf '  %d) %s\n' "$n" "$(awk '{print $1 " (" $3 ")"}' <<<"$line")"; done <<<"$ready"
    printf 'android: which one? [1-%d] ' "$count" > /dev/tty
    read -r choice < /dev/tty
  else
    fail "several devices are connected; set ANDROID_SERIAL to one of: $(awk '{printf "%s ", $1}' <<<"$ready")"
  fi
  [[ "$choice" =~ ^[0-9]+$ && $choice -ge 1 && $choice -le $count ]] || fail "not a number between 1 and $count"
  serial="$(sed -n "${choice}p" <<<"$ready" | awk '{print $1}')"
  say "using $serial"
}

has_tty() { [[ -t 0 || -r /dev/tty ]] && [[ -z "${ANDROID_NO_TTY:-}" ]]; }

booted="" # the emulator this run started, to stop at the end
stop_emulator() {
  if [[ -n "$booted" ]]; then
    say "stopping the emulator"
    "$adb" emu kill >/dev/null 2>&1 || true
  fi
}

ensure_device() {
  if pick_device; then return 0; fi
  [[ -n "${ANDROID_AVD:-}" ]] || fail "no device connected and ANDROID_AVD is not set; connect a phone with USB debugging on (how: $ALLOW_URL), or name an emulator"
  [[ -n "${ANDROID_HOME:-}" && -x "$ANDROID_HOME/emulator/emulator" ]] || fail "no emulator under ANDROID_HOME"
  say "booting the emulator $ANDROID_AVD"
  local log="${TMPDIR:-/tmp}/orphan-parts-emulator.log"
  "$ANDROID_HOME/emulator/emulator" -avd "$ANDROID_AVD" -no-window -no-audio -no-boot-anim -no-snapshot >"$log" 2>&1 &
  booted="$!"
  trap stop_emulator EXIT
  # an emulator that cannot start (an image for another CPU, say) exits at once: say why
  local waited=0
  until [[ "$("$adb" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; do
    if ! kill -0 "$booted" 2>/dev/null; then
      booted=""
      fail "the emulator exited: $(grep -E 'FATAL|ERROR' "$log" | head -1)"
    fi
    sleep 3
    waited=$((waited + 3))
    [[ $waited -lt 240 ]] || fail "the emulator did not finish booting in 240 s"
  done
  serial="$(devices_table | awk '$2 == "device" { print $1; exit }')"
  say "emulator ready after ${waited} s"
}

install_debug() {
  [[ -f "$debug_apk" ]] || build_debug
  ensure_device
  say "installing on $(device)"
  "$adb" -s "$(device)" install -r "$debug_apk" >/dev/null
}

smoke() {
  install_debug
  local out="${SMOKE_OUT:-$app/app/build/smoke}"
  mkdir -p "$out"
  say "launching $activity"
  "$adb" -s "$(device)" shell am start -W -n "$activity" >/dev/null
  local waited=0
  until "$adb" -s "$(device)" shell dumpsys activity activities 2>/dev/null | grep -q "$activity"; do
    sleep 1
    waited=$((waited + 1))
    [[ $waited -lt 30 ]] || fail "the app did not come on screen in 30 s"
  done
  "$adb" -s "$(device)" exec-out screencap -p > "$out/smoke.png"
  [[ -s "$out/smoke.png" ]] || fail "the screenshot is empty"
  "$adb" -s "$(device)" shell am force-stop "$package" >/dev/null 2>&1 || true
  say "on screen; screenshot at $out/smoke.png"
}

case "$what" in
  build) build_debug ;;
  test) say "unit tests"; gradle testDebugUnitTest; say "unit tests passed" ;;
  release)
    say "building the release APK"
    gradle assembleRelease
    apk="$(find "$app/app/build/outputs/apk/release" -name '*.apk' 2>/dev/null | head -1)"
    [[ -n "$apk" ]] || fail "no release APK after the build"
    if [[ -n "${KEYSTORE_PATH:-}" || -f "$app/keystore.properties" ]]; then
      say "$apk (release key)"
    else
      say "$apk (debug key: installs, not for a store)"
    fi
    ;;
  install) install_debug; say "installed" ;;
  install-file)
    apk="${2:?install-file needs the APK path}"
    [[ -f "$apk" ]] || fail "no APK at $apk"
    ensure_device
    say "installing $apk on $(device)"
    "$adb" -s "$(device)" install -r "$apk" >/dev/null
    say "installed"
    ;;
  launch)
    ensure_device
    "$adb" -s "$(device)" shell am start -W -n "$activity" >/dev/null
    say "launched $activity"
    ;;
  smoke) smoke ;;
esac
