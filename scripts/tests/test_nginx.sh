#!/usr/bin/env bash
# The web app's nginx: the API prefix is a prefix match that wins over the asset regex, so
# /api/pair.svg reaches the backend instead of the static files.

_nginx="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/frontend/nginx.conf"

test_api_prefix_wins_over_the_asset_regex() {
  assert_true grep -Eq '^[[:space:]]*location \^~ /api/ ' "$_nginx"
  assert_true grep -Eq 'location ~\* \\\.\(js\|css\|svg\|woff2\?\)\$' "$_nginx"
}

test_the_api_proxy_passes_the_host_and_port_the_browser_asked_for() {
  assert_true grep -Eq '^[[:space:]]*proxy_set_header Host \$http_host;' "$_nginx"
  assert_true grep -Eq '^[[:space:]]*proxy_set_header X-Forwarded-Host \$http_host;' "$_nginx"
  assert_false grep -Eq 'proxy_set_header Host \$host;' "$_nginx"
}
