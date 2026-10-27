#!/usr/bin/env bash

test_os_name_is_known() {
  case "$(os_name)" in
    macos|linux|wsl) assert_true true ;;
    *) assert_eq "$(os_name)" "macos|linux|wsl" ;;
  esac
}

test_has_cmd() {
  assert_true has_cmd bash
  assert_false has_cmd definitely-not-a-command-xyz
}

test_require_cmd_fails_loudly() {
  assert_false bash -c '. "'"$here"'/../lib/lib.sh"; require_cmd definitely-not-a-command-xyz' 2>/dev/null
}

test_abs_path_of_dir_and_file() {
  local d
  d="$(mktemp -d)"
  touch "$d/f"
  assert_eq "$(cd "$d" && abs_path .)" "$(cd "$d" && pwd)"
  assert_eq "$(cd "$d" && abs_path f)" "$(cd "$d" && pwd)/f"
  rm -rf "$d"
}
