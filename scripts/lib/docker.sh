#!/usr/bin/env bash
# Docker Compose v2 helpers.

# compose_cmd: print the compose command to use, or fail with install hints.
compose_cmd() {
  if has_cmd docker && docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  elif has_cmd docker-compose; then
    echo "docker-compose"
  else
    die "Docker Compose v2 not found; install Docker Desktop (macOS) or docker-compose-plugin (Linux)"
  fi
}

# compose <args...>: run compose from the project root with the dev file (plus COMPOSE_FILES extras).
compose() {
  local root cmd
  root="$(project_root)"
  cmd="$(compose_cmd)"
  # shellcheck disable=SC2086
  (cd "$root" && DOCKER_UID="$(id -u)" DOCKER_GID="$(id -g)" $cmd -f docker-compose.yml ${COMPOSE_EXTRA_FILES:-} "$@")
}

# wait_http <url> [seconds]: poll until the URL answers 2xx/3xx.
wait_http() {
  local url="$1" timeout="${2:-60}" i=0
  while (( i < timeout )); do
    if curl -fsS -o /dev/null "$url" 2>/dev/null; then return 0; fi
    sleep 1; i=$((i + 1))
  done
  log_error "timed out after ${timeout}s waiting for $url"
  return 1
}

docker_running() {
  has_cmd docker && docker info >/dev/null 2>&1
}
