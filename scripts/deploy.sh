#!/usr/bin/env bash
# deploy.sh [web|android|modal|hosted|all] [--version <x.y.z>]: put a published release where people use it.
#
#   modal    the backend on Modal from this tree (modal deploy deploy/modal_app.py) with this
#            machine's login; the secret and the web app are left as they are
#   hosted   the whole hosted demo from settings in the environment, the same steps the deploy
#            workflow runs: deploy-hosted.sh [secret|backend|web|all]
#   web      on the host named by DEPLOY_HOST (user@host), in DEPLOY_PATH, pull the release's
#            images and start them: the same two compose files as here, with TAG set
#   android  build the release APK when an Android app is in this tree; the upload to the
#            store is a later step, described in docs/operations/deployment.md
#   all      both (the default); a part that is not set up says so and is skipped
#
# The version is VERSION unless --version is given. Nothing here builds images: the release
# workflow did that when the tag was pushed, and the host pulls them.
#
# Environment (from .env, or the shell):
#   DEPLOY_HOST      user@host the web app runs on; empty = web deploy not set up
#   DEPLOY_PATH      absolute directory on the host holding the two compose files and .env
#   DEPLOY_SSH       the ssh command, options included (default: ssh); tests point it at a
#                    stand-in, the workflow adds its key and host-key options
#   IMAGE_PREFIX     where the images are (default: ghcr.io/<owner>/<name> from origin)
#   ROOT             the repository (default: the parent of this script's directory)
set -euo pipefail

root="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
if [[ "${1:-}" == hosted ]]; then
  shift
  exec bash "$root/scripts/deploy-hosted.sh" "$@"
fi
target="all"
version=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    web|android|modal|all) target="$1"; shift ;;
    --version) version="${2:?--version needs a value}"; shift 2 ;;
    *) printf 'deploy: unknown argument %s\n' "$1" >&2; exit 2 ;;
  esac
done

fail() { printf 'deploy: %s\n' "$*" >&2; exit 1; }
say() { printf 'deploy: %s\n' "$*"; }

# .env is read for the deploy settings only when the shell does not already set them.
if [[ -f "$root/.env" ]]; then
  while IFS= read -r line; do
    key="${line%%=*}"
    value="${line#*=}"   # the first = divides; any later one is part of the value
    value="${value%\"}"; value="${value#\"}"
    [[ -n "${!key:-}" ]] || export "$key=$value"
  done < <(grep -E '^(DEPLOY_HOST|DEPLOY_PATH|IMAGE_PREFIX)=' "$root/.env" || true)
fi

if [[ -z "$version" ]]; then
  [[ -f "$root/VERSION" ]] || fail "no VERSION file and no --version"
  version="$(tr -d '[:space:]' < "$root/VERSION")"
fi
semver='(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
[[ "$version" =~ ^${semver}$ ]] || fail "not an x.y.z version: '$version'"

if [[ -z "${IMAGE_PREFIX:-}" ]]; then
  origin="$(git -C "$root" config --get remote.origin.url 2>/dev/null || true)"
  repo="${origin%.git}"; repo="${repo#*github.com[:/]}"
  [[ "$repo" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]] || fail "no IMAGE_PREFIX and no origin to derive it from"
  IMAGE_PREFIX="ghcr.io/$repo"
fi

deploy_web() {
  if [[ -z "${DEPLOY_HOST:-}" ]]; then
    [[ "$target" == "all" ]] && { say "web: DEPLOY_HOST is not set; skipped"; return 0; }
    fail "web: DEPLOY_HOST is not set (user@host); see docs/operations/deployment.md"
  fi
  [[ -n "${DEPLOY_PATH:-}" ]] || fail "web: DEPLOY_PATH is not set"
  [[ "$DEPLOY_HOST" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$ ]] || fail "web: DEPLOY_HOST must be user@host"
  [[ "$DEPLOY_PATH" =~ ^/[A-Za-z0-9._/-]*$ ]] || fail "web: DEPLOY_PATH must be an absolute path of plain characters"
  # the ssh command may carry options; split on spaces, as a shell would
  local -a ssh_cmd
  read -r -a ssh_cmd <<<"${DEPLOY_SSH:-ssh}"
  # One remote command, every value quoted: the host pulls the release and starts it.
  local remote
  remote="cd $(printf '%q' "$DEPLOY_PATH") && IMAGE_PREFIX=$(printf '%q' "$IMAGE_PREFIX") TAG=$(printf '%q' "$version")"
  remote="$remote docker compose -f docker-compose.yml -f docker-compose.prod.yml pull"
  remote="$remote && IMAGE_PREFIX=$(printf '%q' "$IMAGE_PREFIX") TAG=$(printf '%q' "$version")"
  remote="$remote docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans"
  say "web: $version to $DEPLOY_HOST:$DEPLOY_PATH"
  "${ssh_cmd[@]}" "$DEPLOY_HOST" "$remote"
  say "web: up"
}

deploy_modal() {
  local modal_cmd="${MODAL:-modal}"
  if ! command -v "$modal_cmd" >/dev/null 2>&1; then
    fail "modal: the command is not installed; pipx install modal && modal setup, then again (see docs/operations/deployment.md)"
  fi
  [[ -f "$root/deploy/modal_app.py" ]] || fail "modal: no deploy/modal_app.py in this tree"
  say "modal: deploying the backend from $root"
  local out
  out="$("$modal_cmd" deploy "$root/deploy/modal_app.py" 2>&1)" || { printf '%s\n' "$out" >&2; fail "modal: the deploy failed"; }
  printf '%s\n' "$out" | tail -5
  local url
  url="$(printf '%s\n' "$out" | grep -oE 'https://[A-Za-z0-9.-]+\.modal\.run' | tail -1 || true)"
  [[ -n "$url" ]] && say "modal: the backend answers at $url (put it in the web app's VITE_API_URL and the secret's CORS_ORIGINS)"
  say "modal: the web app on Cloudflare Pages follows main on its own"
}

deploy_android() {
  if [[ ! -f "$root/android/gradlew" ]]; then
    [[ "$target" == "all" ]] && { say "android: no app in this tree yet; skipped"; return 0; }
    fail "android: no app in this tree yet (android/gradlew)"
  fi
  say "android: building the release APK for $version"
  (cd "$root/android" && ./gradlew --quiet assembleRelease)
  local apk
  apk="$(find "$root/android" -path '*/outputs/apk/release/*.apk' | head -1)"
  [[ -n "$apk" ]] || fail "android: no APK under outputs/apk/release after the build"
  say "android: $apk"
  say "android: the store upload is a step for later; the APK above is the artifact"
}

case "$target" in
  web) deploy_web ;;
  android) deploy_android ;;
  modal) deploy_modal ;;
  all) deploy_web; deploy_android ;;
esac
