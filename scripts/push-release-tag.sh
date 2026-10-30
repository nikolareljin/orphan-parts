#!/usr/bin/env bash
# push-release-tag.sh <tag> <commit>: tag the release's merge commit and push the tag.
#
# When the repository's tag ruleset refuses the push (GH013, a rule violation: the job token
# may not create tags), say exactly what an admin runs instead, in the job summary when there
# is one ($GITHUB_STEP_SUMMARY) and as an error annotation; the admin's tag push then starts the
# release workflow through its own tag trigger. Any other failure (the network, a tag created
# in the meantime) fails with git's own message and nothing else.
#
# Exit code: 0 pushed, 1 refused or failed. GIT names the git command (tests point it at a
# stand-in).
set -euo pipefail

tag="${1:?usage: push-release-tag.sh <tag> <commit>}"
sha="${2:?usage: push-release-tag.sh <tag> <commit>}"
[[ "$tag" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "push-release-tag: $tag is not x.y.z" >&2; exit 1; }
[[ "$sha" =~ ^[0-9a-f]{7,40}$ ]] || { echo "push-release-tag: $sha is not a commit id" >&2; exit 1; }
read -r -a git_cmd <<<"${GIT:-git}"

"${git_cmd[@]}" tag "$tag" "$sha"
err="$(mktemp)"
trap 'rm -f -- "$err"' EXIT
if "${git_cmd[@]}" push origin "refs/tags/$tag" 2>"$err"; then
  echo "push-release-tag: $tag pushed on $sha"
  exit 0
fi
cat "$err" >&2

if ! grep -qE 'GH013|rule violation' "$err"; then
  echo "push-release-tag: the push of $tag failed (above); not a ruleset refusal" >&2
  exit 1
fi

command="git fetch origin && git tag $tag $sha && git push origin $tag"
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "## The tag $tag was not pushed"
    echo
    echo "The repository's tag ruleset refuses tag creation by the workflow token."
    echo "An admin pushes it, and the release workflow runs from that push:"
    echo
    echo '```bash'
    echo "$command"
    echo '```'
    echo
    echo "Or give tag creation a ruleset of its own with GitHub Actions as a bypass actor,"
    echo "keeping updates and deletions admin-only."
  } >> "$GITHUB_STEP_SUMMARY"
fi
echo "::error title=tag not pushed::the tag ruleset refused the workflow token; an admin runs: $command"
exit 1
