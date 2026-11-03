#!/usr/bin/env bash
# The docs' screenshots (./dev docs-shots, and the phone frames beside them): pixels only.

_shots_root() { cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd; }

test_docs_shots_carry_no_metadata() {
  local root
  root="$(_shots_root)"
  local dir
  for dir in "$root/docs/assets/shots" "$root/docs/assets/phone"; do
    [[ -d "$dir" ]] || continue
    assert_true python3 -I "$root/docs/shots/png_clean.py" --check "$dir"
  done
}

test_docs_shots_png_clean_drops_text_chunks() {
  local root dir
  root="$(_shots_root)"
  dir="$(mktemp -d)"
  mkdir -p "$dir/src/g"
  # a 1x1 PNG with a tEXt chunk, written again without it
  python3 -I - "$dir/src/g/a.png" <<'PY'
import struct, sys, zlib
def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
png += chunk(b"tEXt", b"Comment\x00secret") + chunk(b"IDAT", zlib.compress(b"\x00\x01\x02\x03")) + chunk(b"IEND", b"")
open(sys.argv[1], "wb").write(png)
PY
  assert_false python3 -I "$root/docs/shots/png_clean.py" --check "$dir/src" 2>/dev/null
  python3 -I "$root/docs/shots/png_clean.py" "$dir/src" "$dir/dest" >/dev/null
  assert_true python3 -I "$root/docs/shots/png_clean.py" --check "$dir/dest"
  assert_false grep -q secret "$dir/dest/g/a.png"
  rm -rf "$dir"
}
