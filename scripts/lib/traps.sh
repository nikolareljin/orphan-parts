#!/usr/bin/env bash
# Exit handlers that stack instead of overwriting each other.

_on_exit_fns=()
_tmp_dirs=()

# on_exit <function>: call the function when the script exits, in reverse registration order.
# A function name, not a command string: nothing is re-parsed by the shell at exit, and a name
# that is not a function is refused here rather than ignored at exit.
on_exit() {
  if ! declare -F -- "$1" >/dev/null 2>&1; then
    echo "on_exit: not a function: $1" >&2
    return 1
  fi
  # the empty-array expansion is spelled out for bash 3.2 under set -u
  _on_exit_fns=("$1" ${_on_exit_fns[@]+"${_on_exit_fns[@]}"})
  trap '_run_on_exit' EXIT
}

_run_on_exit() {
  local status=$? fn
  for fn in ${_on_exit_fns[@]+"${_on_exit_fns[@]}"}; do
    "$fn" || true
  done
  return $status
}

_rm_tmp_dirs() {
  (( ${#_tmp_dirs[@]} )) && rm -rf -- ${_tmp_dirs[@]+"${_tmp_dirs[@]}"}
  _tmp_dirs=()
}

# tmp_dir <variable>: create a temp dir that is removed on exit and put its path in the
# variable. It assigns rather than prints: inside $(...) the cleanup would be registered in a
# subshell and run the moment that subshell ends, taking the directory with it.
tmp_dir() {
  # the local has an unlikely name: it must not shadow the caller's variable
  local _tmp_dir_made
  _tmp_dir_made="$(mktemp -d "${TMPDIR:-/tmp}/opl.XXXXXX")"
  (( ${#_tmp_dirs[@]} )) || on_exit _rm_tmp_dirs
  _tmp_dirs+=("$_tmp_dir_made")
  printf -v "$1" '%s' "$_tmp_dir_made"
}

_kill_jobs() {
  local p
  for p in $(jobs -p); do kill "$p" 2>/dev/null || true; done
}

# kill_group_on_exit: stop every background job this script started.
kill_group_on_exit() {
  on_exit _kill_jobs
}
