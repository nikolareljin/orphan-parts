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

test_env_get_reads_one_value_without_exporting() {
  local f
  f="$(mktemp)"
  printf '# comment\nFIRST="quoted"\nexport SECOND=2\nEMPTY=\n' > "$f"
  unset FIRST SECOND EMPTY
  assert_eq "$(env_get FIRST "$f")" "quoted"
  assert_eq "$(env_get SECOND "$f")" "2"
  assert_eq "$(env_get EMPTY "$f")" ""
  assert_eq "$(env_get MISSING "$f")" ""
  assert_eq "${FIRST:-unset}" "unset"
  assert_eq "$(env_get ANY /nonexistent/.env)" ""
  rm -f "$f"
}

test_env_require_fails_on_empty() {
  export PRESENT=1 EMPTY=""
  assert_true env_require PRESENT
  assert_false bash -c '. "'"$here"'/../lib/lib.sh"; EMPTY=""; env_require EMPTY' 2>/dev/null
}

test_project_root_contains_dev() {
  assert_true test -x "$(project_root)/dev"
}

test_env_set_replaces_or_appends_one_line_and_touches_nothing_else() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  printf '# a note\nMODEL_API_KEY=kept\nexport DEMO_ACCESS_CODE=old\nLOG_LEVEL=INFO\n' > "$dir/.env"
  env_set DEMO_ACCESS_CODE new-code "$dir/.env"
  assert_eq "$(tr '\n' '|' < "$dir/.env")" "# a note|MODEL_API_KEY=kept|DEMO_ACCESS_CODE=new-code|LOG_LEVEL=INFO|"
  env_set DEMO_ACCESS_CODE "" "$dir/.env"
  assert_eq "$(env_get DEMO_ACCESS_CODE "$dir/.env")" ""
  env_set NEW_NAME value "$dir/.env"
  assert_eq "$(tail -1 "$dir/.env")" "NEW_NAME=value"
  env_set FIRST one "$dir/none.env"
  assert_eq "$(cat "$dir/none.env")" "FIRST=one"
  # a second line for the same key is dropped, a key that is a prefix of another untouched
  printf 'DEMO_ACCESS_CODE=a\nDEMO_ACCESS_CODE_HOSTED=keep\nDEMO_ACCESS_CODE=b\n' > "$dir/dup.env"
  env_set DEMO_ACCESS_CODE c "$dir/dup.env"
  assert_eq "$(tr '\n' '|' < "$dir/dup.env")" "DEMO_ACCESS_CODE=c|DEMO_ACCESS_CODE_HOSTED=keep|"
  # the file's mode is kept, and no temporary file stays behind
  chmod 600 "$dir/dup.env"; env_set DEMO_ACCESS_CODE d "$dir/dup.env"
  assert_eq "$(stat -c %a "$dir/dup.env" 2>/dev/null || stat -f %Lp "$dir/dup.env")" "600"
  [[ "$dir" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$dir"
}
