#!/usr/bin/env bash
# deploy.sh: the remote command it runs, with a stand-in for ssh that records its arguments;
# what is not set up is said and skipped, or refused when asked for by name.

_deploy="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/deploy.sh"

# A tree with a VERSION, an origin and a stand-in ssh that writes what it was told to a file.
_deploy_tree() {
  local dir="$1"
  mkdir -p "$dir/bin"
  git -C "$dir" init -q -b main
  git -C "$dir" remote add origin https://github.com/someone/thing.git
  printf '0.2.0\n' > "$dir/VERSION"
  printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$@" > "%s/ssh.log"\n' "$dir" > "$dir/bin/ssh"
  chmod +x "$dir/bin/ssh"
}

test_web_runs_one_quoted_remote_command_with_the_release_tag() {
  local dir
  dir="$(mktemp -d)"
  _deploy_tree "$dir"
  assert_true env ROOT="$dir" DEPLOY_HOST=app@host.example DEPLOY_PATH=/srv/orphan-parts DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web
  assert_eq "$(sed -n 1p "$dir/ssh.log")" "app@host.example"
  assert_true grep -q "^cd /srv/orphan-parts && IMAGE_PREFIX=ghcr.io/someone/thing TAG=0.2.0 docker compose -f docker-compose.yml -f docker-compose.prod.yml pull && IMAGE_PREFIX=ghcr.io/someone/thing TAG=0.2.0 docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --remove-orphans$" "$dir/ssh.log"
  # --version and IMAGE_PREFIX win over VERSION and the origin
  assert_true env ROOT="$dir" DEPLOY_HOST=app@host.example DEPLOY_PATH=/srv/x IMAGE_PREFIX=registry.example/img DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web --version 0.3.0
  assert_true grep -q "IMAGE_PREFIX=registry.example/img TAG=0.3.0" "$dir/ssh.log"
  rm -rf "$dir"
}

test_deploy_settings_are_read_from_dot_env_and_checked() {
  local dir
  dir="$(mktemp -d)"
  _deploy_tree "$dir"
  printf 'DEPLOY_HOST=app@host.example\nDEPLOY_PATH=/srv/orphan-parts\n' > "$dir/.env"
  assert_true env ROOT="$dir" DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web
  assert_eq "$(sed -n 1p "$dir/ssh.log")" "app@host.example"
  assert_false env ROOT="$dir" DEPLOY_HOST="app@host.example; rm -rf /" DEPLOY_PATH=/srv DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web 2>/dev/null
  assert_false env ROOT="$dir" DEPLOY_HOST=app@host.example DEPLOY_PATH='/srv/$(x)' DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web 2>/dev/null
  assert_false env ROOT="$dir" DEPLOY_HOST=app@host.example DEPLOY_PATH=/srv DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" web --version v1 2>/dev/null
  rm -rf "$dir"
}

test_what_is_not_set_up_is_skipped_for_all_and_refused_by_name() {
  local dir out
  dir="$(mktemp -d)"
  _deploy_tree "$dir"
  out="$(env ROOT="$dir" DEPLOY_HOST= DEPLOY_SSH="$dir/bin/ssh" bash "$_deploy" all 2>&1)"
  assert_true grep -q 'web: DEPLOY_HOST is not set; skipped' <<<"$out"
  assert_true grep -q 'android: no app in this tree yet; skipped' <<<"$out"
  assert_false env ROOT="$dir" DEPLOY_HOST= bash "$_deploy" web 2>/dev/null
  assert_false env ROOT="$dir" bash "$_deploy" android 2>/dev/null
  assert_false env ROOT="$dir" bash "$_deploy" elsewhere 2>/dev/null
  rm -rf "$dir"
}
