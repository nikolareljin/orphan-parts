#!/usr/bin/env bash
# push-release-tag.sh: the tag pushed, a ruleset refusal turned into the admin's command (in
# the job summary and an annotation), any other failure left as git said it.

_tagger="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/push-release-tag.sh"

# a git stand-in: records what it was told; the push answers from a file
_tagger_git() {
  local dir="$1"
  cat > "$dir/git" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$dir/git.log"
if [[ "\$1" == push ]]; then
  [[ -f "$dir/push.err" ]] || exit 0
  cat "$dir/push.err" >&2
  exit 1
fi
exit 0
STUB
  chmod +x "$dir/git"
}

test_push_release_tag_pushes_and_explains_a_refusal() {
  local dir out sha=5580413b6fc7fe2acba58d93585a1ea1a7a5eecd
  dir="$(mktemp -d)" || { assert_true false; return; }
  _tagger_git "$dir"
  out="$(GIT="$dir/git" GITHUB_STEP_SUMMARY="$dir/summary" bash "$_tagger" 0.2.0 "$sha")" && assert_true true || assert_true false
  assert_eq "$(tr '\n' '|' < "$dir/git.log")" "tag 0.2.0 $sha|push origin refs/tags/0.2.0|"
  assert_true grep -q 'pushed' <<<"$out"
  assert_false test -s "$dir/summary"
  # the ruleset refuses: the admin's command in the summary and the annotation
  printf 'remote: error: GH013: Repository rule violations found for refs/tags/0.2.0.\n' > "$dir/push.err"
  out="$(GIT="$dir/git" GITHUB_STEP_SUMMARY="$dir/summary" bash "$_tagger" 0.2.0 "$sha" 2>/dev/null)" && assert_true false || assert_true true
  assert_true grep -qF "git fetch origin && git tag 0.2.0 $sha && git push origin 0.2.0" "$dir/summary"
  assert_true grep -q '^::error title=tag not pushed::' <<<"$out"
  # any other failure: git's message only, no admin advice
  rm -f "$dir/summary"
  printf 'fatal: unable to access the remote: Could not resolve host\n' > "$dir/push.err"
  out="$(GIT="$dir/git" GITHUB_STEP_SUMMARY="$dir/summary" bash "$_tagger" 0.2.0 "$sha" 2>/dev/null)" && assert_true false || assert_true true
  assert_false test -s "$dir/summary"
  assert_false grep -q '::error title=tag not pushed' <<<"$out"
  # what it will not tag
  assert_false bash "$_tagger" v0.2.0 "$sha" 2>/dev/null
  assert_false bash "$_tagger" 0.2.0 'not-a-sha' 2>/dev/null
  [[ "$dir" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$dir"
}
