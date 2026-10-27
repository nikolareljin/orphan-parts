#!/usr/bin/env bash
# Logging with colors only when stdout is a terminal.
# Set LOG_DEBUG=1 to see log_debug output.

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  _c_reset=$'\033[0m' _c_dim=$'\033[2m' _c_green=$'\033[32m' _c_yellow=$'\033[33m' _c_red=$'\033[31m' _c_blue=$'\033[34m'
else
  _c_reset="" _c_dim="" _c_green="" _c_yellow="" _c_red="" _c_blue=""
fi

log_info()  { printf '%s[info]%s %s\n'  "$_c_blue"   "$_c_reset" "$*"; }
log_ok()    { printf '%s[ok]%s %s\n'    "$_c_green"  "$_c_reset" "$*"; }
log_warn()  { printf '%s[warn]%s %s\n'  "$_c_yellow" "$_c_reset" "$*" >&2; }
log_error() { printf '%s[error]%s %s\n' "$_c_red"    "$_c_reset" "$*" >&2; }
log_debug() { [[ "${LOG_DEBUG:-0}" == "1" ]] && printf '%s[debug] %s%s\n' "$_c_dim" "$*" "$_c_reset" >&2; return 0; }

# die <message> [exit code]
die() {
  log_error "$1"
  exit "${2:-1}"
}
