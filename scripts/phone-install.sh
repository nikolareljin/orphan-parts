#!/usr/bin/env bash
# phone-install.sh: the Orphan Parts Lens app onto an Android phone over USB, from a computer
# with nothing else installed. One command on macOS, Linux and WSL:
#
#   bash scripts/phone-install.sh                 # the latest release's APK
#   bash scripts/phone-install.sh --version 0.3.0 # that release's APK
#   bash scripts/phone-install.sh --apk app.apk   # a file you already have
#
# What it does: finds adb (or downloads Google's platform-tools into ~/.orphan-parts, about
# 10 MB, nothing else), downloads the APK from the GitHub release, waits for one phone with
# USB debugging on, installs the app over any older copy, and opens it. No JDK, no Android
# SDK, no Docker. The phone side (Developer options, USB debugging, the "Allow USB debugging"
# prompt) is in JUDGES.md.
#
# Environment, for tests and odd machines: ADB (the adb command), CURL, UNZIP, TOOLS_DIR
# (where platform-tools go), RELEASES (the GitHub API URL of the releases), PACKAGE.
set -euo pipefail

REPO="${REPO:-nikolareljin/orphan-parts}"
RELEASES="${RELEASES:-https://api.github.com/repos/$REPO/releases}"
PACKAGE="${PACKAGE:-com.orphanparts.lens}"
TOOLS_DIR="${TOOLS_DIR:-$HOME/.orphan-parts}"
PLATFORM_TOOLS="${PLATFORM_TOOLS:-https://dl.google.com/android/repository/platform-tools-latest}"
CURL="${CURL:-curl}"
UNZIP="${UNZIP:-unzip}"

version=""
apk=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) version="${2:-}"; shift 2 ;;
    --apk) apk="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'phone-install: unknown option %s (try --help)\n' "$1" >&2; exit 2 ;;
  esac
done

say() { printf 'phone-install: %s\n' "$*"; }
fail() { printf 'phone-install: %s\n' "$*" >&2; exit 1; }

# --- adb: on the PATH, in a known SDK, or downloaded ----------------------------------------

find_adb() {
  if [[ -n "${ADB:-}" ]]; then printf '%s\n' "$ADB"; return; fi
  if command -v adb >/dev/null 2>&1; then command -v adb; return; fi
  local candidate
  for candidate in "${ANDROID_HOME:-}/platform-tools/adb" "$HOME/Android/Sdk/platform-tools/adb" \
    "$HOME/Library/Android/sdk/platform-tools/adb" "$TOOLS_DIR/platform-tools/adb"; do
    [[ -x "$candidate" ]] && { printf '%s\n' "$candidate"; return; }
  done
  return 1
}

download_adb() {
  local os zip
  case "$(uname -s)" in
    Darwin) os=darwin ;;
    Linux) os=linux ;;
    *) fail "this script runs on macOS, Linux and WSL; on Windows use scripts/phone-install.ps1" ;;
  esac
  mkdir -p "$TOOLS_DIR"
  zip="$TOOLS_DIR/platform-tools.zip"
  say "adb is not installed; downloading Google's platform-tools for $os into $TOOLS_DIR" >&2
  "$CURL" -fsSL -o "$zip" "$PLATFORM_TOOLS-$os.zip" || fail "the platform-tools download failed"
  "$UNZIP" -q -o "$zip" -d "$TOOLS_DIR" || fail "could not unpack $zip (is unzip installed?)"
  rm -f -- "$zip"
  [[ -x "$TOOLS_DIR/platform-tools/adb" ]] || fail "no adb in the download"
  printf '%s\n' "$TOOLS_DIR/platform-tools/adb"
}

adb_cmd="$(find_adb || download_adb)"
say "adb: $adb_cmd"

# --- the APK: a file given, or the release's ------------------------------------------------

if [[ -z "$apk" ]]; then
  if [[ -n "$version" ]]; then url="$RELEASES/tags/$version"; else url="$RELEASES/latest"; fi
  say "looking up the release ($url)"
  listing="$("$CURL" -fsSL -H 'Accept: application/vnd.github+json' "$url")" \
    || fail "could not read the release; is the version right, or is the network off?"
  # the first .apk asset's download URL; no JSON tool is assumed on the machine
  apk_url="$(printf '%s\n' "$listing" | grep -o '"browser_download_url": *"[^"]*\.apk"' | head -1 | sed 's/.*"\(https[^"]*\)"/\1/')"
  [[ -n "$apk_url" ]] || fail "that release has no APK attached (try --version, or --apk with a file)"
  apk="$TOOLS_DIR/$(basename "$apk_url")"
  mkdir -p "$TOOLS_DIR"
  say "downloading $(basename "$apk_url")"
  "$CURL" -fsSL -o "$apk" "$apk_url" || fail "the APK download failed"
fi
[[ -f "$apk" ]] || fail "no such file: $apk"

# --- the phone ------------------------------------------------------------------------------

"$adb_cmd" start-server >/dev/null 2>&1 || true
devices="$("$adb_cmd" devices | awk 'NR > 1 && NF >= 2 {print $1, $2}')"
if [[ -z "$devices" ]]; then
  fail "no phone found. Plug it in with a cable that carries data, turn on USB debugging (Settings, Developer options), choose File transfer if the phone asks, and run this again."
fi
if printf '%s\n' "$devices" | grep -q ' unauthorized$'; then
  fail "the phone has not allowed this computer yet: unlock it, tick 'Always allow from this computer' on the 'Allow USB debugging?' prompt, tap Allow, and run this again."
fi
ready="$(printf '%s\n' "$devices" | awk '$2 == "device" {print $1}')"
count="$(printf '%s\n' "$ready" | grep -c . || true)"
[[ "$count" -ge 1 ]] || fail "the phone is connected but not ready (state: $(printf '%s' "$devices" | head -1)); unplug it and plug it in again."
if [[ "$count" -gt 1 && -z "${ANDROID_SERIAL:-}" ]]; then
  fail "more than one device is connected; set ANDROID_SERIAL to one of: $(printf '%s' "$ready" | tr '\n' ' ')"
fi
serial="${ANDROID_SERIAL:-$ready}"

say "installing $(basename "$apk") on $serial"
"$adb_cmd" -s "$serial" install -r "$apk" || fail "the install failed. If the phone says the app is from an unknown source, allow installing over USB in Developer options (some makers call it 'Install via USB') and run this again."
say "opening the app"
"$adb_cmd" -s "$serial" shell monkey -p "$PACKAGE" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
say "done. In the app, open the Backend tab and tap 'Scan to pair' (JUDGES.md, step 4)."
