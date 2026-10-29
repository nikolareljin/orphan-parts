#!/usr/bin/env bash
# release-notes.sh <version> [--repo <owner/name>] [--previous <tag>]: the notes of one release,
# assembled from what the repository already records, written to standard output.
#
#   1. the changelog section for the version, as written by hand (required);
#   2. the pull requests merged since the previous release, from the merge commits;
#   3. the compare link between the two releases;
#   4. the images the release publishes.
#
# The previous release is the highest tag below the version, unless --previous names one; with
# no tag before it, the notes say so and the pull requests are those of the whole history.
# The repository comes from --repo, else the origin remote, else GITHUB_REPOSITORY.
#
# Environment:
#   ROOT   the repository (default: the parent of this script's directory)
set -euo pipefail

root="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
version="${1:-}"
repo=""
previous=""
shift $(( $# > 0 ? 1 : 0 ))
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) repo="${2:?--repo needs a value}"; shift 2 ;;
    --previous) previous="${2:?--previous needs a value}"; shift 2 ;;
    *) printf 'release-notes: unknown argument %s\n' "$1" >&2; exit 2 ;;
  esac
done

fail() { printf 'release-notes: %s\n' "$*" >&2; exit 1; }

semver='(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
[[ "$version" =~ ^${semver}$ ]] || fail "not an x.y.z version: '$version'"

# The changelog section: from its heading to the next one, heading included. The heading is
# the whole version, so 0.2.0 does not read the section of 0.2.01.
heading="^## ${version//./\\.}( |$)"
section="$(awk -v h="$heading" '/^## /{p = ($0 ~ h)} p' "$root/CHANGELOG.md")"
[[ -n "$section" ]] || fail "CHANGELOG.md has no '## $version' section"
grep -q '^- ' <<<"$section" || fail "the '## $version' section of CHANGELOG.md lists nothing"

# The checkout's own origin first: the notes belong to the repository they are run in. The
# workflow variable is the fallback for a checkout without a remote.
if [[ -z "$repo" ]]; then
  origin="$(git -C "$root" config --get remote.origin.url 2>/dev/null || true)"
  repo="${origin%.git}"
  repo="${repo#*github.com[:/]}"
  [[ "$repo" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]] || repo="${GITHUB_REPOSITORY:-}"
fi
[[ "$repo" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]] || fail "no owner/name for the repository; pass --repo"

# The previous release: the highest x.y.z tag that sorts below this version. A grep that
# finds nothing exits 1, which pipefail would turn into a silent exit here; each step says so.
if [[ -z "$previous" ]]; then
  others="$(git -C "$root" tag -l | { grep -E "^${semver}$" || true; } | { grep -vx "$version" || true; })"
  previous="$(printf '%s\n%s\n' "$others" "$version" | grep -v '^$' | sort -V \
    | { grep -B1 -x "$version" || true; } | head -1)"
  [[ "$previous" == "$version" ]] && previous=""
fi

# The range the notes cover: up to the tag when it exists, else up to HEAD.
end="$version"
git -C "$root" rev-parse -q --verify "refs/tags/$version" >/dev/null 2>&1 || end="HEAD"
range="$end"
[[ -n "$previous" ]] && range="$previous..$end"

# Merge commits as the forge writes them: "Merge pull request #N from owner/branch", then the
# pull request's title as the body's first line.
pulls="$(git -C "$root" log --merges --format='%s%x1f%b%x1e' "$range" 2>/dev/null \
  | awk -v RS='\x1e' -F'\x1f' '
      { sub(/^[\n ]+/, "", $1) }
      $1 ~ /^Merge pull request #[0-9]+ / {
        n = $1; sub(/^Merge pull request #/, "", n); sub(/ .*/, "", n)
        title = $2; sub(/\n.*/, "", title); gsub(/^[ \t]+|[ \t]+$/, "", title)
        if (title == "") title = "(no title)"
        printf "- #%s %s\n", n, title
      }')"

printf '%s\n\n' "$section"
printf '### Pull requests\n\n'
if [[ -n "$pulls" ]]; then printf '%s\n\n' "$pulls"; else printf '(none merged as pull requests)\n\n'; fi
printf '### Compare\n\n'
if [[ -n "$previous" ]]; then
  printf 'https://github.com/%s/compare/%s...%s\n\n' "$repo" "$previous" "$version"
else
  printf 'The first release; nothing before it to compare with.\n\n'
fi
printf '### Images\n\n'
printf -- '- `ghcr.io/%s/backend:%s`\n' "$repo" "$version"
printf -- '- `ghcr.io/%s/frontend:%s`\n' "$repo" "$version"
