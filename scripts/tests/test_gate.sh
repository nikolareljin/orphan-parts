#!/usr/bin/env bash
# ./dev gate: a copy of the dev script and its library in a temporary tree, with stand-ins for
# docker (compose included) and curl that record what they were told.

_gate_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

_gate_cleanup() { [[ -n "${1:-}" && -d "$1" && "$1" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$1"; }

# The docker stand-in answers `compose version` and `info`; `compose ... run ... app.keys issue`
# writes compose noise to stderr around the line "<label>: <code>" on stdout; `compose ps`
# names a container only when the tree has a flag file.
_gate_tree() {
  local dir="$1"
  mkdir -p "$dir/bin" "$dir/scripts"
  cp "$_gate_repo/dev" "$dir/dev"
  cp -R "$_gate_repo/scripts/lib" "$dir/scripts/lib"
  printf 'services: {}\n' > "$dir/docker-compose.yml"
  printf 'OPL_FAKE_API=1\nDEMO_ACCESS_CODE=placeholder-code\n' > "$dir/.env"
  cat > "$dir/bin/docker" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$dir/docker.log"
case "\$*" in
  "compose version"|info) exit 0 ;;
  *"app.keys issue"*)
    echo " Container orphan-parts-backend-run-1  Creating" >&2
    echo "Pulling fs layer" >&2
    [[ -f "$dir/issue-fails" ]] && { echo "keys: a current code is labeled phone" >&2; exit 2; }
    [[ -f "$dir/issue-garbled" ]] && { echo "something else"; exit 0; }
    echo "phone: opl_issued_code_123"
    echo "issued until 2026-11-06; shown once, kept as a hash" >&2
    exit 0 ;;
  *" ps "*) [[ -f "$dir/backend-running" ]] && echo 0123abcd; exit 0 ;;
esac
exit 0
STUB
  printf '#!/usr/bin/env bash\nexit 0\n' > "$dir/bin/curl"
  chmod +x "$dir/bin/"* "$dir/dev"
}

_gate_run() {
  local dir="$1"; shift
  env -u CI -u DEMO_ACCESS_CODE PATH="$dir/bin:$PATH" "$@"
}

test_gate_on_picks_the_issued_code_by_label_despite_stderr_noise() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _gate_tree "$dir"
  out="$(_gate_run "$dir" "$dir/dev" gate on 2>/dev/null)"
  assert_true grep -q 'issued code (for phone, 7 days): *opl_issued_code_123$' <<< "$out"
  assert_true grep -q 'access code (the master, for you): *placeholder-code$' <<< "$out"
  assert_false grep -q 'Creating\|Pulling' <<< "$out"
  # no line for the label: a clear failure, not a wrong code
  touch "$dir/issue-garbled"
  assert_false _gate_run "$dir" "$dir/dev" gate on >/dev/null 2>&1
  out="$(_gate_run "$dir" "$dir/dev" gate on 2>&1)"
  assert_true grep -q 'no line "phone: <code>"' <<< "$out"
  rm -f "$dir/issue-garbled"; touch "$dir/issue-fails"
  out="$(_gate_run "$dir" "$dir/dev" gate on 2>&1)"
  assert_true grep -q 'keys: a current code is labeled phone' <<< "$out"
  _gate_cleanup "$dir"
}

test_gate_refuses_a_shell_code_that_overrides_env() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _gate_tree "$dir"
  out="$(env -u CI PATH="$dir/bin:$PATH" DEMO_ACCESS_CODE=other-placeholder "$dir/dev" gate on 2>&1)"
  assert_true grep -q 'unset DEMO_ACCESS_CODE' <<< "$out"
  assert_false grep -q 'app.keys issue' "$dir/docker.log"
  out="$(env -u CI PATH="$dir/bin:$PATH" DEMO_ACCESS_CODE=placeholder-code "$dir/dev" gate off 2>&1)"
  assert_true grep -q 'unset DEMO_ACCESS_CODE' <<< "$out"
  assert_eq "$(grep DEMO_ACCESS_CODE "$dir/.env")" "DEMO_ACCESS_CODE=placeholder-code"
  # the same value in the shell and .env is no conflict
  assert_true env -u CI PATH="$dir/bin:$PATH" DEMO_ACCESS_CODE=placeholder-code "$dir/dev" gate on >/dev/null 2>&1
  _gate_cleanup "$dir"
}

test_gate_refuses_to_run_in_ci() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _gate_tree "$dir"
  out="$(env -u DEMO_ACCESS_CODE CI=true PATH="$dir/bin:$PATH" "$dir/dev" gate show 2>&1)"
  assert_true grep -q 'never CI' <<< "$out"
  assert_false env -u DEMO_ACCESS_CODE CI=true PATH="$dir/bin:$PATH" "$dir/dev" gate off
  assert_eq "$(grep DEMO_ACCESS_CODE "$dir/.env")" "DEMO_ACCESS_CODE=placeholder-code"
  _gate_cleanup "$dir"
}

test_gate_off_leaves_a_stopped_backend_stopped() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _gate_tree "$dir"
  out="$(_gate_run "$dir" "$dir/dev" gate off 2>&1)"
  assert_true grep -q 'next ./dev up' <<< "$out"
  assert_false grep -q 'up -d backend' "$dir/docker.log"
  assert_eq "$(grep DEMO_ACCESS_CODE "$dir/.env")" "DEMO_ACCESS_CODE="
  touch "$dir/backend-running"
  out="$(_gate_run "$dir" "$dir/dev" gate off 2>&1)"
  assert_true grep -q 'backend restarted' <<< "$out"
  assert_true grep -q 'up -d backend' "$dir/docker.log"
  _gate_cleanup "$dir"
}
