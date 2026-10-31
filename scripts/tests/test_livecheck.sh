#!/usr/bin/env bash
# The live check (livecheck/, ./dev live-check): nothing in it reads like a credential, an
# address or an environment file; every file in it is tracked Python or Markdown; it is named
# in both .dockerignore files (belt and braces: the images' build contexts keep it out); the
# command takes its two secrets from the environment, never reads their values itself, never
# records fixtures and reads OPL_FAKE_API strictly.

_lc_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# What the check must never hold, matched in any case (grep -a -i -E): a key, code, token,
# secret or password assigned a literal value (as code, JSON, YAML or dotenv write it), a
# quoted literal of 20 or more key characters (a dev-issued 24-character code, a short key),
# an access code or a key as the Model API writes them, a long hex or base64 run, an email
# address.
_lc_patterns=(
  '(MODEL_API_KEY|ACCESS_CODE|API_KEY|_KEY|_TOKEN|SECRET|PASSWORD)["'"'"']?\]?[[:space:]]*[:=][[:space:]]*["'"'"']?[^[:space:]"'"'"'$]{6,}'
  '["'"'"'][A-Za-z0-9_-]{20,}["'"'"']'
  '(^|[^A-Za-z0-9])sk-'
  '(^|[^A-Za-z0-9])ak-'
  '(^|[^A-Za-z0-9])as-'
  '[A-Fa-f0-9]{32,}'
  '[A-Za-z0-9+/=]{32,}'
  '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
)
# Matched as written (grep -a -E): their case is the point. An Authorization header with a
# value, this project's own key prefix (opl_, in lower case; OPL_FAKE_API is a setting), an AWS
# access key id, a JWT.
_lc_patterns_exact=(
  '[Bb]earer[[:space:]]+[A-Za-z0-9]'
  'opl[-_][A-Za-z0-9_-]{8,}'
  'AKIA[0-9A-Z]{16}'
  'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.'
)
# Quoted literals of 20 or more key characters that are known not to be secrets, each with why:
#   "LIVECHECK_ACCESS_CODE"  the environment variable's name, read with os.environ.get and
#                            reported by said(); never a value
_lc_allowed_literals=(
  '"LIVECHECK_ACCESS_CODE"'
)

# Every file under livecheck/ but the bytecode a run leaves in __pycache__.
_lc_files() {
  find "$_lc_root/livecheck" -type f ! -path '*/__pycache__/*.pyc' | sort
}

# The lines ./dev gained for the check: its help entry, cmd_live_check and its _lc_ helpers.
_lc_dev_lines() {
  awk '
    /^#   live-check/ { help = 1 }
    help && /^#   e2e/ { help = 0 }
    /^(cmd_live_check|_lc_[a-z_]+)\(\)/ { body = 1 }
    help || body { print }
    body && /^}/ { body = 0 }
  ' "$_lc_root/dev"
}

# _lc_hits <case flag: -i or ""> <pattern>: every line under livecheck/ and in the dev lines
# that matches, with the allowed literals taken out first; else nothing.
_lc_hits() {
  local flag="$1" pattern="$2" file
  while IFS= read -r file; do
    _lc_unallowed < "$file" | grep -naE ${flag:+"$flag"} -e "$pattern" | sed "s|^|$file:|" || true
  done < <(_lc_files)
  _lc_dev_lines | _lc_unallowed | grep -naE ${flag:+"$flag"} -e "$pattern" | sed 's/^/dev:/' || true
}

# stdin with every allowed literal replaced by a quoted word too short to match anything.
_lc_unallowed() {
  local literal script=""
  for literal in "${_lc_allowed_literals[@]}"; do
    script+="s|${literal}|\"allowed\"|g;"
  done
  sed -e "$script"
}

test_livecheck_holds_nothing_that_reads_like_a_credential() {
  local pattern
  assert_true [ -n "$(_lc_files)" ]
  assert_true [ -n "$(_lc_dev_lines)" ]
  for pattern in "${_lc_patterns[@]}"; do
    assert_eq "$(_lc_hits -i "$pattern")" ""
  done
  for pattern in "${_lc_patterns_exact[@]}"; do
    assert_eq "$(_lc_hits "" "$pattern")" ""
  done
}

test_livecheck_holds_only_tracked_python_and_markdown() {
  local root="$_lc_root" file rel tracked
  # only .py and .md: no environment file, no data, no key file can sit in the folder
  while IFS= read -r file; do
    rel="${file#"$root/"}"
    case "$rel" in
      *.py|*.md) ;;
      *) assert_eq "$rel" "a .py or .md file under livecheck/" ;;
    esac
  done < <(_lc_files)
  if ! git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf '  note %s: not a git checkout, the tracked check is skipped\n' "$_current"
    return 0
  fi
  # every one of them tracked: an ignored or untracked file is not the check
  tracked="$(git -C "$root" ls-files -- livecheck | sort)"
  assert_eq "$(_lc_files | sed "s|^$root/||")" "$tracked"
}

test_livecheck_passes_gitleaks_when_installed() {
  if ! command -v gitleaks >/dev/null 2>&1; then
    printf '  note %s: gitleaks is not installed, skipped\n' "$_current"
    return 0
  fi
  local empty
  empty="$(mktemp -d)"
  # no allow comments honored, no ignore file but an empty one, no config from the folder
  assert_true gitleaks dir "$_lc_root/livecheck" --no-banner --log-level error \
    --ignore-gitleaks-allow --gitleaks-ignore-path "$empty"
  rmdir "$empty"
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
  # dev hands both on by name, never as a value on a command line, and reads neither value
  assert_true grep -q -- '-e MODEL_API_KEY)' <(_lc_dev_lines)
  assert_true grep -q -- '-e LIVECHECK_ACCESS_CODE)' <(_lc_dev_lines)
  assert_false grep -Eq -- '-e "?(MODEL_API_KEY|LIVECHECK_ACCESS_CODE)=' <(_lc_dev_lines)
  assert_false grep -Eq 'env_get "?(MODEL_API_KEY|LIVECHECK_ACCESS_CODE)' <(_lc_dev_lines)
  assert_false grep -Eq '(export|local)[[:space:]].*(MODEL_API_KEY|LIVECHECK_ACCESS_CODE)=' <(_lc_dev_lines)
}

test_dev_live_check_is_listed_and_refuses_an_unknown_option() {
  assert_true grep -q '^ *live-check \[--ops' <(bash "$_lc_root/dev" help)
  assert_false bash "$_lc_root/dev" live-check --bogus 2>/dev/null
}

# A copy of the tree's dev and its libraries with a fake .env and a docker that prints what it
# was asked to run: what ./dev live-check passes on, and what it prints, with no container.
_lc_stage() {
  local work="$1"
  mkdir -p "$work/tree/scripts" "$work/bin"
  cp "$_lc_root/dev" "$work/tree/dev"
  cp -R "$_lc_root/scripts/lib" "$work/tree/scripts/lib"
  [[ ! -f "$_lc_root/.env.example" ]] || cp "$_lc_root/.env.example" "$work/tree/.env.example"
  printf 'MODEL_API_KEY=FAKEKEY_abcdefghijklmnop\nLIVECHECK_ACCESS_CODE=FAKECODE_qrstuvwxyz0123\n' > "$work/tree/.env"
  cat > "$work/bin/docker" <<'SHIM'
#!/usr/bin/env bash
case "$1" in info|version) exit 0 ;; esac
echo "DOCKER ARGV: $*"
SHIM
  chmod +x "$work/bin/docker"
}

# _lc_dev <work> [VAR=value ...] -- <args>: ./dev in the staged copy, output combined.
_lc_dev() {
  local work="$1"; shift
  local envs=()
  while [[ $# -gt 0 && "$1" != "--" ]]; do envs+=("$1"); shift; done
  shift
  env -u MODEL_API_KEY -u LIVECHECK_ACCESS_CODE -u OPL_FAKE_API -u OPL_RECORD_FIXTURES \
    PATH="$work/bin:$PATH" "${envs[@]+"${envs[@]}"}" bash "$work/tree/dev" "$@" 2>&1
}

test_dev_live_check_reads_opl_fake_api_strictly_and_never_records() {
  local work out value
  work="$(mktemp -d)"
  _lc_stage "$work"
  for value in 1 true TRUE yes On; do
    out="$(_lc_dev "$work" OPL_FAKE_API="$value" -- live-check --ops segment)"
    assert_true grep -q -- '-e OPL_FAKE_API=1 -e OPL_RECORD_FIXTURES=0 ' <<<"$out"
  done
  for value in 0 false no OFF; do
    out="$(_lc_dev "$work" OPL_FAKE_API="$value" -- live-check --ops segment)"
    assert_true grep -q -- '-e OPL_FAKE_API=0 -e OPL_RECORD_FIXTURES=0 ' <<<"$out"
  done
  # a value that is neither is refused, not read as a live run
  for value in 2 enabled y; do
    out="$(_lc_dev "$work" OPL_FAKE_API="$value" -- live-check --ops segment)"
    assert_false grep -q 'DOCKER ARGV' <<<"$out"
    assert_true grep -q 'OPL_FAKE_API must be' <<<"$out"
  done
  # recording asked for, in the shell or in .env, is refused before docker
  out="$(_lc_dev "$work" OPL_FAKE_API=1 OPL_RECORD_FIXTURES=1 -- live-check --ops segment)"
  assert_false grep -q 'DOCKER ARGV' <<<"$out"
  assert_true grep -q 'does not record fixtures' <<<"$out"
  printf 'OPL_RECORD_FIXTURES=true\n' >> "$work/tree/.env"
  out="$(_lc_dev "$work" OPL_FAKE_API=1 -- live-check --ops segment)"
  assert_false grep -q 'DOCKER ARGV' <<<"$out"
  assert_true grep -q 'does not record fixtures' <<<"$out"
  rm -rf "$work"
}

test_dev_live_check_never_prints_a_secret_even_traced() {
  local work out
  work="$(mktemp -d)"
  _lc_stage "$work"
  # values in .env only: nothing is passed by name, nothing printed under -d (set -x)
  out="$(_lc_dev "$work" -- -d live-check --ops segment)"
  assert_true grep -q 'DOCKER ARGV' <<<"$out"
  assert_false grep -q 'FAKEKEY_\|FAKECODE_' <<<"$out"
  assert_false grep -q -- '-e MODEL_API_KEY\|-e LIVECHECK_ACCESS_CODE' <<<"$out"
  # values in the shell: passed by name only, still never printed
  out="$(_lc_dev "$work" MODEL_API_KEY=FAKEKEY_shellshellshell LIVECHECK_ACCESS_CODE=FAKECODE_shellshell -- -d live-check --against local)"
  assert_true grep -q -- '-e MODEL_API_KEY -e LIVECHECK_ACCESS_CODE ' <<<"$out"
  assert_false grep -q 'FAKEKEY_\|FAKECODE_' <<<"$out"
  # no key anywhere and no fixture mode: refused before docker
  printf 'MODEL_API_KEY=\n' > "$work/tree/.env"
  out="$(_lc_dev "$work" -- live-check --ops segment)"
  assert_false grep -q 'DOCKER ARGV' <<<"$out"
  assert_true grep -q 'MODEL_API_KEY is empty' <<<"$out"
  rm -rf "$work"
}
