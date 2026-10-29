#!/usr/bin/env bash
# release.sh [--dry-run]: tag the version in VERSION on main and push the tag, by hand.
#
# The repository's rules let only its admin create a tag, so this is the admin's command. It
# refuses unless the checkout is main, clean and level with origin, VERSION matches every
# manifest and the changelog has the section, and no such tag exists here or on origin.
# Then it creates the tag on HEAD and pushes it. The tag push starts the release workflow:
# the images are built, smoke-tested and published, the notes assembled, the release created.
# After that, `./dev deploy` puts the release on the host.
#
#   --dry-run   run every check and show what would be tagged; create and push nothing
#
# Environment:
#   ROOT   the repository (default: the parent of this script's directory)
set -euo pipefail

root="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
dry_run=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=1 ;;
    *) printf 'release: unknown argument %s\n' "$arg" >&2; exit 2 ;;
  esac
done

fail() { printf 'release: %s\n' "$*" >&2; exit 1; }
say() { printf 'release: %s\n' "$*"; }

[[ -f "$root/VERSION" ]] || fail "no VERSION file; ./dev version <x.y.z> writes it"
version="$(tr -d '[:space:]' < "$root/VERSION")"

branch="$(git -C "$root" rev-parse --abbrev-ref HEAD)"
[[ "$branch" == "main" ]] || fail "a release is tagged on main, not on '$branch'"
[[ -z "$(git -C "$root" status --porcelain)" ]] || fail "the working tree is not clean"

git -C "$root" fetch --quiet --tags origin || fail "could not fetch origin"
local_head="$(git -C "$root" rev-parse HEAD)"
remote_head="$(git -C "$root" rev-parse origin/main 2>/dev/null)" || fail "origin has no main branch"
[[ "$local_head" == "$remote_head" ]] || fail "main is not level with origin/main; pull or push first"

# The same checks the merge workflow runs: format, manifests, changelog, no such tag.
ROOT="$root" bash "$root/scripts/release-tag.sh" "release/$version" >/dev/null
if git -C "$root" ls-remote --tags origin "refs/tags/$version" | grep -q .; then
  fail "tag $version exists on origin already; existing tags are never moved"
fi

say "version $version, on main at ${local_head:0:7}, every check passed"
if [[ "$dry_run" -eq 1 ]]; then
  say "dry run: nothing tagged, nothing pushed"
  exit 0
fi

git -C "$root" tag "$version"
git -C "$root" push origin "refs/tags/$version"
say "tag $version pushed; the release workflow builds, smoke-tests and publishes it"
say "when the release is up: ./dev deploy"
