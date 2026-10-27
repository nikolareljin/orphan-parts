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

# env_require VAR [VAR...]: fail if any variable is unset or empty.
env_require() {
  local name missing=""
  for name in "$@"; do
    [[ -n "${!name:-}" ]] || missing="$missing $name"
  done
  [[ -z "$missing" ]] || die "missing required environment variable(s):$missing"
}
