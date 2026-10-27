#!/usr/bin/env bash
# Help text from a script's header comment block, and the common -h/-v/-d flags.

# script_help <script_path>: print the comment block after the shebang, uncommented.
script_help() {
  awk 'NR == 1 && /^#!/ {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$1"
}

# parse_common_args <script_path> "$@": handles -h/--help, -v/--verbose, -d/--debug.
# Leaves the remaining arguments in the global array ARGS.
ARGS=()
parse_common_args() {
  local script="$1"; shift
  ARGS=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help) script_help "$script"; exit 0 ;;
      -v|--verbose) export LOG_DEBUG=1 ;;
      -d|--debug) export LOG_DEBUG=1; set -x ;;
      --) shift; ARGS+=("$@"); break ;;
      *) ARGS+=("$1") ;;
    esac
    shift
  done
}
