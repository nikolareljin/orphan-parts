#!/usr/bin/env bash
# release.sh: every check before a tag is created, against a throwaway repository with an
# origin of its own; the tag itself is created and pushed only when every check holds.

_release="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/release.sh"
_release_tag_script="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/release-tag.sh"

_rel_git() { git -c user.name=test -c user.email=test@example.invalid "$@"; }

# Only a directory mktemp made is removed: never an empty path, never anything else.
_rel_cleanup() { [[ -n "${1:-}" && -d "$1" && "$1" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$1"; }

# A clone of a bare origin, with every manifest at the version and the scripts in place.
_rel_repo() {
  local dir="$1" version="$2" bare="$1.origin"
  git init -q --bare -b main "$bare"
  git clone -q "$bare" "$dir" 2>/dev/null
  mkdir -p "$dir/backend/app" "$dir/frontend" "$dir/scripts"
  printf '[project]\nname = "x"\nversion = "%s"\n' "$version" > "$dir/backend/pyproject.toml"
  printf '__version__ = "%s"\n' "$version" > "$dir/backend/app/__init__.py"
  printf '{\n  "name": "x",\n  "version": "%s"\n}\n' "$version" > "$dir/frontend/package.json"
  printf '# Changelog\n\n## Unreleased\n\n## %s - 2026-01-01\n\n### Added\n- x\n' "$version" > "$dir/CHANGELOG.md"
  printf '%s\n' "$version" > "$dir/VERSION"
  cp "$_release_tag_script" "$dir/scripts/release-tag.sh"
  _rel_git -C "$dir" add . && _rel_git -C "$dir" commit -q -m "chore: release $version"
  _rel_git -C "$dir" push -q origin main
}

test_a_dry_run_passes_every_check_and_tags_nothing() {
  local base dir out
  base="$(mktemp -d)" || { assert_true false; return; }
  dir="$base/repo"
  _rel_repo "$dir" 0.2.0
  out="$(ROOT="$dir" bash "$_release" --dry-run 2>&1)"
  assert_true grep -q 'version 0.2.0, on main' <<<"$out"
  assert_true grep -q 'dry run: nothing tagged' <<<"$out"
  assert_eq "$(git -C "$dir" tag -l)" ""
  _rel_cleanup "$base"
}

test_a_release_tags_head_and_pushes_the_tag() {
  local base dir
  base="$(mktemp -d)" || { assert_true false; return; }
  dir="$base/repo"
  _rel_repo "$dir" 0.2.0
  assert_true env ROOT="$dir" bash "$_release"
  assert_eq "$(git -C "$dir" tag -l)" "0.2.0"
  assert_eq "$(git -C "$dir.origin" tag -l)" "0.2.0"
  assert_eq "$(git -C "$dir" rev-parse 0.2.0^{commit})" "$(git -C "$dir" rev-parse HEAD)"
  # a second time: the tag exists, here and on origin
  assert_false env ROOT="$dir" bash "$_release" --dry-run 2>/dev/null
  _rel_cleanup "$base"
}

test_a_release_refuses_a_branch_a_dirty_tree_and_a_stale_main() {
  local base dir
  base="$(mktemp -d)" || { assert_true false; return; }
  dir="$base/repo"
  _rel_repo "$dir" 0.2.0
  git -C "$dir" switch -q -c feat/x
  assert_false env ROOT="$dir" bash "$_release" --dry-run 2>/dev/null
  git -C "$dir" switch -q main
  echo x > "$dir/extra.txt"
  assert_false env ROOT="$dir" bash "$_release" --dry-run 2>/dev/null
  rm "$dir/extra.txt"
  _rel_git -C "$dir" commit -q --allow-empty -m "chore: not pushed"
  assert_false env ROOT="$dir" bash "$_release" --dry-run 2>/dev/null
  _rel_git -C "$dir" push -q origin main
  assert_true env ROOT="$dir" bash "$_release" --dry-run
  _rel_cleanup "$base"
}

test_a_release_refuses_a_version_the_manifests_do_not_carry() {
  local base dir
  base="$(mktemp -d)" || { assert_true false; return; }
  dir="$base/repo"
  _rel_repo "$dir" 0.2.0
  printf '0.3.0\n' > "$dir/VERSION"
  _rel_git -C "$dir" commit -q -am "chore: bump VERSION only" && _rel_git -C "$dir" push -q origin main
  assert_false env ROOT="$dir" bash "$_release" --dry-run 2>/dev/null
  rm "$dir/VERSION"
  _rel_git -C "$dir" commit -q -am "chore: no VERSION" && _rel_git -C "$dir" push -q origin main
  assert_false env ROOT="$dir" bash "$_release" --dry-run 2>/dev/null
  _rel_cleanup "$base"
}
