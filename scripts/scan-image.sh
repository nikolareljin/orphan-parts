#!/usr/bin/env bash
# scan-image.sh <image>...: no credential and no personal data in what an image ships.
#
# For each image: its configured environment must hold no filled value under a name that
# reads like a secret (KEY, TOKEN, SECRET, PASSWORD, CODE), and gitleaks must find nothing in
# the files the project put there (the backend's /app, the web app's /usr/share/nginx/html and
# the nginx configuration); the base image's own files are not the project's and are skipped.
# No .env, database, log or capture may be in those paths at all.
#
# Exit code: 0 clean, 1 a finding (printed with the value redacted), 2 a tool missing.
# Used by the release workflow before any image is pushed; runs the same on a laptop.
set -euo pipefail

GITLEAKS="${GITLEAKS:-gitleaks}"
DOCKER="${DOCKER:-docker}"
command -v "$DOCKER" >/dev/null 2>&1 || { echo "scan-image: docker is not installed" >&2; exit 2; }
command -v "$GITLEAKS" >/dev/null 2>&1 || { echo "scan-image: gitleaks is not installed" >&2; exit 2; }
[[ $# -ge 1 ]] || { echo "usage: scan-image.sh <image>..." >&2; exit 2; }

# the project's paths in each image; anything else came with the base image
PATHS=(app usr/share/nginx/html etc/nginx/conf.d)
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT
rc=0

for image in "$@"; do
  echo "scan-image: $image"
  img_rc=0
  # 1. the configured environment: names that read like secrets must be empty
  while IFS= read -r pair; do
    name="${pair%%=*}"
    value="${pair#*=}"
    # GPG_KEY is the base Python image's public release-signing key id, not a credential
    [[ "$name" == GPG_KEY ]] && continue
    if [[ "$name" =~ (^|_)(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CODE)$ && -n "$value" ]]; then
      echo "  FINDING: the image's environment sets $name (value not shown)"
      img_rc=1
    fi
  done < <("$DOCKER" image inspect "$image" --format '{{range .Config.Env}}{{println .}}{{end}}')

  # 2. the files the project put there
  dir="$work/$(echo "$image" | tr '/:' '__')"
  mkdir -p "$dir"
  container="$("$DOCKER" create "$image")"
  # tar complains about a path this image does not have and extracts the rest; a failed export
  # is a finding of its own
  set +e
  "$DOCKER" export "$container" | tar -x -C "$dir" "${PATHS[@]}" 2>/dev/null
  export_rc="${PIPESTATUS[0]}"
  set -e
  "$DOCKER" rm "$container" >/dev/null
  [[ "$export_rc" == 0 ]] || { echo "  FINDING: the image could not be exported"; img_rc=1; rc=1; continue; }
  found_any=0
  for p in "${PATHS[@]}"; do [[ -e "$dir/$p" ]] && found_any=1; done
  [[ "$found_any" == 1 ]] || { echo "  FINDING: none of the project's paths is in the image"; img_rc=1; rc=1; continue; }

  # files that never belong in an image
  while IFS= read -r f; do
    echo "  FINDING: ${f#"$dir"/} is in the image"
    img_rc=1
  done < <(find "$dir" -type f \( -name '.env' -o -name '.env.*' -o -name '*.sqlite3' -o -name '*.sqlite3-*' \
    -o -name '*.sqlite' -o -name '*.db' \
    -o -name '*.log' -o -name '*.jks' -o -name 'keystore.properties' \
    -o -name 'photo-*.jpg' -o -name 'clip.mp4' -o -name 'note.wav' \) ! -name '.env.example')

  # --verbose lists each finding (file, line, rule); --redact keeps the secret itself out
  if ! "$GITLEAKS" dir "$dir" --no-banner --redact --verbose --exit-code 1 >"$work/gitleaks.log" 2>&1; then
    echo "  FINDING: gitleaks found something in the project's files:"
    grep -E '^(Finding|File|RuleID|Line):' "$work/gitleaks.log" | sed "s|$dir/||" | sed 's/^/    /' || true
    img_rc=1
  fi
  [[ $img_rc -eq 0 ]] && echo "  clean"
  [[ $img_rc -eq 0 ]] || rc=1
done

exit $rc
