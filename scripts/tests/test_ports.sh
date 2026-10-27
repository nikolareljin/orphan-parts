#!/usr/bin/env bash

test_unused_high_port_is_free() {
  assert_true port_free 65123
}

test_ports_check_passes_for_free_ports() {
  assert_true ports_check 65123 65124
}
