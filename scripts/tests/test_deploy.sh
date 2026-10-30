#!/usr/bin/env bash
# deploy.sh: the remote command it runs, with a stand-in for ssh that records its arguments;
# what is not set up is said and skipped, or refused when asked for by name.

_deploy="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/deploy.sh"

# Only a directory mktemp made is removed: never an empty path, never anything else.
_deploy_cleanup() { [[ -n "${1:-}" && -d "$1" && "$1" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$1"; }

# A tree with a VERSION, an origin and a stand-in ssh that writes what it was told to a file.
_deploy_tree() {
  local dir="$1"
  mkdir -p "$dir/bin"
  git -C "$dir" init -q -b main
  git -C "$dir" remote add origin https://github.com/someone/thing.git
  printf '0.2.0\n' > "$dir/VERSION"
  printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$@" > "%s/ssh.log"\n' "$dir" > "$dir/bin/ssh"
  cp "$dir/bin/ssh" "$dir/bin/ssh-with-options"
  chmod +x "$dir/bin/ssh" "$dir/bin/ssh-with-options"
}

test_web_runs_one_quoted_remote_command_with_the_release_tag() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  _deploy_tree "$dir"
  assert_true env ROOT="$dir" DEPLOY_HOST=app@host.example DEPLOY_PATH=/srv/orphan-parts DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web
  assert_eq "$(sed -n 1p "$dir/ssh.log")" "app@host.example"
  assert_true grep -q "^cd /srv/orphan-parts && IMAGE_PREFIX=ghcr.io/someone/thing TAG=0.2.0 docker compose -f docker-compose.yml -f docker-compose.prod.yml pull && IMAGE_PREFIX=ghcr.io/someone/thing TAG=0.2.0 docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans$" "$dir/ssh.log"
  # the ssh command may carry options, which reach ssh before the host
  assert_true env ROOT="$dir" DEPLOY_HOST=app@host.example DEPLOY_PATH=/srv/x DEPLOY_SSH="$dir/bin/ssh-with-options -i /k -o StrictHostKeyChecking=accept-new" bash "$_deploy" web
  assert_eq "$(sed -n 1,5p "$dir/ssh.log" | tr '\n' ' ')" "-i /k -o StrictHostKeyChecking=accept-new app@host.example "
  # --version and IMAGE_PREFIX win over VERSION and the origin
  assert_true env ROOT="$dir" DEPLOY_HOST=app@host.example DEPLOY_PATH=/srv/x IMAGE_PREFIX=registry.example/img DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web --version 0.3.0
  assert_true grep -q "IMAGE_PREFIX=registry.example/img TAG=0.3.0" "$dir/ssh.log"
  _deploy_cleanup "$dir"
}

test_deploy_settings_are_read_from_dot_env_and_checked() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  _deploy_tree "$dir"
  printf 'DEPLOY_HOST="app@host.example"\nDEPLOY_PATH=/srv/orphan-parts\nIMAGE_PREFIX=registry.example/a=b/img\n' > "$dir/.env"
  assert_true env ROOT="$dir" DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web
  assert_eq "$(sed -n 1p "$dir/ssh.log")" "app@host.example"
  assert_true grep -q "IMAGE_PREFIX=registry.example/a=b/img TAG=0.2.0" "$dir/ssh.log"  # quotes dropped, a later = kept
  assert_false env ROOT="$dir" DEPLOY_HOST="app@host.example; rm -rf /" DEPLOY_PATH=/srv DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web 2>/dev/null
  assert_false env ROOT="$dir" DEPLOY_HOST=app@host.example DEPLOY_PATH='/srv/$(x)' DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web 2>/dev/null
  assert_false env ROOT="$dir" DEPLOY_HOST=app@host.example DEPLOY_PATH='~/srv' DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web 2>/dev/null
  assert_false env ROOT="$dir" DEPLOY_HOST=app@host.example DEPLOY_PATH='srv/x' DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web 2>/dev/null
  assert_false env ROOT="$dir" DEPLOY_HOST=app@host.example DEPLOY_PATH=/srv DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web --version v1 2>/dev/null
  _deploy_cleanup "$dir"
}

test_what_is_not_set_up_is_skipped_for_all_and_refused_by_name() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _deploy_tree "$dir"
  out="$(env ROOT="$dir" DEPLOY_HOST= DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" all 2>&1)"
  assert_true grep -q 'web: DEPLOY_HOST is not set; skipped' <<<"$out"
  assert_true grep -q 'android: no app in this tree yet; skipped' <<<"$out"
  assert_false env ROOT="$dir" DEPLOY_HOST= bash "$_deploy" web 2>/dev/null
  assert_false env ROOT="$dir" bash "$_deploy" android 2>/dev/null
  assert_false env ROOT="$dir" bash "$_deploy" elsewhere 2>/dev/null
  _deploy_cleanup "$dir"
}

test_modal_deploys_the_app_file_and_names_the_url() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _deploy_tree "$dir"
  mkdir -p "$dir/deploy"; printf 'app = 1\n' > "$dir/deploy/modal_app.py"
  printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$@" > "%s/modal.log"\nprintf "Created web function web => https://someone--orphan-parts-web.modal.run\\n"\n' "$dir" > "$dir/bin/modal"
  chmod +x "$dir/bin/modal"
  out="$(env ROOT="$dir" MODAL="$dir/bin/modal" bash "$_deploy" modal)" && assert_true true || assert_true false
  assert_eq "$(cat "$dir/modal.log" | tr '\n' ' ')" "deploy $dir/deploy/modal_app.py "
  assert_true grep -q "answers at https://someone--orphan-parts-web.modal.run" <<<"$out"
  # no modal command: said with the install line; no app file: said
  out="$(env ROOT="$dir" MODAL="$dir/bin/nowhere" bash "$_deploy" modal 2>&1)" && assert_true false || assert_true true
  assert_true grep -q "pipx install modal" <<<"$out"
  rm "$dir/deploy/modal_app.py"
  assert_false env ROOT="$dir" MODAL="$dir/bin/modal" bash "$_deploy" modal 2>/dev/null
  _deploy_cleanup "$dir"
}

test_deploy_hosted_reads_its_names_from_env_and_the_shell_wins() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  mkdir -p "$dir/scripts"
  # a stand-in for deploy-hosted.sh that prints what it was handed
  printf '#!/usr/bin/env bash\necho "args=$*"\necho "MODAL_TOKEN_ID=${MODAL_TOKEN_ID:-}"\necho "DEMO_ACCESS_CODE=${DEMO_ACCESS_CODE:-}"\necho "SPEND_CAP_USD=${SPEND_CAP_USD:-}"\necho "WEB_ORIGIN=${WEB_ORIGIN:-}"\necho "MODEL_API_KEY=${MODEL_API_KEY:-}"\n' > "$dir/scripts/deploy-hosted.sh"
  printf 'MODEL_API_KEY=local-only\nMODAL_TOKEN_ID=from-env\nDEMO_ACCESS_CODE=machine-code\nDEMO_ACCESS_CODE_HOSTED=host-code-long\nSPEND_CAP_USD_HOSTED=15\nWEB_ORIGIN=https://orphan-parts.pages.dev\nCLOUDFLARE_API_TOKEN=\n' > "$dir/.env"
  out="$(env -u MODAL_TOKEN_ID -u DEMO_ACCESS_CODE -u SPEND_CAP_USD -u WEB_ORIGIN -u MODEL_API_KEY ROOT="$dir" bash "$_deploy" hosted backend)"
  assert_true grep -q '^args=backend$' <<<"$out"
  assert_true grep -q '^MODAL_TOKEN_ID=from-env$' <<<"$out"
  assert_true grep -q '^DEMO_ACCESS_CODE=host-code-long$' <<<"$out"   # the host's, not this machine's
  assert_true grep -q '^SPEND_CAP_USD=15$' <<<"$out"
  assert_true grep -q '^WEB_ORIGIN=https://orphan-parts.pages.dev$' <<<"$out"
  assert_true grep -q '^MODEL_API_KEY=$' <<<"$out"                    # never handed to the host
  # the shell wins over .env
  out="$(env -u DEMO_ACCESS_CODE MODAL_TOKEN_ID=from-shell ROOT="$dir" bash "$_deploy" hosted)"
  assert_true grep -q '^MODAL_TOKEN_ID=from-shell$' <<<"$out"
  [[ "$dir" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$dir"
}
