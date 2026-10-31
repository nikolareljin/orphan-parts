#!/usr/bin/env bash
# ci-changes.sh: which slow CI jobs a set of changed files needs.

_ci_changes="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ci-changes.sh"

_ci_changes_for() { printf '%s\n' "$@" | bash "$_ci_changes" | tr '\n' ' '; }

test_ci_changes_docs_only_runs_neither() {
  assert_eq "$(_ci_changes_for docs/guides/android.md mkdocs.yml README.md overrides/main.html)" "backend=false web=false "
}

test_ci_changes_android_only_runs_neither() {
  assert_eq "$(_ci_changes_for android/app/build.gradle.kts scripts/android.sh)" "backend=false web=false "
}

test_ci_changes_frontend_sources_run_web_only() {
  assert_eq "$(_ci_changes_for frontend/src/App.tsx e2e/tests/build.spec.ts docs/index.md)" "backend=false web=true "
}

test_ci_changes_frontend_dockerfile_runs_both() {
  assert_eq "$(_ci_changes_for frontend/Dockerfile)" "backend=true web=true "
}

test_ci_changes_backend_runs_both() {
  assert_eq "$(_ci_changes_for backend/app/main.py)" "backend=true web=true "
}

test_ci_changes_workflow_or_unknown_runs_both() {
  assert_eq "$(_ci_changes_for .github/workflows/ci.yml)" "backend=true web=true "
  assert_eq "$(_ci_changes_for docs/assets/logo.svg VERSION)" "backend=true web=true "
}

test_ci_changes_empty_runs_both() {
  assert_eq "$(printf '' | bash "$_ci_changes" | tr '\n' ' ')" "backend=true web=true "
}

test_ci_changes_rejects_one_argument() {
  assert_false bash "$_ci_changes" HEAD
}

test_ci_changes_markdown_outside_the_root_is_data() {
  # the demo set's listings and the live check's README are read by tests: they run everything
  assert_eq "$(_ci_changes_for demo/listings/frappe-agitator.md)" "backend=true web=true "
  assert_eq "$(_ci_changes_for livecheck/README.md JUDGES.md)" "backend=true web=true "
  assert_eq "$(_ci_changes_for JUDGES.md CHANGELOG.md)" "backend=false web=false "
}
