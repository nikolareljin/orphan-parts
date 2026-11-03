#!/usr/bin/env bash
# Draft cuts of the demo videos, end to end: a stack of its own in fixture mode, the demo set
# loaded, every web scene recorded with Playwright, the phone scene, the owner's photos, cards,
# titles and captions cut into video/out/main-draft.mp4 and video/out/short-draft.mp4, with a
# contact sheet of the main video's shots (video/out/main-shots.jpg). The stack is torn down
# at the end, its volumes with it; nothing outside video/out/ changes.
#
# Usage: video/generate.sh [--record] [--narration FILE] [--tts] [--phone] [--keep]
#                          [--assemble]
#
#   --record           record the model answers the scenes need, once, with MODEL_API_KEY from
#                      this shell (never written anywhere): the stack runs live with
#                      OPL_RECORD_FIXTURES=1 and a spend cap of VIDEO_SPEND_CAP_USD (default 1),
#                      every answer kept under backend/tests/fixtures/api; a request already
#                      recorded is replayed, not bought again. Review and commit the new
#                      fixtures, then run without --record for the drafts
#   --narration FILE   the owner's narration (WAV, the cut's length), mixed in as is; nothing
#                      is retimed
#   --tts              a rough narration from a local text-to-speech (espeak-ng, espeak or
#                      pico2wave) when one is installed; skipped otherwise
#   --phone            record the phone scene (S19) on the phone or emulator VIDEO_PHONE_SERIAL
#                      names (video/phone.sh: unlocked, the app installed); without it the
#                      app's screenshots stand in. With --record the phone's capture is read
#                      live once too
#   --keep             leave the stack up afterwards (VIDEO_PROJECT, default opl-video)
#   --assemble         only cut the drafts again from the takes already in video/out/work
#
# Ports: VIDEO_BACKEND_PORT (18310) and VIDEO_FRONTEND_PORT (18373), so a running ./dev up is
# never touched. The access code of the stack is made here, used by the scenes and never shown.
# Needs Docker, ffmpeg, python3 and curl.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
# shellcheck source=../scripts/lib/lib.sh
. "$ROOT/scripts/lib/lib.sh"

parse_common_args "${BASH_SOURCE[0]}" "$@"
set -- "${ARGS[@]+"${ARGS[@]}"}"

record=0 narration="" tts=0 android=0 keep=0 assemble_only=0 started=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --record) record=1 ;;
    --narration) [[ $# -ge 2 && -f "$2" ]] || die "--narration needs a WAV file"; narration="$(abs_path "$2")"; shift ;;
    --tts) tts=1 ;;
    --phone) android=1 ;;
    --keep) keep=1 ;;
    --assemble) assemble_only=1 ;;
    *) die "unknown option: $1 (video/generate.sh -h)" ;;
  esac
  shift
done

OUT="$HERE/out"
WORK="$OUT/work"
export COMPOSE_PROJECT_NAME="${VIDEO_PROJECT:-opl-video}"
export COMPOSE_EXTRA_FILES="-f video/compose.video.yml"
export BACKEND_PORT="${VIDEO_BACKEND_PORT:-18310}"
export FRONTEND_PORT="${VIDEO_FRONTEND_PORT:-18373}"
export CORS_ORIGINS="http://localhost:$FRONTEND_PORT"
export VIDEO_WORK="$WORK"
# the scenes are one person clicking, not six workers: the allowances are wide here
export DEMO_REQUESTS_PER_MINUTE=100000 DEMO_VISITOR_CALLS_PER_HOUR=100000 DEMO_DAILY_CALLS=1000000
export PICTURE_ENABLED=1

require_cmd ffmpeg
require_cmd ffprobe
require_cmd python3
require_cmd curl

[[ "$COMPOSE_PROJECT_NAME" != orphan-parts ]] || die "VIDEO_PROJECT must not be the dev stack's project (orphan-parts)"

# The access code of this stack: random, in this process's environment only (compose hands it
# to the backend and the scenes by name), never printed or written to a file.
_make_code() {
  DEMO_ACCESS_CODE="video-$(od -An -N12 -tx1 /dev/urandom | tr -d ' \n')"
  export DEMO_ACCESS_CODE
}

_mode() {
  if [[ $record -eq 1 ]]; then
    untraced _need_key
    export OPL_FAKE_API=0 VIDEO_RECORD=1 VIDEO_SPEND_CAP_USD="${VIDEO_SPEND_CAP_USD:-1}"
    log_warn "record mode: live calls with the key from this shell, at most ${VIDEO_SPEND_CAP_USD} USD"
  else
    # fixture mode hands the backend no key at all, whatever this shell or .env holds
    unset MODEL_API_KEY
    export OPL_FAKE_API=1 VIDEO_RECORD=0
  fi
}

_need_key() {
  [[ -n "${MODEL_API_KEY:-}" ]] || die "--record needs MODEL_API_KEY in this shell (export it; it is never written to a file)"
}

_down() {
  [[ $started -eq 1 ]] || return 0
  started=0
  if [[ $keep -eq 1 ]]; then
    log_info "the stack stays up: http://localhost:$FRONTEND_PORT (COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME)"
    return 0
  fi
  log_info "tearing the stack down"
  compose --profile video down -v --remove-orphans >/dev/null 2>&1 || true
}

stack_up() {
  docker_running || die "docker is not running"
  ports_check "$BACKEND_PORT" "$FRONTEND_PORT" || die "free the ports above or set VIDEO_BACKEND_PORT/VIDEO_FRONTEND_PORT"
  on_exit _down
  started=1
  log_info "stack $COMPOSE_PROJECT_NAME on :$FRONTEND_PORT ($([[ $record -eq 1 ]] && echo record || echo fixture) mode)"
  compose up -d --build backend frontend >/dev/null 2>&1 || { compose logs --tail 30 backend; die "the stack did not start"; }
  wait_http "http://localhost:$BACKEND_PORT/healthz" 120 || die "the backend did not become healthy"
  wait_http "http://localhost:$FRONTEND_PORT" 240 || die "the web app did not start"
}

# The demo set as ./dev demo loads it, with the agitator's device left unanswered: the video
# shows the app asking for it and the label answering. The copy sits in a stage folder of the
# work area whose photos/, listings/ and notes/ point at the demo set's own inside the
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

scenes() {
  rm -rf "$WORK/takes" "$WORK/raw"
  mkdir -p "$WORK/takes"
  log_info "recording the web scenes"
  compose --profile video run --rm --no-deps -T scenes || die "a scene failed (its video and log are under video/out/work/raw)"
}

# Which takes got an operation's stub instead of a recording of that very request: the
# backend logs each such answer ("fixture by operation"); each line's time is matched to the
# takes' wall-clock windows. Written to work/standins.txt as "<shot> <op> ...".
standins() {
  : >"$WORK/standins.txt"
  [[ $record -eq 0 ]] || return 0
  compose logs --no-color --no-log-prefix backend 2>/dev/null >"$WORK/backend.log" || true
  python3 - "$WORK" <<'EOF'
import json, sys
from datetime import datetime
from pathlib import Path
work = Path(sys.argv[1])
takes = []
for meta in sorted((work / "takes").glob("*.json")):
    d = json.loads(meta.read_text())
    takes.append((d["shot"], d["wall"]["from"] / 1000, d["wall"]["to"] / 1000))
found = {}
for line in (work / "backend.log").read_text(errors="replace").splitlines():
    try:
        rec = json.loads(line)
    except ValueError:
        continue
    if rec.get("msg") != "fixture by operation":
        continue
    at = datetime.fromisoformat(rec["ts"]).timestamp()
    for shot, a, b in takes:
        if a <= at <= b:
            found.setdefault(shot, set()).add(rec.get("op", "?"))
(work / "standins.txt").write_text("".join(f"{s} {' '.join(sorted(o))}\n" for s, o in sorted(found.items())))
for s, o in sorted(found.items()):
    print(f"  {s}: stand-in answer for {', '.join(sorted(o))} (record it with --record)")
EOF
}

# The phone scene on the phone VIDEO_PHONE_SERIAL names. Best effort: a step that fails (a
# locked phone, say) leaves the app's screenshots in place.
android_scene() {
  [[ $android -eq 1 ]] || { log_info "phone scene: the app's screenshots (--phone records it)"; return 0; }
  rm -f "$WORK/takes/S19.mp4"
  bash "$HERE/phone.sh" "$WORK/takes/S19.mp4" || log_warn "phone scene: not recorded; the app's screenshots stand in"
}

narrate() {
  if [[ -n "$narration" ]]; then
    printf '%s\n' "$narration"
    return
  fi
  [[ $tts -eq 1 ]] || return 0
  local engine=""
  for engine in espeak-ng espeak pico2wave; do has_cmd "$engine" && break || engine=""; done
  if [[ -z "$engine" ]]; then
    log_warn "--tts: no local text-to-speech (espeak-ng, espeak, pico2wave) is installed; the drafts stay silent" >&2
    return 0
  fi
  python3 "$HERE/tts.py" "$engine" "$HERE/scripts/main.md" "$WORK/tts-main.wav" >&2 && printf '%s\n' "$WORK/tts-main.wav"
}

main() {
  mkdir -p "$WORK"
  if [[ $assemble_only -eq 0 ]]; then
    _mode
    untraced _make_code
    stack_up
    stage
    scenes
    android_scene
    standins
    [[ $record -eq 0 ]] || { log_ok "recorded: new answers under backend/tests/fixtures/api (git status); review and commit them, then run video/generate.sh"; return 0; }
    _down
  fi
  local voice
  voice="$(narrate)"
  log_info "cutting the drafts"
  python3 "$HERE/assemble.py" ${voice:+--narration "$voice"}
  log_ok "video/out/main-draft.mp4, video/out/short-draft.mp4, video/out/main-shots.jpg"
}

main
