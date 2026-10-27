#!/usr/bin/env bash
# Runs every test_*.sh in this directory. Each file defines functions named test_* that use
# assert_eq / assert_true / assert_false. Exit code is non-zero when any assertion fails.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/lib.sh
. "$here/../lib/lib.sh"

_pass=0 _fail=0 _current=""

assert_eq() {
  if [[ "$1" == "$2" ]]; then _pass=$((_pass + 1)); else
    _fail=$((_fail + 1)); printf '  FAIL %s: expected [%s] got [%s]\n' "$_current" "$2" "$1"
  fi
}
assert_true()  { if "$@"; then _pass=$((_pass + 1)); else _fail=$((_fail + 1)); printf '  FAIL %s: expected success: %s\n' "$_current" "$*"; fi; }
assert_false() { if "$@"; then _fail=$((_fail + 1)); printf '  FAIL %s: expected failure: %s\n' "$_current" "$*"; else _pass=$((_pass + 1)); fi; }

for file in "$here"/test_*.sh; do
  # shellcheck source=/dev/null
  . "$file"
done

for fn in $(declare -F | awk '{print $3}' | grep '^test_' | sort); do
  _current="$fn"
  "$fn"
done

printf 'scripts: %d passed, %d failed\n' "$_pass" "$_fail"
[[ $_fail -eq 0 ]]
