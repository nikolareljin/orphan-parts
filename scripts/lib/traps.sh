#!/usr/bin/env bash
# Exit handlers that stack instead of overwriting each other.

_on_exit_cmds=""

# on_exit <command>: run the command when the script exits, in reverse registration order.
on_exit() {
  _on_exit_cmds="$1"$'\n'"$_on_exit_cmds"
  trap '_run_on_exit' EXIT
}

_run_on_exit() {
  local status=$? cmd
  while IFS= read -r cmd; do
    [[ -n "$cmd" ]] && eval "$cmd" || true
  done <<< "$_on_exit_cmds"
  return $status
}

# tmp_dir: create a temp dir that is removed on exit, print its path.
tmp_dir() {
  local d
  d="$(mktemp -d "${TMPDIR:-/tmp}/opl.XXXXXX")"
  on_exit "rm -rf '$d'"
  echo "$d"
}

# kill_group_on_exit: stop every background job this script started.
kill_group_on_exit() {
  on_exit 'for p in $(jobs -p); do kill "$p" 2>/dev/null || true; done'
}
