#!/usr/bin/env bash
# deploy-hosted.sh secret|backend|web|all: the hosted demo, the backend on Modal and the web
# app on Cloudflare Pages, from settings in the environment. The deploy workflow runs it with
# the repository's secrets and variables; from a shell it runs the same with this machine's
# modal and wrangler logins.
#
#   secret    writes the Modal secret orphan-parts from the environment (every field, replaced;
#             a value holding a single quote, a backslash or a newline is refused, since the
#             dotenv reader cannot carry those; anything else is kept as it is)
#   backend   deploys deploy/modal_app.py, reads the URL off the output, stops the running
#             containers of the deployed app orphan-parts (a warm container keeps the secret
#             it started with; the next one reads the secret as it is now) and waits for
#             /readyz to answer ok with the key answering (a key that failed its probe fails
#             the step)
#   web       builds the web app against the backend's URL and publishes frontend/dist to Pages
#             (refused while a frontend/.env* exists, since Vite would bake its VITE_ names into
#             the public bundle, and when the build leaves one in dist)
#   all       secret, backend, web, in that order; web takes the URL backend found
#
# Environment:
#   WEB_ORIGIN           the origin browsers use: https://<project>.pages.dev, or a custom
#                        domain attached to the project; it becomes the backend's CORS_ORIGINS
#   PAGES_PROJECT        the Pages project (default orphan-parts); created when it is missing
#   API_URL              the backend's URL for the web build; empty = what backend printed
#   MODEL_API_KEY_DEMO   the key the host uses; empty = recorded answers, nothing spent
#   DEMO_ACCESS_CODE     the access code; empty = an open demo
#   SPEND_CAP_USD        the ledger's cap on the host (default 20)
#   OPL_FAKE_API         1 = recorded answers even with a key (default 1)
#   PICTURE_ENABLED      1 = the item dialog may draw a picture with Muse Image (default 0;
#                        only 0 or 1)
#   OPL_MIN_CONTAINERS   read by deploy/modal_app.py at deploy time: 1 keeps the container warm
#   MODAL_TOKEN_ID, MODAL_TOKEN_SECRET          the modal command's login (or ~/.modal.toml)
#   CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID wrangler's login
#   MODAL, WRANGLER, NPM, CURL, PYTHON   the commands, options included (tests point them at
#                        stand-ins; PYTHON reads modal's JSON, default python3)
#   READY_TRIES, READY_WAIT      how long backend waits for the old containers to go and for
#                        /readyz (default 12 times 5 s each)
#   GITHUB_OUTPUT        when set, api_url= and web_url= lines are appended to it
#   ROOT                 the repository (default: the parent of this script's directory)
set -euo pipefail

root="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
target="${1:-all}"
case "$target" in
  secret|backend|web|all) ;;
  *) printf 'deploy-hosted: unknown target %s (secret, backend, web, all)\n' "$target" >&2; exit 2 ;;
esac

fail() { printf 'deploy-hosted: %s\n' "$*" >&2; exit 1; }
# untraced CMD...: CMD with xtrace off, on again after if it was on, so bash -x never prints a
# secret (the same helper as scripts/lib/env.sh; this script stands alone)
untraced() {
  local _untraced_x=0 _untraced_rc=0
  [[ $- == *x* ]] && _untraced_x=1
  { set +x; } 2>/dev/null
  # not "|| rc=$?": that would turn errexit off inside CMD; under set -e a failure ends the
  # script here, as it would have without the wrapper
  "$@"; _untraced_rc=$?
  [[ $_untraced_x -eq 0 ]] || set -x
  return $_untraced_rc
}
say() { printf 'deploy-hosted: %s\n' "$*"; }
origin_ok() { [[ "$1" =~ ^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?$ ]]; }

# the commands may carry options; split on spaces, as a shell would
read -r -a modal_cmd <<<"${MODAL:-modal}"
read -r -a wrangler_cmd <<<"${WRANGLER:-npx --yes wrangler@4}"
read -r -a npm_cmd <<<"${NPM:-npm}"
read -r -a curl_cmd <<<"${CURL:-curl}"
read -r -a python_cmd <<<"${PYTHON:-python3}"
# the name in deploy/modal_app.py (modal.App("orphan-parts")), the secret's name too
app_name="orphan-parts"
project="${PAGES_PROJECT:-orphan-parts}"
api_url="${API_URL:-}"
# the dotenv the secret step writes holds the key and the code: gone when the script ends,
# however it ends (a failure, an interrupt, a normal end)
secret_file=""
trap '[[ -n "$secret_file" ]] && rm -f -- "$secret_file"' EXIT

need_modal() {
  command -v "${modal_cmd[0]}" >/dev/null 2>&1 \
    || fail "the modal command is not installed (pip install modal python-dotenv); see docs/operations/deployment.md"
}

# Untraced as a whole: it reads the key and the code and writes them into the dotenv.
step_secret() { untraced _step_secret; }
_step_secret() {
  need_modal
  origin_ok "${WEB_ORIGIN:-}" || fail "secret: WEB_ORIGIN must be an https origin (https://<project>.pages.dev)"
  local name value
  for name in MODEL_API_KEY_DEMO DEMO_ACCESS_CODE SPEND_CAP_USD OPL_FAKE_API; do
    value="${!name:-}"
    [[ "$value" != *[\\\']* && "$value" != *$'\n'* ]] \
      || fail "secret: $name holds a single quote, a backslash or a newline, which the dotenv cannot carry"
  done
  [[ "${PICTURE_ENABLED:-0}" =~ ^[01]$ ]] \
    || fail "secret: PICTURE_ENABLED must be 0 or 1, not ${PICTURE_ENABLED}"
  local file
  file="$(mktemp)" || fail "secret: no temporary file"
  secret_file="$file"
  chmod 600 "$file"
  # single quotes: the dotenv reader keeps the value as it is (no $expansion, no escapes)
  {
    printf "MODEL_API_KEY='%s'\n" "${MODEL_API_KEY_DEMO:-}"
    printf "DEMO_ACCESS_CODE='%s'\n" "${DEMO_ACCESS_CODE:-}"
    printf "SPEND_CAP_USD='%s'\n" "${SPEND_CAP_USD:-20}"
    printf "OPL_FAKE_API='%s'\n" "${OPL_FAKE_API:-1}"
    printf "PICTURE_ENABLED='%s'\n" "${PICTURE_ENABLED:-0}"
    printf "CORS_ORIGINS='%s'\n" "$WEB_ORIGIN"
    printf "DEMO_COOKIE_SECURE='1'\n"
    # Modal's proxy forwards the visitor's address: counted per visitor, not per proxy
    printf "DEMO_TRUST_PROXY='1'\n"
    # the host serves no API docs: /docs and /openapi.json answer 404 there
    printf "API_DOCS='0'\n"
  } > "$file"
  local ok=0
  "${modal_cmd[@]}" secret create orphan-parts --from-dotenv "$file" --force && ok=1
  [[ -f "$file" ]] && rm -f -- "$file"
  [[ "$ok" = 1 ]] || fail "secret: modal secret create failed"
  local key="empty" code="empty"
  [[ -n "${MODEL_API_KEY_DEMO:-}" ]] && key="set"
  [[ -n "${DEMO_ACCESS_CODE:-}" ]] && code="set"
  say "secret: orphan-parts written: key $key, code $code, OPL_FAKE_API=${OPL_FAKE_API:-1}, PICTURE_ENABLED=${PICTURE_ENABLED:-0}, cap ${SPEND_CAP_USD:-20}, origin $WEB_ORIGIN"
}

step_backend() {
  need_modal
  [[ -f "$root/deploy/modal_app.py" ]] || fail "backend: no deploy/modal_app.py in this tree"
  say "backend: modal deploy from $root (OPL_MIN_CONTAINERS=${OPL_MIN_CONTAINERS:-1})"
  local out url
  out="$("${modal_cmd[@]}" deploy "$root/deploy/modal_app.py" 2>&1)" \
    || { printf '%s\n' "$out" >&2; fail "backend: the deploy failed"; }
  printf '%s\n' "$out" | tail -5
  url="$(printf '%s\n' "$out" | grep -oE 'https://[A-Za-z0-9.-]+\.modal\.run' | tail -1 || true)"
  [[ -n "$url" ]] || fail "backend: no .modal.run URL in the deploy output"
  restart_containers
  local ready="" tries="${READY_TRIES:-12}" wait="${READY_WAIT:-5}" i
  for ((i = 1; i <= tries; i++)); do
    ready="$("${curl_cmd[@]}" -fsS -m 20 "$url/readyz" 2>/dev/null)" && break
    ready=""
    sleep "$wait"
  done
  [[ -n "$ready" ]] || fail "backend: $url/readyz did not answer after $tries tries"
  printf '%s\n' "$ready" | grep -q '"status":"ok"' || fail "backend: readyz is not ok: $ready"
  # the key in the secret must answer: a service on recorded answers because it did not
  # is a deploy to fix, not one to build the web app against
  printf '%s\n' "$ready" | grep -q '"model_api":"fixture (key failed)"' \
    && fail "backend: the key did not answer the startup probe: $ready"
  say "backend: $url is up: $ready"
  api_url="$url"
  [[ -n "${GITHUB_OUTPUT:-}" ]] && printf 'api_url=%s\n' "$url" >> "$GITHUB_OUTPUT"
  return 0
}

# modal_json app NAME | container APP_ID: from modal's --json table on stdin, the id of the
# deployed app named NAME, or the ids of the containers of APP_ID, one per line. The keys are
# taken in either spelling modal has used ("App ID" or app_id).
modal_json() {
  "${python_cmd[@]}" -c '
import json, re, sys
kind, want = sys.argv[1], sys.argv[2]
def norm(row):
    return {re.sub(r"[^a-z0-9]+", "_", str(k).lower()).strip("_"): str(v) for k, v in row.items()}
rows = [norm(r) for r in json.load(sys.stdin) if isinstance(r, dict)]
for r in rows:
    if kind == "app" and r.get("description") == want and r.get("state") == "deployed":
        print(r.get("app_id", ""))
    elif kind == "container" and r.get("app_id") == want and r.get("container_id"):
        print(r["container_id"])
' "$1" "$2"
}

# restart_containers: a container that is running keeps the secret it started with, and with
# OPL_MIN_CONTAINERS=1 one always is; each running container of the deployed app is stopped
# (an ephemeral run of the same app, a load or a keys command, is left alone) and the step
# waits until they are gone, so the one that answers /readyz next started with the secret as
# it is now. No container running (scaled to zero) is nothing to do.
restart_containers() {
  local out app_id ids id left tries="${READY_TRIES:-12}" wait="${READY_WAIT:-5}" i
  out="$("${modal_cmd[@]}" app list --json)" || fail "backend: modal app list failed"
  app_id="$(printf '%s' "$out" | modal_json app "$app_name" | head -1)" \
    || fail "backend: modal app list did not answer in JSON"
  [[ -n "$app_id" ]] || fail "backend: no deployed app $app_name in modal app list"
  out="$("${modal_cmd[@]}" container list --app-id "$app_id" --json)" || fail "backend: modal container list failed"
  ids="$(printf '%s' "$out" | modal_json container "$app_id")" \
    || fail "backend: modal container list did not answer in JSON"
  if [[ -z "$ids" ]]; then
    say "backend: no container of $app_name running; the next one starts with the current secret"
    return 0
  fi
  while IFS= read -r id; do
    say "backend: stopping container $id so the next one reads the current secret"
    "${modal_cmd[@]}" container stop --yes "$id" >/dev/null || fail "backend: modal container stop $id failed"
  done <<<"$ids"
  for ((i = 1; i <= tries; i++)); do
    out="$("${modal_cmd[@]}" container list --app-id "$app_id" --json 2>/dev/null)" || out="[]"
    left="$(printf '%s' "$out" | modal_json container "$app_id" | grep -Fxf <(printf '%s\n' "$ids") || true)"
    [[ -z "$left" ]] && { say "backend: the old containers are gone"; return 0; }
    sleep "$wait"
  done
  fail "backend: container(s) ${left//$'\n'/, } still running after $tries tries"
}

step_web() {
  origin_ok "${WEB_ORIGIN:-}" || fail "web: WEB_ORIGIN must be an https origin (https://<project>.pages.dev)"
  origin_ok "$api_url" || fail "web: API_URL must be the backend's https URL (the backend step prints it)"
  [[ "$project" =~ ^[a-z0-9-]+$ ]] || fail "web: PAGES_PROJECT must be lowercase letters, digits and dashes"
  local pages="https://$project.pages.dev"
  # the origin browsers use must be the one the backend will allow: the project's own, or a
  # custom domain attached to the project
  if [[ "$WEB_ORIGIN" == *.pages.dev && "$WEB_ORIGIN" != "$pages" ]]; then
    fail "web: WEB_ORIGIN is $WEB_ORIGIN but the project $project publishes at $pages"
  fi
  # Vite reads frontend/.env, .env.local, .env.production and .env.production.local and bakes
  # every VITE_ name in them into the public bundle: one lying there is refused, not built
  local stray
  if stray="$(cd "$root/frontend" && compgen -G '.env*')"; then
    fail "web: frontend/${stray//$'\n'/, frontend/} would be read by Vite and its VITE_ names baked into the public bundle; remove it first"
  fi
  say "web: building the web app against $api_url"
  (cd "$root/frontend" && VITE_API_URL="$api_url" "${npm_cmd[@]}" ci && VITE_API_URL="$api_url" "${npm_cmd[@]}" run build)
  [[ -d "$root/frontend/dist" ]] || fail "web: no frontend/dist after the build"
  # whatever the build or a tool left there: nothing named .env goes up with the bundle
  stray="$(find "$root/frontend/dist" -name '.env*' 2>/dev/null)"
  [[ -z "$stray" ]] || fail "web: frontend/dist holds ${stray//$'\n'/, }; nothing is uploaded"
  local projects
  projects="$("${wrangler_cmd[@]}" pages project list 2>/dev/null || true)"
  if ! grep -qE "(^|[[:space:]|])$project([[:space:]|]|$)" <<<"$projects"; then
    say "web: creating the Pages project $project"
    "${wrangler_cmd[@]}" pages project create "$project" --production-branch main
  fi
  "${wrangler_cmd[@]}" pages deploy "$root/frontend/dist" --project-name "$project" --branch main
  say "web: published at $pages; browsers use $WEB_ORIGIN"
  [[ -n "${GITHUB_OUTPUT:-}" ]] && printf 'web_url=%s\n' "$WEB_ORIGIN" >> "$GITHUB_OUTPUT"
  return 0
}

case "$target" in
  secret) step_secret ;;
  backend) step_backend ;;
  web) step_web ;;
  all) step_secret; step_backend; step_web ;;
esac
