#!/usr/bin/env bash
# deploy-hosted.sh: the Modal secret written from the environment, the backend deployed and
# checked on /readyz, the web app built against the backend's URL and published to Pages; each
# step with stand-ins for modal, wrangler, npm and curl that record what they were told.

_hosted="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/deploy-hosted.sh"

_hosted_cleanup() { [[ -n "${1:-}" && -d "$1" && "$1" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$1"; }

# A tree with the app file, a frontend directory and the four stand-ins. The modal stand-in
# keeps the dotenv it was given (the secret) and prints a deploy line; wrangler lists the
# project only when the tree has a flag file; npm writes dist on build and records VITE_API_URL;
# curl answers readyz from a file.
_hosted_tree() {
  local dir="$1"
  mkdir -p "$dir/bin" "$dir/deploy" "$dir/frontend"
  printf 'app = 1\n' > "$dir/deploy/modal_app.py"
  cat > "$dir/bin/modal" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$dir/modal.log"
if [[ "\$1" == secret ]]; then
  for ((i = 1; i <= \$#; i++)); do
    [[ "\${!i}" == --from-dotenv ]] && { j=\$((i + 1)); cp "\${!j}" "$dir/secret.env"; }
  done
  exit 0
fi
[[ -f "$dir/deploy-fails" ]] && { echo "Error: something"; exit 1; }
[[ -f "$dir/deploy-no-url" ]] && { echo "deployed, no address"; exit 0; }
echo "✓ Created web function web => https://someone--orphan-parts-web.modal.run"
STUB
  cat > "$dir/bin/wrangler" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$dir/wrangler.log"
if [[ "\$1 \$2 \$3" == "pages project list" ]]; then
  echo "│ Project Name │ Project Domains │"
  [[ -f "$dir/project-exists" ]] && echo "│ orphan-parts │ orphan-parts.pages.dev │"
  echo "│ other-site │ other-site.pages.dev │"
  exit 0
fi
[[ "\$1 \$2" == "pages deploy" ]] && echo "Deployment complete! https://abc123.orphan-parts.pages.dev"
exit 0
STUB
  cat > "$dir/bin/npm" <<STUB
#!/usr/bin/env bash
printf '%s VITE_API_URL=%s\n' "\$*" "\${VITE_API_URL:-}" >> "$dir/npm.log"
[[ "\$1 \$2" == "run build" ]] && { mkdir -p dist; echo '<html></html>' > dist/index.html; }
exit 0
STUB
  cat > "$dir/bin/curl" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$dir/curl.log"
[[ -f "$dir/readyz" ]] || exit 7
cat "$dir/readyz"
STUB
  chmod +x "$dir/bin/"*
  printf '{"status":"ok","model_api":"fixture","demo":"gated"}' > "$dir/readyz"
}

_hosted_env() {
  # the settings every step gets; tests override single ones on the command line
  local dir="$1"; shift
  env ROOT="$dir" MODAL="$dir/bin/modal" WRANGLER="$dir/bin/wrangler" NPM="$dir/bin/npm" CURL="$dir/bin/curl" \
    READY_TRIES=2 READY_WAIT=0 WEB_ORIGIN=https://orphan-parts.pages.dev "$@"
}

test_hosted_secret_is_written_from_the_environment_with_every_field() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  _hosted_tree "$dir"
  assert_true _hosted_env "$dir" MODEL_API_KEY_DEMO=sample-value DEMO_ACCESS_CODE=judges-code SPEND_CAP_USD=15 OPL_FAKE_API=0 bash "$_hosted" secret
  assert_true grep -q '^secret create orphan-parts --from-dotenv .* --force$' "$dir/modal.log"
  assert_eq "$(tr '\n' ' ' < "$dir/secret.env")" "MODEL_API_KEY=sample-value DEMO_ACCESS_CODE=judges-code SPEND_CAP_USD=15 OPL_FAKE_API=0 CORS_ORIGINS=https://orphan-parts.pages.dev DEMO_COOKIE_SECURE=1 "
  # the dotenv the stand-in copied was a temporary file, removed after the call
  assert_false test -f "$(grep -oE -- '--from-dotenv [^ ]+' "$dir/modal.log" | cut -d' ' -f2)"
  # nothing set: recorded answers, open, the defaults
  rm -f "$dir/secret.env"
  assert_true _hosted_env "$dir" bash "$_hosted" secret
  assert_eq "$(tr '\n' ' ' < "$dir/secret.env")" "MODEL_API_KEY= DEMO_ACCESS_CODE= SPEND_CAP_USD=20 OPL_FAKE_API=1 CORS_ORIGINS=https://orphan-parts.pages.dev DEMO_COOKIE_SECURE=1 "
  # the origin has to be https, and present
  assert_false _hosted_env "$dir" WEB_ORIGIN= bash "$_hosted" secret 2>/dev/null
  assert_false _hosted_env "$dir" WEB_ORIGIN=http://orphan-parts.pages.dev bash "$_hosted" secret 2>/dev/null
  assert_false _hosted_env "$dir" WEB_ORIGIN='https://x.pages.dev/path' bash "$_hosted" secret 2>/dev/null
  _hosted_cleanup "$dir"
}

test_hosted_backend_deploys_finds_the_url_and_waits_for_readyz() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _hosted_tree "$dir"
  out="$(_hosted_env "$dir" GITHUB_OUTPUT="$dir/out" bash "$_hosted" backend)" && assert_true true || assert_true false
  assert_eq "$(cat "$dir/modal.log")" "deploy $dir/deploy/modal_app.py"
  assert_true grep -q '^-fsS -m 20 https://someone--orphan-parts-web.modal.run/readyz$' "$dir/curl.log"
  assert_true grep -q 'backend: https://someone--orphan-parts-web.modal.run is up' <<<"$out"
  assert_eq "$(cat "$dir/out")" "api_url=https://someone--orphan-parts-web.modal.run"
  # a readyz that is not ok, one that never answers, a deploy without a URL, a failed deploy
  printf '{"status":"degraded"}' > "$dir/readyz"
  assert_false _hosted_env "$dir" bash "$_hosted" backend 2>/dev/null
  rm "$dir/readyz"
  : > "$dir/curl.log"
  assert_false _hosted_env "$dir" bash "$_hosted" backend 2>/dev/null
  assert_eq "$(wc -l < "$dir/curl.log" | tr -d ' ')" "2"   # READY_TRIES
  touch "$dir/deploy-no-url"
  assert_false _hosted_env "$dir" bash "$_hosted" backend 2>/dev/null
  rm "$dir/deploy-no-url"; touch "$dir/deploy-fails"
  assert_false _hosted_env "$dir" bash "$_hosted" backend 2>/dev/null
  rm "$dir/deploy/modal_app.py" "$dir/deploy-fails"
  assert_false _hosted_env "$dir" bash "$_hosted" backend 2>/dev/null
  _hosted_cleanup "$dir"
}

test_hosted_web_builds_against_the_api_and_publishes_to_pages() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _hosted_tree "$dir"
  # the project is missing: created, then the build is deployed
  out="$(_hosted_env "$dir" API_URL=https://someone--orphan-parts-web.modal.run GITHUB_OUTPUT="$dir/out" bash "$_hosted" web)" && assert_true true || assert_true false
  assert_eq "$(tr '\n' '|' < "$dir/npm.log")" "ci VITE_API_URL=https://someone--orphan-parts-web.modal.run|run build VITE_API_URL=https://someone--orphan-parts-web.modal.run|"
  assert_eq "$(tr '\n' '|' < "$dir/wrangler.log")" "pages project list|pages project create orphan-parts --production-branch main|pages deploy $dir/frontend/dist --project-name orphan-parts --branch main|"
  assert_true grep -q 'web: published at https://orphan-parts.pages.dev' <<<"$out"
  assert_eq "$(cat "$dir/out")" "web_url=https://orphan-parts.pages.dev"
  # the project exists: no create
  : > "$dir/wrangler.log"; touch "$dir/project-exists"
  assert_true _hosted_env "$dir" API_URL=https://someone--orphan-parts-web.modal.run bash "$_hosted" web
  assert_false grep -q 'project create' "$dir/wrangler.log"
  # a custom domain passes; another pages.dev origin does not; no API URL, a bad project name
  assert_true _hosted_env "$dir" WEB_ORIGIN=https://parts.example API_URL=https://someone--orphan-parts-web.modal.run bash "$_hosted" web
  assert_false _hosted_env "$dir" WEB_ORIGIN=https://other.pages.dev API_URL=https://someone--orphan-parts-web.modal.run bash "$_hosted" web 2>/dev/null
  assert_false _hosted_env "$dir" bash "$_hosted" web 2>/dev/null
  assert_false _hosted_env "$dir" PAGES_PROJECT='Orphan Parts' API_URL=https://someone--orphan-parts-web.modal.run bash "$_hosted" web 2>/dev/null
  _hosted_cleanup "$dir"
}

test_hosted_all_runs_the_three_steps_and_the_web_takes_the_backend_url() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  _hosted_tree "$dir"
  assert_true _hosted_env "$dir" bash "$_hosted" all
  assert_eq "$(cut -d' ' -f1 "$dir/modal.log" | tr '\n' ' ')" "secret deploy "
  assert_true grep -q 'run build VITE_API_URL=https://someone--orphan-parts-web.modal.run' "$dir/npm.log"
  assert_true grep -q 'pages deploy' "$dir/wrangler.log"
  assert_false _hosted_env "$dir" bash "$_hosted" elsewhere 2>/dev/null
  # no modal command: said with the install line
  assert_false _hosted_env "$dir" MODAL="$dir/bin/nowhere" bash "$_hosted" backend 2>/dev/null
  _hosted_cleanup "$dir"
}
