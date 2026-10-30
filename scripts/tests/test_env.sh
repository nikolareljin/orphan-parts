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

test_env_set_replaces_an_indented_key_and_makes_new_files_private() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  printf 'A=1\n  DEMO_ACCESS_CODE=old\n\texport OTHER=x\n' > "$dir/.env"
  assert_eq "$(env_get DEMO_ACCESS_CODE "$dir/.env")" "old"
  env_set DEMO_ACCESS_CODE new "$dir/.env"
  assert_eq "$(tr '\n' '|' < "$dir/.env")" "A=1|DEMO_ACCESS_CODE=new|$(printf '\t')export OTHER=x|"
  env_set OTHER y "$dir/.env"
  assert_eq "$(env_get OTHER "$dir/.env")" "y"
  assert_eq "$(grep -c OTHER "$dir/.env")" "1"
  env_set FIRST one "$dir/made.env"
  assert_eq "$(stat -c %a "$dir/made.env" 2>/dev/null || stat -f %Lp "$dir/made.env")" "600"
  chmod 644 "$dir/.env"; env_set A 2 "$dir/.env"
  assert_eq "$(stat -c %a "$dir/.env" 2>/dev/null || stat -f %Lp "$dir/.env")" "644"
  # the temporary file is made beside the target and gone afterwards
  assert_eq "$(find "$dir" -name '.env.*' | wc -l | tr -d ' ')" "0"
  [[ "$dir" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$dir"
}

test_env_set_and_env_get_agree_on_quotes_crlf_and_special_values() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  printf 'A=1\r\nDEMO_ACCESS_CODE=old\r\nB=2\r\n' > "$dir/.env"
  assert_eq "$(env_get DEMO_ACCESS_CODE "$dir/.env")" "old"
  env_set DEMO_ACCESS_CODE new "$dir/.env"
  assert_eq "$(env_get DEMO_ACCESS_CODE "$dir/.env")" "new"
  assert_eq "$(env_get B "$dir/.env")" "2"
  assert_eq "$(grep -c $'\r$' "$dir/.env")" "3"
  env_set Q '"a b # c"' "$dir/.env"
  assert_eq "$(env_get Q "$dir/.env")" "a b # c"
  env_set E 'x=y=z' "$dir/.env"
  assert_eq "$(env_get E "$dir/.env")" "x=y=z"
  # read as Compose reads it: a " #" comment after an unquoted value, the text inside quotes,
  # the last of two lines for one key
  printf 'C=abc # a note\nH=abc#def\nS='"'"'one two'"'"' # x\nD="q # r" # s\nT=1\nT=2\n' > "$dir/c.env"
  assert_eq "$(env_get C "$dir/c.env")" "abc"
  assert_eq "$(env_get H "$dir/c.env")" "abc#def"
  assert_eq "$(env_get S "$dir/c.env")" "one two"
  assert_eq "$(env_get D "$dir/c.env")" "q # r"
  assert_eq "$(env_get T "$dir/c.env")" "2"
  [[ "$dir" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$dir"
}


test_env_load_uses_last_duplicate_but_keeps_shell_exports() {
  local f
  f="$(mktemp)"
  printf 'DUP_VALUE=first\nDUP_VALUE=last\nDUP_SHELL=first\nDUP_SHELL=last\n' > "$f"
  unset DUP_VALUE
  export DUP_SHELL=shell
  env_load "$f"
  assert_eq "$DUP_VALUE" "last"
  assert_eq "$DUP_SHELL" "shell"
  unset DUP_VALUE DUP_SHELL
  rm -f "$f"
}


test_env_quoted_values_stop_before_quoted_comments() {
  local f
  f="$(mktemp)"
  printf '%s\n' 'QUOTED="value" # "comment"' "SINGLE='value' # it's a comment" > "$f"
  assert_eq "$(env_get QUOTED "$f")" "value"
  assert_eq "$(env_get SINGLE "$f")" "value"
  unset QUOTED SINGLE
  env_load "$f"
  assert_eq "$QUOTED" "value"
  assert_eq "$SINGLE" "value"
  unset QUOTED SINGLE
  rm -f "$f"
}


test_env_set_refuses_invalid_assignments_without_writing() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  assert_false env_set 'BAD NAME' value "$dir/invalid.env"
  assert_false test -e "$dir/invalid.env"
  printf 'FIRST=original\n' > "$dir/fixture.env"
  assert_false env_set FIRST $'value\nSECOND=injected' "$dir/fixture.env"
  assert_eq "$(cat "$dir/fixture.env")" "FIRST=original"
  rm -rf -- "$dir"
}


test_env_load_ignores_names_without_assignments() {
  local f
  f="$(mktemp)"
  printf 'BARE_SETTING\nVALID_SETTING=yes\n' > "$f"
  unset BARE_SETTING VALID_SETTING
  env_load "$f"
  assert_eq "${BARE_SETTING-unset}" "unset"
  assert_eq "$VALID_SETTING" "yes"
  assert_eq "$(env_get BARE_SETTING "$f")" ""
  unset VALID_SETTING
  rm -f "$f"
}
