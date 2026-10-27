#!/usr/bin/env bash
# Port checks that work with lsof (macOS, most Linux) or ss (Linux).

# port_who <port>: print the PID/command listening on the port, empty if none.
port_who() {
  local port="$1"
  if has_cmd lsof; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $2" "$1}' | sort -u
  elif has_cmd ss; then
    ss -ltnp 2>/dev/null | awk -v p=":$port" '$4 ~ p"$" {print $6}' | sed 's/users:((\"\([^"]*\)\",pid=\([0-9]*\).*/\2 \1/'
  fi
}

# port_free <port>: true when nothing listens on it.
port_free() {
  [[ -z "$(port_who "$1")" ]]
}

# ports_check <port...>: warn about every port in use, return 1 if any is.
ports_check() {
  local port busy=0 who
  for port in "$@"; do
    who="$(port_who "$port")"
    if [[ -n "$who" ]]; then
      log_warn "port $port is in use by: $who"
      busy=1
    fi
  done
  return $busy
}
