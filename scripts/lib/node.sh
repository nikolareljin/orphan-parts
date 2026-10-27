#!/usr/bin/env bash
# Node toolchain for the native dev loop: nvm when available, otherwise whatever node is on PATH.

# node_ensure <frontend_dir>: select the version from .nvmrc and install packages when the
# lockfile changed since the last install.
node_ensure() {
  local dir="$1" root stamp="$1/node_modules/.stamp-lock" want
  root="$(project_root)"
  want="$(tr -d '[:space:]' < "$root/.nvmrc")"
  if [[ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]]; then
    # shellcheck source=/dev/null
    . "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
    nvm use --silent "$want" >/dev/null 2>&1 || { log_info "installing node $want with nvm"; nvm install "$want" >/dev/null; nvm use --silent "$want" >/dev/null; }
  fi
  require_cmd node "install Node $want (nvm install $want) or use the Docker path"
  local have
  have="$(node -p 'process.versions.node.split(".")[0]')"
  [[ "$have" == "$want" ]] || log_warn "node $have found, .nvmrc wants $want"
  if [[ ! -f "$stamp" ]] || [[ "$dir/package-lock.json" -nt "$stamp" ]]; then
    log_info "installing frontend packages"
    (cd "$dir" && npm ci --no-audit --no-fund --loglevel=error)
    touch "$stamp"
  fi
}

# node_run <frontend_dir> <cmd...>
node_run() {
  local dir="$1"; shift
  (cd "$dir" && "$@")
}
