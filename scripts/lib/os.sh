#!/usr/bin/env bash
# Platform detection and command checks. Works on bash 3.2 (macOS) and Linux.

os_name() {
  case "$(uname -s)" in
    Darwin) echo macos ;;
    Linux)
      if [[ -r /proc/version ]] && grep -qi microsoft /proc/version; then echo wsl; else echo linux; fi ;;
    *) echo unknown ;;
  esac
}

is_macos() { [[ "$(os_name)" == macos ]]; }
is_linux() { [[ "$(os_name)" == linux || "$(os_name)" == wsl ]]; }
is_wsl()   { [[ "$(os_name)" == wsl ]]; }

has_cmd() { command -v "$1" >/dev/null 2>&1; }

# require_cmd <cmd> [hint]
require_cmd() {
  has_cmd "$1" && return 0
  die "missing command: $1${2:+ ($2)}" 127
}

# Portable absolute path (readlink -f is GNU-only).
abs_path() {
  local target="$1"
  if [[ -d "$target" ]]; then
    (cd "$target" && pwd)
  else
    (cd "$(dirname "$target")" && printf '%s/%s\n' "$(pwd)" "$(basename "$target")")
  fi
}
