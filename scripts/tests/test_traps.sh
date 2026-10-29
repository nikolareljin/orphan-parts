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

test_tmp_dir_is_removed_on_exit() {
  local d
  d="$(bash -c '. "'"$here"'/../lib/lib.sh"; d=$(tmp_dir); echo "$d"')"
  assert_false test -d "$d"
}

test_every_tmp_dir_is_removed() {
  local out
  out="$(bash -c '. "'"$here"'/../lib/lib.sh"; a=$(tmp_dir); b=$(tmp_dir); echo "$a $b"')"
  assert_false test -d "${out% *}"
  assert_false test -d "${out#* }"
}
