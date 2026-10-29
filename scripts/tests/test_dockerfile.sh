#!/usr/bin/env bash
# The backend image: the production stage runs one worker without reload, the dev stage reloads.

_dockerfile="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/backend/Dockerfile"

# The CMD line of one stage: the last CMD before the next FROM (or the end of the file).
_stage_cmd() {
  awk -v stage="$1" '
    /^FROM / { in_stage = ($0 ~ " AS " stage "$") }
    in_stage && /^CMD / { cmd = $0 }
    END { print cmd }
  ' "$_dockerfile"
}

test_production_stage_runs_one_worker() {
  local cmd
  cmd="$(_stage_cmd prod)"
  assert_true grep -q -- '"--workers", "1"' <<<"$cmd"
  assert_false grep -q -- '--reload' <<<"$cmd"
}

test_dev_stage_reloads_in_one_process() {
  local cmd
  cmd="$(_stage_cmd dev)"
  assert_true grep -q -- '--reload' <<<"$cmd"
  assert_false grep -q -- '--workers' <<<"$cmd"
}
