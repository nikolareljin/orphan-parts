#!/usr/bin/env bash
# ci-changes.sh [<base> <head>]: which of the CI's slow jobs a change needs, as lines for
# $GITHUB_OUTPUT (backend=true|false, web=true|false). The changed files come from
# `git diff --name-only <base> <head>`, or one per line on stdin without arguments.
#
#   backend  the backend job: skipped when every file is documentation, the Android app, the
#            frontend's sources or the browser checks (its tests read frontend/Dockerfile and
#            the compose files, so those still count)
#   web      the frontend and e2e jobs: skipped when every file is documentation or the
#            Android app
#
# Anything not known to be outside a job runs it; an empty or unreadable diff runs everything.
set -euo pipefail

is_docs() {
  case "$1" in
    docs/*|overrides/*|docker/docs/*|mkdocs.yml|*.md) return 0 ;;
  esac
  return 1
}

is_android() {
  case "$1" in
    android/*|scripts/android.sh|.github/workflows/android.yml) return 0 ;;
  esac
  return 1
}

is_web_only() {
  case "$1" in
    frontend/src/*|frontend/public/*|e2e/*) return 0 ;;
  esac
  return 1
}

if [[ $# -eq 2 ]]; then
  files="$(git diff --name-only "$1" "$2")" || files=""
elif [[ $# -eq 0 ]]; then
  files="$(cat)"
else
  printf 'usage: ci-changes.sh [<base> <head>]\n' >&2
  exit 2
fi

backend=false web=false
if [[ -z "$files" ]]; then
  backend=true web=true
fi
while IFS= read -r f; do
  [[ -n "$f" ]] || continue
  if ! is_docs "$f" && ! is_android "$f"; then
    web=true
    is_web_only "$f" || backend=true
  fi
done <<< "$files"

printf 'backend=%s\nweb=%s\n' "$backend" "$web"
