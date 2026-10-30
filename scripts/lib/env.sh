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
# stands (a second line for the same key is dropped, since Compose would read the last one),
# or appended when there is none; comments and every other line untouched, the file's inode
# and mode kept. The value is written as it is; a value with spaces or # should be quoted by
# the caller.
env_set() {
  local key="$1" value="$2" file="${3:-$(project_root)/.env}" tmp done=0 line rc
  [[ -f "$file" ]] || : > "$file"
  tmp="$(mktemp)" || return 1
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "${line#export }" == "$key="* ]]; then
      [[ $done -eq 1 ]] && continue
      printf '%s=%s\n' "$key" "$value" >> "$tmp"; done=1
    else
      printf '%s\n' "$line" >> "$tmp"
    fi
  done < "$file"
  [[ $done -eq 1 ]] || printf '%s=%s\n' "$key" "$value" >> "$tmp"
  cat "$tmp" > "$file"; rc=$?
  rm -f -- "$tmp"
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
