#!/usr/bin/env bash
# setup-android.sh [--check]: what building the app needs on this machine, installed or said.
#
#   a JDK 17 or later         apt (Debian, Ubuntu) or Homebrew (macOS) when missing
#   the Android command-line tools under ANDROID_HOME (default ~/Android/Sdk), from Google's
#   archive, their checksum checked; then the licences accepted and these packages:
#   platform-tools (adb), platforms;android-35, build-tools;35.0.0
#
#   --check   print the table and change nothing (exit 1 when something is missing)
#
# Windows is not handled here: use WSL, where this script is the Linux path. Environment:
#   ANDROID_HOME   the SDK (default ~/Android/Sdk)
#   JAVA, SDKMANAGER, CURL, UNZIP, INSTALLER   the commands, for tests to point at stand-ins;
#                  INSTALLER is what runs the package manager (default: sudo apt-get or brew)
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/lib.sh
. "$here/lib/lib.sh"

check_only=0
[[ "${1:-}" == "--check" ]] && check_only=1

TOOLS_BUILD=15859902
TOOLS_SHA_LINUX=4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583
TOOLS_SHA_MAC_X86=c5a6378ab5cf7e0d5701921405115befff13e9ff7417fb588389338f8bd050f3
TOOLS_SHA_MAC_ARM=835b62a26162b229b441d1f6d4680383815a270809eb33522c0d480fa5002c4e
PACKAGES=("platform-tools" "platforms;android-35" "build-tools;35.0.0")

sdk="${ANDROID_HOME:-$HOME/Android/Sdk}"
java_cmd="${JAVA:-java}"
curl_cmd="${CURL:-curl}"
unzip_cmd="${UNZIP:-unzip}"
missing=0

say() { printf 'setup-android: %s\n' "$*"; }
fail() { printf 'setup-android: %s\n' "$*" >&2; exit 1; }

java_major() {
  "$java_cmd" -version 2>&1 | head -1 | sed -E 's/.*"([0-9]+)(\.[0-9]+)*.*/\1/' | grep -E '^[0-9]+$' || echo 0
}

installer() {
  if [[ -n "${INSTALLER:-}" ]]; then "$INSTALLER" "$@"; return; fi
  if is_macos; then brew install "$@"
  elif has_cmd apt-get; then sudo apt-get install -y "$@"
  else fail "install $* with your package manager, then run again"
  fi
}

# --- the JDK ------------------------------------------------------------------
if has_cmd "$java_cmd" && [[ "$(java_major)" -ge 17 ]]; then
  log_ok "java: $("$java_cmd" -version 2>&1 | head -1)"
else
  if [[ $check_only -eq 1 ]]; then log_warn "java: a JDK 17 or later is missing"; missing=1
  else
    say "installing a JDK 17"
    if is_macos; then installer openjdk@17; else installer openjdk-17-jdk; fi
    has_cmd "$java_cmd" && [[ "$(java_major)" -ge 17 ]] || fail "java still not found after the install; put it on PATH"
    log_ok "java: $("$java_cmd" -version 2>&1 | head -1)"
  fi
fi

# --- the command-line tools --------------------------------------------------------
sdkmanager_cmd="${SDKMANAGER:-$sdk/cmdline-tools/latest/bin/sdkmanager}"
if [[ -x "$sdkmanager_cmd" ]]; then
  log_ok "sdkmanager: $sdkmanager_cmd"
else
  if [[ $check_only -eq 1 ]]; then log_warn "sdkmanager: the command-line tools are missing under $sdk"; missing=1
  else
    case "$(os_name)" in
      macos)
        if [[ "$(uname -m)" == arm64 ]]; then name="commandlinetools-mac_arm64-${TOOLS_BUILD}_latest.zip"; sha="$TOOLS_SHA_MAC_ARM"
        else name="commandlinetools-mac_x86_64-${TOOLS_BUILD}_latest.zip"; sha="$TOOLS_SHA_MAC_X86"; fi ;;
      linux|wsl) name="commandlinetools-linux-${TOOLS_BUILD}_latest.zip"; sha="$TOOLS_SHA_LINUX" ;;
      *) fail "unknown platform; install the Android command-line tools by hand" ;;
    esac
    url="${TOOLS_URL:-https://dl.google.com/android/repository/$name}"
    tmp="$(mktemp -d)"
    say "downloading the command-line tools ($name)"
    "$curl_cmd" -fsSL "$url" -o "$tmp/$name"
    got="$(sha256sum "$tmp/$name" 2>/dev/null | awk '{print $1}' || shasum -a 256 "$tmp/$name" | awk '{print $1}')"
    [[ "$got" == "$sha" ]] || fail "the download's checksum does not match; nothing installed"
    mkdir -p "$sdk/cmdline-tools"
    "$unzip_cmd" -q "$tmp/$name" -d "$tmp/unzipped"
    rm -rf "$sdk/cmdline-tools/latest"
    mv "$tmp/unzipped/cmdline-tools" "$sdk/cmdline-tools/latest"
    rm -rf "$tmp"
    sdkmanager_cmd="$sdk/cmdline-tools/latest/bin/sdkmanager"
    [[ -x "$sdkmanager_cmd" ]] || fail "sdkmanager not found after the unpack"
    log_ok "sdkmanager: $sdkmanager_cmd"
  fi
fi

# --- the packages ------------------------------------------------------------------
if [[ -x "$sdkmanager_cmd" ]]; then
  for pkg in "${PACKAGES[@]}"; do
    dir="$sdk/${pkg//;//}"
    if [[ -d "$dir" ]]; then
      log_ok "$pkg"
    elif [[ $check_only -eq 1 ]]; then
      log_warn "$pkg: missing"; missing=1
    else
      say "installing $pkg"
      yes 2>/dev/null | "$sdkmanager_cmd" --sdk_root="$sdk" --licenses >/dev/null 2>&1 || true
      "$sdkmanager_cmd" --sdk_root="$sdk" "$pkg" >/dev/null
      [[ -d "$dir" ]] || fail "$pkg not found under $sdk after the install"
      log_ok "$pkg"
    fi
  done
fi

if [[ $check_only -eq 1 ]]; then
  [[ $missing -eq 0 ]] && say "everything the app needs is here (ANDROID_HOME=$sdk)" || { say "run ./dev setup --android to install what is missing"; exit 1; }
else
  say "ready: ANDROID_HOME=$sdk; next: ./dev phone"
fi
