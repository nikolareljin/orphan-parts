#!/usr/bin/env bash
# Google Search Console's ownership file: mkdocs copies a non-Markdown file under docs/ to the
# site root unchanged, and Google compares it byte for byte, so no trailing newline.

test_docs_site_verification_file_is_exact() {
  local file
  file="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/docs/googlefb1695ee9a07673e.html"
  assert_true test -f "$file"
  assert_eq "$(cat "$file" 2>/dev/null; printf x)" "google-site-verification: googlefb1695ee9a07673e.htmlx"
}
