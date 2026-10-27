#!/usr/bin/env bash

test_env_load_reads_values_and_strips_quotes() {
  local f
  f="$(mktemp)"
  printf '# comment\n\nA_PLAIN=1\nB_QUOTED="two words"\nexport C_EXPORTED=3\nbad key=4\n' > "$f"
  unset A_PLAIN B_QUOTED C_EXPORTED
  env_load "$f"
  assert_eq "$A_PLAIN" "1"
  assert_eq "$B_QUOTED" "two words"
  assert_eq "$C_EXPORTED" "3"
  rm -f "$f"
}

test_env_load_keeps_existing_exports() {
  local f
  f="$(mktemp)"
  printf 'KEEP_ME=file\n' > "$f"
  export KEEP_ME=shell
  env_load "$f"
  assert_eq "$KEEP_ME" "shell"
  rm -f "$f"
}

test_env_load_missing_file_is_fine() {
  assert_true env_load /nonexistent/.env
}

test_env_require_fails_on_empty() {
  export PRESENT=1 EMPTY=""
  assert_true env_require PRESENT
  assert_false bash -c '. "'"$here"'/../lib/lib.sh"; EMPTY=""; env_require EMPTY' 2>/dev/null
}

test_project_root_contains_dev() {
  assert_true test -x "$(project_root)/dev"
}
