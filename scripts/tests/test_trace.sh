#!/usr/bin/env bash
# Debug tracing (./dev -d, bash -x) never prints a value read from .env or a secret from the
# shell: each path runs traced against a temporary .env holding sentinel values, and the
# sentinels must appear nowhere in what it printed, stdout and stderr together. Uses the dev
# tree and stand-ins of test_gate.sh and test_deploy_hosted.sh.

_trace_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# _trace_dev <dir> [NAME=value...] -- <dev args...>: ./dev in the tree, traced output and all;
# ports no one uses, so the port check passes on any machine.
_trace_dev() {
  local dir="$1"; shift
  local envs=()
  while [[ $# -gt 0 && "$1" != -- ]]; do envs+=("$1"); shift; done
  shift
  _gate_run "$dir" BACKEND_PORT=59871 FRONTEND_PORT=59872 "${envs[@]+"${envs[@]}"}" "$dir/dev" "$@" 2>&1
}

test_trace_env_helpers_print_no_value() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  printf 'MODEL_API_KEY=leakcheck_key\nexport DEMO_ACCESS_CODE="leakcheck_code"\n' > "$dir/.env"
  out="$( (
    set -x
    env_load "$dir/.env"
    env_get MODEL_API_KEY "$dir/.env" >/dev/null
    env_set OTHER plain "$dir/.env"   # rewrites the file, walking the lines with the code
    [[ $- == *x* ]] && echo still-traced
  ) 2>&1)"
  assert_true grep -q '^+.*env_load' <<<"$out"
  assert_true grep -q 'still-traced' <<<"$out"   # tracing is back on after each helper
  assert_false grep -q 'leakcheck_' <<<"$out"
  _gate_cleanup "$dir"
}

test_trace_dev_debug_never_prints_an_env_value() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _gate_tree "$dir"
  printf 'MODEL_API_KEY=leakcheck_key\nDEMO_ACCESS_CODE=leakcheck_code\nLIVECHECK_ACCESS_CODE=leakcheck_lc\nLAN_ADDRESS=10.0.0.9\n' > "$dir/.env"
  # up: the key read for presence (live mode)
  out="$(_trace_dev "$dir" -- -d up)" && assert_true true || assert_true false
  assert_true grep -q '^+' <<<"$out"
  assert_false grep -q 'leakcheck_' <<<"$out"
  # up with no key: fixture mode, the code still untraced
  printf 'MODEL_API_KEY=\nOPL_FAKE_API=0\nDEMO_ACCESS_CODE=leakcheck_code\n' > "$dir/.env"
  out="$(_trace_dev "$dir" -- -d up)" && assert_true true || assert_true false
  assert_true grep -q 'starting in fixture mode' <<<"$out"
  assert_false grep -q 'leakcheck_' <<<"$out"
  # a key in the shell, not in .env
  out="$(_trace_dev "$dir" MODEL_API_KEY=leakcheck_shellkey -- -d up)" && assert_true true || assert_true false
  assert_false grep -q 'leakcheck_' <<<"$out"
  # gate off, with the backend running: the code read, cleared, the backend restarted
  touch "$dir/backend-running"
  out="$(_trace_dev "$dir" -- -d gate off)" && assert_true true || assert_true false
  assert_true grep -q 'the gate is off' <<<"$out"
  assert_false grep -q 'leakcheck_' <<<"$out"
  # gate on prints the master code by design, once, on its own line, and nowhere in the trace
  printf 'OPL_FAKE_API=1\nDEMO_ACCESS_CODE=leakcheck_codexx\n' > "$dir/.env"
  out="$(_trace_dev "$dir" -- -d gate on)" && assert_true true || assert_true false
  assert_eq "$(grep -c 'leakcheck_' <<<"$out")" "1"
  assert_true grep -q '^access code (the master, for you): *leakcheck_codexx$' <<<"$out"
  # e2e with a code set in the shell
  out="$(_trace_dev "$dir" DEMO_ACCESS_CODE=leakcheck_e2e -- -d e2e)" && assert_true true || assert_true false
  assert_true grep -q 'end-to-end checks passed' <<<"$out"
  assert_false grep -q 'leakcheck_' <<<"$out"
  _gate_cleanup "$dir"
}

test_trace_deploy_hosted_from_env_never_prints_a_secret() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _hosted_tree "$dir"
  mkdir -p "$dir/scripts"
  cp "$_trace_repo/scripts/deploy-hosted.sh" "$dir/scripts/deploy-hosted.sh"
  printf '%s\n' MODAL_TOKEN_ID=leakcheck_tid MODAL_TOKEN_SECRET=leakcheck_tsec \
    CLOUDFLARE_API_TOKEN=leakcheck_cf MODEL_API_KEY_DEMO=leakcheck_key \
    DEMO_ACCESS_CODE_HOSTED=leakcheck_code WEB_ORIGIN=https://orphan-parts.pages.dev > "$dir/.env"
  # SHELLOPTS=xtrace traces every bash it starts: deploy.sh, deploy-hosted.sh, the stand-ins
  out="$(env -u WEB_ORIGIN -u DEMO_ACCESS_CODE ROOT="$dir" MODAL="$dir/bin/modal" CURL="$dir/bin/curl" \
    READY_TRIES=2 READY_WAIT=0 SHELLOPTS=xtrace bash "$_trace_repo/scripts/deploy.sh" hosted secret 2>&1)" \
    && assert_true true || assert_true false
  assert_true grep -q '^+.*load_env' <<<"$out"
  assert_true grep -q "^MODEL_API_KEY='leakcheck_key'$" "$dir/secret.env"
  assert_true grep -q "^DEMO_ACCESS_CODE='leakcheck_code'$" "$dir/secret.env"
  assert_false grep -q 'leakcheck_' <<<"$out"
  _gate_cleanup "$dir"
}
