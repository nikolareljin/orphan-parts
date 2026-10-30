#!/usr/bin/env bash
# Project root discovery and .env loading.

# project_root: directory that contains the ./dev script, found from this file's location.
project_root() {
  (cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
}

# env_load [file]: export KEY=value lines from a dotenv file. Ignores comments and blank lines.
# Quotes around values are stripped. Existing exported variables win over the file.
env_load() {
  local file="${1:-$(project_root)/.env}"
  [[ -f "$file" ]] || return 0
  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    line="${line#export }"
    key="${line%%=*}"
    value="${line#*=}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    value="${value%\"}"; value="${value#\"}"
    value="${value%\'}"; value="${value#\'}"
    if [[ -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  done < "$file"
}

# env_get KEY [file]: print one value from a dotenv file without exporting anything.
# Empty output when the file or the key is missing. Quotes are stripped as in env_load.
env_get() {
  local want="$1" file="${2:-$(project_root)/.env}"
  [[ -f "$file" ]] || return 0
  local line key value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    line="${line#export }"
    key="${line%%=*}"
    [[ "$key" == "$want" ]] || continue
    value="${line#*=}"
    value="${value%\"}"; value="${value#\"}"
    value="${value%\'}"; value="${value#\'}"
    printf '%s' "$value"
    return 0
  done < "$file"
}

# env_set KEY VALUE [file]: write one value into a dotenv file: the key's line replaced where it
# stands (indented or with `export `, as env_get reads it; a second line for the same key is
# dropped, since Compose would read the last one), or appended when there is none; comments and
# every other line untouched, the file's inode and mode kept. A file it creates is readable by
# its owner alone (600). The new text is put together in a temporary file beside the target,
# removed on failure and on exit, so the value never lands elsewhere. The value is written as
# it is; a value with spaces or # should be quoted by the caller.
_env_set_tmp=""
_env_set_cleanup() { [[ -z "$_env_set_tmp" ]] || rm -f -- "$_env_set_tmp"; _env_set_tmp=""; }
env_set() {
  local key="$1" value="$2" file="${3:-$(project_root)/.env}" done=0 line rest rc=0
  if [[ ! -f "$file" ]]; then
    (umask 077 && : > "$file") || return 1
    chmod 600 "$file" || return 1
  fi
  [[ "$(type -t on_exit)" == function && -z "${_env_set_registered:-}" ]] \
    && on_exit _env_set_cleanup && _env_set_registered=1
  _env_set_tmp="$(mktemp "$(dirname "$file")/.env.XXXXXX")" || { _env_set_tmp=""; return 1; }
  {
    while IFS= read -r line || [[ -n "$line" ]]; do
      rest="${line#"${line%%[![:space:]]*}"}"
      rest="${rest#export }"
      if [[ "$rest" == "$key="* ]]; then
        [[ $done -eq 1 ]] && continue
        printf '%s=%s\n' "$key" "$value"; done=1
      else
        printf '%s\n' "$line"
      fi
    done < "$file"
    [[ $done -eq 1 ]] || printf '%s=%s\n' "$key" "$value"
  } > "$_env_set_tmp" || rc=$?
  [[ $rc -ne 0 ]] || cat -- "$_env_set_tmp" > "$file" || rc=$?
  _env_set_cleanup
  return $rc
}

# env_require VAR [VAR...]: fail if any variable is unset or empty.
env_require() {
  local name missing=""
  for name in "$@"; do
    [[ -n "${!name:-}" ]] || missing="$missing $name"
  done
  [[ -z "$missing" ]] || die "missing required environment variable(s):$missing"
}
