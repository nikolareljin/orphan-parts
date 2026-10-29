#!/usr/bin/env bash
# release-tag.sh <branch>: the version a release branch names, checked before it becomes a tag.
#
#   release/0.2.0 prints 0.2.0 when the version is x.y.z, every manifest carries it, the
#   changelog has its section, and no tag of that name exists. Existing tags are never moved:
#   a version that is tagged already is refused, whatever it points at.
#
# Environment:
#   ROOT   the repository (default: the parent of this script's directory)
set -euo pipefail

root="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
branch="${1:-}"

fail() { printf 'release-tag: %s\n' "$*" >&2; exit 1; }

[[ "$branch" =~ ^release/([0-9]+\.[0-9]+\.[0-9]+)$ ]] \
  || fail "not a release branch with an x.y.z version: '$branch'"
tag="${BASH_REMATCH[1]}"

if git -C "$root" rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
  fail "tag $tag exists already; existing tags are never moved"
fi

py="$(grep -m1 '^version = ' "$root/backend/pyproject.toml" | cut -d'"' -f2)"
init="$(grep -m1 '^__version__ = ' "$root/backend/app/__init__.py" | cut -d'"' -f2)"
js="$(grep -m1 '"version"' "$root/frontend/package.json" | sed -E 's/.*"version": *"([^"]+)".*/\1/')"
if [[ "$tag" != "$py" || "$tag" != "$init" || "$tag" != "$js" ]]; then
  fail "branch names $tag; pyproject $py; app/__init__.py $init; package.json $js"
fi

grep -q "^## $tag\( \|$\)" "$root/CHANGELOG.md" \
  || fail "CHANGELOG.md has no '## $tag' section"

printf '%s\n' "$tag"
