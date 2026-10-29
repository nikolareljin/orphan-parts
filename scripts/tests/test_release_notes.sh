#!/usr/bin/env bash
# release-notes.sh: the changelog section, the pull requests since the last release, the
# compare link and the images, from a throwaway repository.

_notes="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/release-notes.sh"

_notes_git() { git -c user.name=test -c user.email=test@example.invalid "$@"; }

# Only a directory mktemp made is removed: never an empty path, never anything else.
_notes_cleanup() { [[ -n "${1:-}" && -d "$1" && "$1" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$1"; }

# A repository with two releases: 0.1.0 tagged, then two pull requests merged, then 0.2.0.
_notes_repo() {
  local dir="$1"
  mkdir -p "$dir"
  git -C "$dir" init -q -b main
  git -C "$dir" remote add origin git@github.com:someone/thing.git
  printf '# Changelog\n\n## Unreleased\n\n## 0.2.0 - 2026-02-01\n\n### Added\n- two\n\n## 0.1.0 - 2026-01-01\n\n### Added\n- one\n' > "$dir/CHANGELOG.md"
  _notes_git -C "$dir" add . && _notes_git -C "$dir" commit -q -m "chore: release 0.1.0"
  git -C "$dir" tag 0.1.0
  _notes_merge "$dir" feat/x "$(printf 'Merge pull request #7 from someone/feat/x\n\nfeat(x): the first thing')"
  _notes_merge "$dir" fix/y "$(printf 'Merge pull request #9 from someone/fix/y\n\n  fix(y): the second thing  ')"
  _notes_merge "$dir" feat/z "$(printf 'Merge branch feat/z\n\nnot a pull request')"
}

# A real merge commit, the way the forge makes one: a branch with a commit, merged with --no-ff.
_notes_merge() {
  local dir="$1" branch="$2" message="$3"
  git -C "$dir" switch -q -c "$branch"
  _notes_git -C "$dir" commit -q --allow-empty -m "feat: on $branch"
  git -C "$dir" switch -q main
  _notes_git -C "$dir" merge -q --no-ff -m "$message" "$branch"
}

test_notes_hold_the_four_parts() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _notes_repo "$dir"
  out="$(ROOT="$dir" bash "$_notes" 0.2.0)"
  assert_true grep -q '^## 0.2.0 - 2026-02-01' <<<"$out"
  assert_true grep -q '^- two$' <<<"$out"
  assert_false grep -q '^- one$' <<<"$out"
  assert_true grep -q '^- #7 feat(x): the first thing$' <<<"$out"
  assert_true grep -q '^- #9 fix(y): the second thing$' <<<"$out"
  assert_false grep -q 'Merge branch' <<<"$out"
  assert_true grep -q '^https://github.com/someone/thing/compare/0.1.0...0.2.0$' <<<"$out"
  assert_true grep -q 'ghcr.io/someone/thing/backend:0.2.0' <<<"$out"
  assert_true grep -q 'ghcr.io/someone/thing/frontend:0.2.0' <<<"$out"
  _notes_cleanup "$dir"
}

test_the_first_release_has_nothing_to_compare_with() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _notes_repo "$dir"
  out="$(ROOT="$dir" bash "$_notes" 0.1.0)"
  assert_true grep -q '^- one$' <<<"$out"
  assert_true grep -q 'The first release' <<<"$out"
  assert_false grep -q '/compare/' <<<"$out"
  _notes_cleanup "$dir"
}

test_the_previous_release_can_be_named_and_the_repository_given() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _notes_repo "$dir"
  git -C "$dir" remote remove origin
  out="$(GITHUB_REPOSITORY= ROOT="$dir" bash "$_notes" 0.2.0 --repo other/name --previous 0.1.0)"
  assert_true grep -q '^https://github.com/other/name/compare/0.1.0...0.2.0$' <<<"$out"
  assert_false env GITHUB_REPOSITORY= ROOT="$dir" bash "$_notes" 0.2.0 2>/dev/null   # no origin, no --repo
  # the workflow's variable serves a checkout without a remote, and never outranks the origin
  out="$(GITHUB_REPOSITORY=ci/fallback ROOT="$dir" bash "$_notes" 0.2.0)"
  assert_true grep -q 'ghcr.io/ci/fallback/backend:0.2.0' <<<"$out"
  git -C "$dir" remote add origin git@github.com:someone/thing.git
  out="$(GITHUB_REPOSITORY=ci/fallback ROOT="$dir" bash "$_notes" 0.2.0)"
  assert_true grep -q 'ghcr.io/someone/thing/backend:0.2.0' <<<"$out"
  _notes_cleanup "$dir"
}

test_notes_refuse_a_missing_or_empty_section_and_a_bad_version() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  _notes_repo "$dir"
  assert_false ROOT="$dir" bash "$_notes" 0.3.0 2>/dev/null
  assert_false ROOT="$dir" bash "$_notes" v0.2.0 2>/dev/null
  printf '# Changelog\n\n## 0.2.0 - 2026-02-01\n\n### Added\n' > "$dir/CHANGELOG.md"
  assert_false ROOT="$dir" bash "$_notes" 0.2.0 2>/dev/null
  # the heading is the whole version: 0.2.01 is not 0.2.0
  printf '# Changelog\n\n## 0.2.01 - 2026-02-01\n\n### Added\n- not it\n' > "$dir/CHANGELOG.md"
  assert_false ROOT="$dir" bash "$_notes" 0.2.0 2>/dev/null
  _notes_cleanup "$dir"
}
