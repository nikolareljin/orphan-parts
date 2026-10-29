#!/usr/bin/env bash
# release-tag.sh: the version a release branch names, refused when anything is off.

_release_tag="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/release-tag.sh"

# A throwaway repository with every manifest at the given version and one commit to tag.
_release_repo() {
  local dir="$1" version="$2"
  mkdir -p "$dir/backend/app" "$dir/frontend"
  printf '[project]\nname = "x"\nversion = "%s"\n' "$version" > "$dir/backend/pyproject.toml"
  printf '__version__ = "%s"\n' "$version" > "$dir/backend/app/__init__.py"
  printf '{\n  "name": "x",\n  "version": "%s"\n}\n' "$version" > "$dir/frontend/package.json"
  printf '# Changelog\n\n## Unreleased\n\n## %s - 2026-01-01\n\n### Added\n- x\n' "$version" > "$dir/CHANGELOG.md"
  printf '%s\n' "$version" > "$dir/VERSION"
  git -C "$dir" init -q
  git -C "$dir" -c user.name=test -c user.email=test@example.invalid commit -q --allow-empty -m "x"
}

_release_run() {
  ROOT="$1" bash "$_release_tag" "$2" 2>/dev/null
}

test_release_branch_prints_its_version() {
  local dir
  dir="$(mktemp -d)"
  _release_repo "$dir" 0.2.0
  assert_eq "$(_release_run "$dir" release/0.2.0)" "0.2.0"
  rm -rf "$dir"
}

test_other_branch_names_are_refused() {
  local dir
  dir="$(mktemp -d)"
  _release_repo "$dir" 0.2.0
  assert_false _release_run "$dir" feat/topic
  assert_false _release_run "$dir" release/v0.2.0
  assert_false _release_run "$dir" release/0.2
  assert_false _release_run "$dir" release/0.2.0.1
  assert_false _release_run "$dir" release/01.2.0
  assert_false _release_run "$dir" "release/0.2.0 "
  assert_false _release_run "$dir" ""
  rm -rf "$dir"
}

test_manifests_and_changelog_must_carry_the_version() {
  local dir
  dir="$(mktemp -d)"
  _release_repo "$dir" 0.2.0
  assert_false _release_run "$dir" release/0.3.0
  printf '__version__ = "0.2.1"\n' > "$dir/backend/app/__init__.py"
  assert_false _release_run "$dir" release/0.2.0
  printf '__version__ = "0.2.0"\n' > "$dir/backend/app/__init__.py"
  printf '# Changelog\n\n## Unreleased\n\n### Added\n- x\n' > "$dir/CHANGELOG.md"
  assert_false _release_run "$dir" release/0.2.0
  # a dot in the version is a dot, and the heading is the whole version
  printf '# Changelog\n\n## 0x2y0 - 2026-01-01\n\n## 0.2.0.1 - 2026-01-01\n' > "$dir/CHANGELOG.md"
  assert_false _release_run "$dir" release/0.2.0
  printf '# Changelog\n\n## 0.2.0\n' > "$dir/CHANGELOG.md"
  assert_eq "$(_release_run "$dir" release/0.2.0)" "0.2.0"
  rm -f "$dir/frontend/package.json"; : > "$dir/frontend/package.json"
  assert_false _release_run "$dir" release/0.2.0
  rm -rf "$dir"
}

test_the_version_file_must_agree_when_it_exists() {
  local dir
  dir="$(mktemp -d)"
  _release_repo "$dir" 0.2.0
  printf '0.2.1\n' > "$dir/VERSION"
  assert_false _release_run "$dir" release/0.2.0
  printf ' 0.2.0 \n' > "$dir/VERSION"
  assert_eq "$(_release_run "$dir" release/0.2.0)" "0.2.0"
  rm "$dir/VERSION"
  assert_eq "$(_release_run "$dir" release/0.2.0)" "0.2.0"
  rm -rf "$dir"
}

test_an_existing_tag_is_never_moved() {
  local dir
  dir="$(mktemp -d)"
  _release_repo "$dir" 0.2.0
  git -C "$dir" tag 0.2.0
  assert_false _release_run "$dir" release/0.2.0
  assert_eq "$(ROOT="$dir" bash "$_release_tag" release/0.2.0 2>&1 || true)" \
    "release-tag: tag 0.2.0 exists already; existing tags are never moved"
  rm -rf "$dir"
}
