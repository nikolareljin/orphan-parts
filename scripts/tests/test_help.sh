#!/usr/bin/env bash

test_script_help_prints_header_block() {
  local f
  f="$(mktemp)"
  printf '#!/usr/bin/env bash\n# first line\n#\n# third line\nset -e\n# not help\n' > "$f"
  assert_eq "$(script_help "$f")" "$(printf 'first line\n\nthird line')"
  rm -f "$f"
}

test_parse_common_args_keeps_positional() {
  parse_common_args /dev/null one -v two -- -h
  assert_eq "${ARGS[*]}" "one two -h"
  unset LOG_DEBUG
}
