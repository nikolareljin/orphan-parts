#!/usr/bin/env bash
# Exit handlers that stack instead of overwriting each other.

_on_exit_fns=()
_tmp_dirs=()

# on_exit <function>: call the function when the script exits, in reverse registration order.
# A function name, not a command string: nothing is re-parsed by the shell at exit.
on_exit() {
  _on_exit_fns=("$1" "${_on_exit_fns[@]}")
  trap '_run_on_exit' EXIT
}

_run_on_exit() {
  local status=$? fn
  for fn in "${_on_exit_fns[@]}"; do
    "$fn" || true
  done
  return $status
}

_rm_tmp_dirs() {
  (( ${#_tmp_dirs[@]} )) && rm -rf -- "${_tmp_dirs[@]}"
  _tmp_dirs=()
}

# tmp_dir: create a temp dir that is removed on exit, print its path.
tmp_dir() {
  local d
  d="$(mktemp -d "${TMPDIR:-/tmp}/opl.XXXXXX")"
  (( ${#_tmp_dirs[@]} )) || on_exit _rm_tmp_dirs
  _tmp_dirs+=("$d")
  echo "$d"
}

_kill_jobs() {
  local p
  for p in $(jobs -p); do kill "$p" 2>/dev/null || true; done
}

# kill_group_on_exit: stop every background job this script started.
kill_group_on_exit() {
  on_exit _kill_jobs
}
