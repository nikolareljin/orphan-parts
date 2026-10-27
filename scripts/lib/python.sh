#!/usr/bin/env bash
# Local Python 3.12 virtualenv for the native dev loop. Never touches the system site-packages.

PY_MIN="3.12"

# py_find: print a python 3.12 interpreter, or fail.
py_find() {
  local candidate
  for candidate in python3.12 python3 python; do
    if has_cmd "$candidate" && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>/dev/null; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

# venv_ensure <backend_dir>: create .venv next to pyproject.toml and install the package when
# pyproject changed since the last install (tracked with a stamp file).
venv_ensure() {
  local dir="$1" venv="$1/.venv" stamp="$1/.venv/.stamp-pyproject" py
  if [[ ! -x "$venv/bin/python" ]]; then
    py="$(py_find)" || die "Python $PY_MIN not found; install it or use the Docker path (./dev up)"
    log_info "creating virtualenv in $venv"
    "$py" -m venv "$venv"
    "$venv/bin/python" -m pip install --quiet --upgrade pip
  fi
  if [[ ! -f "$stamp" ]] || [[ "$dir/pyproject.toml" -nt "$stamp" ]]; then
    log_info "installing backend dependencies"
    "$venv/bin/python" -m pip install --quiet -e "$dir[dev]"
    touch "$stamp"
  fi
}

# venv_run <backend_dir> <cmd...>: run a command with the venv on PATH, from the backend dir.
venv_run() {
  local dir="$1"; shift
  (cd "$dir" && PATH="$dir/.venv/bin:$PATH" VIRTUAL_ENV="$dir/.venv" "$@")
}
