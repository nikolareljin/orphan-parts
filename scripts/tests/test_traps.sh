#!/usr/bin/env bash

test_on_exit_runs_in_reverse_order() {
  local out
  out="$(bash -c '. "'"$here"'/../lib/lib.sh"; one() { echo one; }; two() { echo two; }; on_exit one; on_exit two; exit 0')"
  assert_eq "$out" "$(printf 'two\none')"
}

test_on_exit_keeps_the_exit_status() {
  local status=0
  bash -c '. "'"$here"'/../lib/lib.sh"; say() { echo bye; }; on_exit say; exit 3' >/dev/null || status=$?
  assert_eq "$status" "3"
}

test_tmp_dir_exists_while_the_script_runs_and_is_removed_on_exit() {
  local out d
  out="$(bash -c '. "'"$here"'/../lib/lib.sh"; tmp_dir d; test -d "$d" && echo "alive $d"')"
  d="${out#alive }"
  assert_eq "${out%% *}" "alive"
  assert_false test -d "$d"
}

test_every_tmp_dir_is_removed() {
  local out
  out="$(bash -c '. "'"$here"'/../lib/lib.sh"; tmp_dir a; tmp_dir b; echo "$a $b"')"
  assert_false test -d "${out% *}"
  assert_false test -d "${out#* }"
}

test_on_exit_refuses_a_name_that_is_not_a_function() {
  local status=0 err
  err="$(bash -c '. "'"$here"'/../lib/lib.sh"; on_exit "rm -rf /tmp/never"' 2>&1 >/dev/null)" || status=$?
  assert_eq "$status" "1"
  assert_eq "$err" "on_exit: not a function: rm -rf /tmp/never"
}

test_traps_work_under_set_u() {
  local out
  out="$(bash -uc '. "'"$here"'/../lib/lib.sh"; bye() { echo bye; }; on_exit bye; tmp_dir d; test -d "$d" && echo made')"
  assert_eq "$out" "$(printf 'made\nbye')"
}
