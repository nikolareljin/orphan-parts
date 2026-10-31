#!/usr/bin/env bash
# The live check (livecheck/, ./dev live-check): nothing in it reads like a credential, an
# address or an environment file; it is named in both .dockerignore files; the command takes
# its two secrets from the environment and refuses anything else on the command line.

_lc_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# What the check must never hold: an access code or a key as this project and the Model API
# write them, a bearer header with a value, a key assignment, a long hex or base64 run, an
# email address. Each pattern is extended grep syntax.
_lc_patterns=(
  'opl_[A-Za-z0-9_-]{8,}'
  '(^|[^A-Za-z0-9])sk-'
  '(^|[^A-Za-z0-9])ak-'
  '(^|[^A-Za-z0-9])as-'
  'Bearer [A-Za-z0-9]'
  'MODEL_API_KEY=.+'
  'api[_-]?key[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"']+'
  '[A-Fa-f0-9]{32,}'
  '[A-Za-z0-9+/=]{32,}'
  '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
)

# Every file under livecheck/ (a cache left by a run is not the check).
_lc_files() {
  find "$_lc_root/livecheck" -type f ! -name '*.pyc' ! -path '*/__pycache__/*' | sort
}

# The lines ./dev gained for the check: its help entry and cmd_live_check, nothing else of dev.
_lc_dev_lines() {
  awk '
    /^#   live-check/ { help = 1 }
    help && /^#   e2e/ { help = 0 }
    /^cmd_live_check\(\)/ { body = 1 }
    help || body { print }
    body && /^}/ { body = 0 }
  ' "$_lc_root/dev"
}

# _lc_hits <pattern>: every line under livecheck/ and in the dev lines that matches, else nothing.
_lc_hits() {
  local pattern="$1" file
  while IFS= read -r file; do
    grep -HEn -e "$pattern" "$file" || true
  done < <(_lc_files)
  _lc_dev_lines | grep -En -e "$pattern" | sed 's/^/dev:/' || true
}

test_livecheck_holds_nothing_that_reads_like_a_credential() {
  local pattern
  assert_true [ -n "$(_lc_files)" ]
  assert_true [ -n "$(_lc_dev_lines)" ]
  for pattern in "${_lc_patterns[@]}"; do
    assert_eq "$(_lc_hits "$pattern")" ""
  done
}

test_livecheck_holds_no_environment_file() {
  assert_eq "$(find "$_lc_root/livecheck" -name '.env*' | sort)" ""
}

test_livecheck_is_named_in_both_dockerignore_files() {
  assert_true grep -qx 'livecheck' "$_lc_root/backend/.dockerignore"
  assert_true grep -qx 'livecheck' "$_lc_root/frontend/.dockerignore"
}

test_livecheck_takes_its_secrets_from_the_environment_only() {
  # the two names are read from the environment in the entry point; no flag names a credential
  assert_true grep -q 'os.environ.get("MODEL_API_KEY"' "$_lc_root/livecheck/__main__.py"
  assert_true grep -q 'os.environ.get("LIVECHECK_ACCESS_CODE"' "$_lc_root/livecheck/__main__.py"
  assert_false grep -Eq 'add_argument\("--(key|code|access|token|secret)' "$_lc_root/livecheck/__main__.py"
  # dev hands the code on by name, never as a value on a command line
  assert_true grep -q -- '-e LIVECHECK_ACCESS_CODE)' <(_lc_dev_lines)
  assert_false grep -Eq -- '-e "?LIVECHECK_ACCESS_CODE=' <(_lc_dev_lines)
}

test_dev_live_check_is_listed_and_refuses_an_unknown_option() {
  assert_true grep -q '^ *live-check \[--ops' <(bash "$_lc_root/dev" help)
  assert_false bash "$_lc_root/dev" live-check --bogus 2>/dev/null
}
