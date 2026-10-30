#!/usr/bin/env bash
# The web app's nginx: the API prefix is a prefix match that wins over the asset regex, so
# /api/pair.svg reaches the backend instead of the static files.

_nginx="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/frontend/nginx.conf"

test_api_prefix_wins_over_the_asset_regex() {
  assert_true grep -Eq '^[[:space:]]*location \^~ /api/ ' "$_nginx"
  assert_true grep -Eq 'location ~\* \\\.\(js\|css\|svg\|woff2\?\)\$' "$_nginx"
}
