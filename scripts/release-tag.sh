#!/usr/bin/env bash
# release-tag.sh <branch>: the version a release branch names, checked before it becomes a tag.
#
#   release/0.2.0 prints 0.2.0 when the version is x.y.z, VERSION and every manifest carry
#   it, the changelog has its section, and no tag of that name exists. Existing tags are never moved:
#   a version that is tagged already is refused, whatever it points at.
#
# Environment:
#   ROOT   the repository (default: the parent of this script's directory)
set -euo pipefail

root="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
branch="${1:-}"

fail() { printf 'release-tag: %s\n' "$*" >&2; exit 1; }

# x.y.z as SemVer writes it: no leading zeros, no prefix, nothing after
semver='(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
[[ "$branch" =~ ^release/(${semver})$ ]] \
  || fail "not a release branch with an x.y.z version: '$branch'"
tag="${BASH_REMATCH[1]}"

if git -C "$root" rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
  fail "tag $tag exists already; existing tags are never moved"
fi

# a manifest without its line reads as empty, and the mismatch names it
py="$(grep -m1 '^version = ' "$root/backend/pyproject.toml" | cut -d'"' -f2 || true)"
init="$(grep -m1 '^__version__ = ' "$root/backend/app/__init__.py" | cut -d'"' -f2 || true)"
js="$(grep -m1 '"version"' "$root/frontend/package.json" | sed -E 's/.*"version": *"([^"]+)".*/\1/' || true)"
if [[ "$tag" != "$py" || "$tag" != "$init" || "$tag" != "$js" ]]; then
  fail "branch names $tag; pyproject $py; app/__init__.py $init; package.json $js"
fi
# VERSION is the one place the version is read from by hand; it has to agree with the rest.
if [[ -f "$root/VERSION" ]]; then
  file="$(tr -d '[:space:]' < "$root/VERSION")"
  [[ "$tag" == "$file" ]] || fail "branch names $tag; VERSION says ${file:-nothing}"
fi

grep -qE "^## ${tag//./\\.}( |$)" "$root/CHANGELOG.md" \
  || fail "CHANGELOG.md has no '## $tag' section"

printf '%s\n' "$tag"
