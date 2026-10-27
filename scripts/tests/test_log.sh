#!/usr/bin/env bash

test_log_info_goes_to_stdout() {
  assert_eq "$(log_info hello 2>/dev/null)" "[info] hello"
}

test_log_warn_goes_to_stderr() {
  assert_eq "$(log_warn hello 2>/dev/null)" ""
  assert_eq "$(log_warn hello 2>&1)" "[warn] hello"
}

test_log_debug_is_silent_by_default() {
  unset LOG_DEBUG
  assert_eq "$(log_debug x 2>&1)" ""
  assert_eq "$(LOG_DEBUG=1 log_debug x 2>&1)" "[debug] x"
}
