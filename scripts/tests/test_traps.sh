#!/usr/bin/env bash

test_on_exit_runs_in_reverse_order() {
  local out
  out="$(bash -c '. "'"$here"'/../lib/lib.sh"; on_exit "echo one"; on_exit "echo two"; exit 0')"
  assert_eq "$out" "$(printf 'two\none')"
}

test_tmp_dir_is_removed_on_exit() {
  local d
  d="$(bash -c '. "'"$here"'/../lib/lib.sh"; d=$(tmp_dir); echo "$d"')"
  assert_false test -d "$d"
}
