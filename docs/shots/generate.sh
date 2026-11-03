#!/usr/bin/env bash
# The screenshots of the docs, end to end: a stack of its own in fixture mode (recorded answers,
# no key, nothing spent), the demo set loaded, every guide's steps clicked through with
# Playwright (docs/shots/*.spec.ts) at 1280x800 in the light scheme, each step kept as
# docs/assets/shots/<guide>/<nn-name>.png. Pairing codes and code fields are blurred in the
# page before a shot is taken; every PNG is written again with its pixels alone (no text,
# time or color-profile chunks). A shot with the same pixels as the one already there is left
# as it was, so a second run on the same day changes nothing.
# The stack is torn down at the end, its volumes with it.
#
# Usage: docs/shots/generate.sh [--only PATTERN] [--force] [--keep]
#
#   --only PATTERN   only the tests whose file name or title matches PATTERN (a Playwright
#                    grep, e.g. --only profile); they start from the fresh demo set, so a
#                    guide whose steps build on earlier ones may get stand-in answers
#   --force          write every shot taken, even one with the same pixels as the one there
#   --keep           leave the stack up afterwards (SHOTS_PROJECT, default opl-docs-shots)
#
# Ports: SHOTS_BACKEND_PORT (18410) and SHOTS_FRONTEND_PORT (18473), so a running ./dev up is
# never touched. The web app also gets a private address of its own, SHOTS_LAN_PREFIX.10
# (default 192.168.250.10), for the pairing shots. The access code of the stack is made here,
# used by the shots and never shown. Needs Docker, python3 and curl.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
# shellcheck source=../../scripts/lib/lib.sh
. "$ROOT/scripts/lib/lib.sh"

parse_common_args "${BASH_SOURCE[0]}" "$@"
set -- "${ARGS[@]+"${ARGS[@]}"}"

only="" force=0 keep=0 started=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --only) [[ $# -ge 2 && -n "$2" ]] || die "--only needs a pattern"; only="$2"; shift ;;
    --force) force=1 ;;
    --keep) keep=1 ;;
    *) die "unknown option: $1 (docs/shots/generate.sh -h)" ;;
  esac
  shift
done

WORK="$HERE/out"
DEST="$ROOT/docs/assets/shots"
export COMPOSE_PROJECT_NAME="${SHOTS_PROJECT:-opl-docs-shots}"
export COMPOSE_EXTRA_FILES="-f docs/shots/compose.shots.yml"
export BACKEND_PORT="${SHOTS_BACKEND_PORT:-18410}"
export FRONTEND_PORT="${SHOTS_FRONTEND_PORT:-18473}"
export SHOTS_LAN_PREFIX="${SHOTS_LAN_PREFIX:-192.168.250}"
export CORS_ORIGINS="http://localhost:$FRONTEND_PORT"
export SHOTS_WORK="$WORK" SHOTS_ONLY="$only"
# one person clicking through: requests unbounded, the live-call allowances (in the footer of
# every shot) at round numbers the run stays well under
export DEMO_REQUESTS_PER_MINUTE=100000 DEMO_VISITOR_CALLS_PER_HOUR=100 DEMO_DAILY_CALLS=300
export PICTURE_ENABLED=1
# fixture mode hands the backend no key at all, whatever this shell or .env holds
unset MODEL_API_KEY
export OPL_FAKE_API=1

require_cmd python3
require_cmd curl

[[ "$COMPOSE_PROJECT_NAME" != orphan-parts ]] || die "SHOTS_PROJECT must not be the dev stack's project (orphan-parts)"

# The access code of this stack: random, in this process's environment only (compose hands it
# to the backend and the shots by name), never printed or written to a file.
_make_code() {
  DEMO_ACCESS_CODE="shots-$(od -An -N12 -tx1 /dev/urandom | tr -d ' \n')"
  export DEMO_ACCESS_CODE
}

_down() {
  [[ $started -eq 1 ]] || return 0
  started=0
  if [[ $keep -eq 1 ]]; then
    log_info "the stack stays up: http://localhost:$FRONTEND_PORT (COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME)"
    return 0
  fi
  log_info "tearing the stack down"
  compose --profile shots down -v --remove-orphans >/dev/null 2>&1 || true
}

stack_up() {
  docker_running || die "docker is not running"
  ports_check "$BACKEND_PORT" "$FRONTEND_PORT" || die "free the ports above or set SHOTS_BACKEND_PORT/SHOTS_FRONTEND_PORT"
  on_exit _down
  started=1
  log_info "stack $COMPOSE_PROJECT_NAME on :$FRONTEND_PORT (fixture mode)"
  compose up -d --build backend frontend >/dev/null 2>&1 || { compose logs --tail 30 backend; die "the stack did not start"; }
  wait_http "http://localhost:$BACKEND_PORT/healthz" 120 || die "the backend did not become healthy"
  wait_http "http://localhost:$FRONTEND_PORT" 240 || die "the web app did not start"
}

# The demo set as ./dev demo loads it, with the parts' devices left unanswered: the inventory
# guide shows the app asking for the device and a label photo answering. The copy sits in a
# stage folder whose photos/, listings/ and notes/ point at the demo set's own inside the
# container, so nothing is written under demo/.
stage() {
  local dir="$WORK/stage"
  rm -rf "$dir"
  mkdir -p "$dir"
  grep -vE '^    parent_(photos|device|device_model):' "$ROOT/demo/set.yaml" >"$dir/set.yaml"
  grep -q 'key: frappe_agitator' "$dir/set.yaml" || die "demo/set.yaml has no frappe_agitator item"
  ln -s /demo/photos "$dir/photos"
  ln -s /demo/listings "$dir/listings"
  ln -s /demo/notes "$dir/notes"
  compose stop backend >/dev/null 2>&1
  compose run --rm --no-deps -T -e OPL_FAKE_API=1 -v "$dir:/stage:ro" backend \
    python -m app.demo load --set /stage/set.yaml --reset 2>/dev/null | grep -v '^{' || die "the demo set did not load"
  compose up -d backend frontend >/dev/null 2>&1
  wait_http "http://localhost:$BACKEND_PORT/readyz" 120 || die "the backend did not come back"
  wait_http "http://localhost:$FRONTEND_PORT" 120 || die "the web app did not come back"
}

shots() {
  rm -rf "$WORK/png" "$WORK/raw"
  mkdir -p "$WORK/png"
  log_info "taking the shots"
  compose --profile shots run --rm --no-deps -T shots || die "a shot failed (its trace is under docs/shots/out/raw)"
}

# Which shots got an operation's stub instead of a recording of that very request: the backend
# logs each such answer ("fixture by operation"); listed so the guide's text is checked against
# what the shot really shows.
standins() {
  compose logs --no-color --no-log-prefix backend 2>/dev/null >"$WORK/backend.log" || true
  python3 - "$WORK/backend.log" <<'EOF'
import json, sys
ops = {}
for line in open(sys.argv[1], errors="replace"):
    try:
        rec = json.loads(line)
    except ValueError:
        continue
    if rec.get("msg") == "fixture by operation":
        ops[rec.get("op", "?")] = ops.get(rec.get("op", "?"), 0) + 1
for op, n in sorted(ops.items()):
    print(f"  stand-in answer for {op} ({n}x): no recording of that exact request")
EOF
}

# Every PNG under work/png written again into docs/assets/shots with its pixels alone, unless
# the one there has the same pixels (docs/shots/png_clean.py).
publish() {
  local args=("$WORK/png" "$DEST")
  [[ $force -eq 1 ]] && args+=(--force)
  python3 -I "$HERE/png_clean.py" "${args[@]}"
}

main() {
  mkdir -p "$WORK"
  untraced _make_code
  stack_up
  stage
  shots
  standins
  _down
  publish
  log_ok "docs/assets/shots/ (git status shows what changed)"
}

main
