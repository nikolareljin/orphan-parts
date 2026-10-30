#!/usr/bin/env bash
# android.sh <build|test|release|install|smoke>: the app's checks, and a run on a device.
#
#   build    the debug APK (gradlew assembleDebug)
#   test     the unit tests on the JVM (gradlew testDebugUnitTest)
#   release  the release APK: signed with the release key when one is given (KEYSTORE_PATH,
#            KEYSTORE_PASSWORD, KEY_ALIAS, KEY_PASSWORD, or android/keystore.properties),
#            with the debug key otherwise
#   install  the debug APK onto the connected device or the running emulator
#   smoke    install, launch, confirm the app is on screen, keep a screenshot, stop it
#
# Environment:
#   ANDROID_HOME     the SDK (default: ~/Android/Sdk when it exists)
#   ANDROID_SERIAL   which device, when several are connected (adb reads it)
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
  build|test|release|install|smoke) ;;
  *) printf 'android: usage: android.sh <build|test|release|install|smoke>\n' >&2; exit 2 ;;
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

gradle() { (cd "$app" && "$gradlew" --quiet "$@"); }

build_debug() {
  say "building the debug APK"
  gradle assembleDebug
  [[ -f "$debug_apk" ]] || fail "no APK at $debug_apk after the build"
  say "$debug_apk"
}

# The first device adb lists as ready; empty when there is none.
device() {
  "$adb" devices 2>/dev/null | awk 'NR > 1 && $2 == "device" { print $1; exit }'
}

booted="" # the emulator this run started, to stop at the end
stop_emulator() {
  if [[ -n "$booted" ]]; then
    say "stopping the emulator"
    "$adb" emu kill >/dev/null 2>&1 || true
  fi
}

ensure_device() {
  if [[ -n "$(device)" ]]; then return 0; fi
  [[ -n "${ANDROID_AVD:-}" ]] || fail "no device connected and ANDROID_AVD is not set; connect a phone with USB debugging on, or name an emulator"
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
  say "emulator ready after ${waited} s"
}

install_debug() {
  [[ -f "$debug_apk" ]] || build_debug
  ensure_device
  say "installing on $(device)"
  "$adb" install -r "$debug_apk" >/dev/null
}

smoke() {
  install_debug
  local out="${SMOKE_OUT:-$app/app/build/smoke}"
  mkdir -p "$out"
  say "launching $activity"
  "$adb" shell am start -W -n "$activity" >/dev/null
  local waited=0
  # the output is read whole, then searched: grep -q closing the pipe early would fail the
  # pipeline under pipefail and the loop would never see the app
  local shown=""
  until shown="$("$adb" shell dumpsys activity activities 2>/dev/null || true)" && grep -q "$activity" <<<"$shown"; do
    sleep 1
    waited=$((waited + 1))
    [[ $waited -lt 30 ]] || fail "the app did not come on screen in 30 s"
  done
  "$adb" exec-out screencap -p > "$out/smoke.png"
  [[ -s "$out/smoke.png" ]] || fail "the screenshot is empty"
  "$adb" shell am force-stop "$package" >/dev/null 2>&1 || true
  say "on screen; screenshot at $out/smoke.png"
}

case "$what" in
  build) build_debug ;;
  test) say "unit tests"; gradle testDebugUnitTest; say "unit tests passed" ;;
  release)
    say "building the release APK"
    gradle assembleRelease
    apk="$(find "$app/app/build/outputs/apk/release" -name '*.apk' 2>/dev/null | head -1 || true)"
    [[ -n "$apk" ]] || fail "no release APK after the build"
    if [[ -n "${KEYSTORE_PATH:-}" ]] || grep -qs '^KEYSTORE_PATH=' "$app/keystore.properties"; then
      say "$apk (release key)"
    else
      say "$apk (debug key: installs, not for a store)"
    fi
    ;;
  install) install_debug; say "installed" ;;
  smoke) smoke ;;
esac
