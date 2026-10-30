#!/usr/bin/env bash
# scan-security.sh [--json] [<ref>]: what gitleaks and foxguard find in the committed tree,
# never in files that are not committed. Two scans, one answer:
#
#   gitleaks   secrets in the git history (every commit reachable from <ref>, default HEAD)
#   foxguard   secrets and built-in rules over the tracked files at <ref>, checked out into a
#              temporary directory so an uncommitted change never shows up
#
#   --json   write gitleaks.json and foxguard.json under scan/ (git-ignored) and print the
#            counts; without it the two tools print their own reports
#
# Exit code: 0 when both find nothing, 1 when either finds something, 2 when a tool is missing.
# Both tools are installed with pipx or from their release pages; see docs/development/ci.md.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
json=0
ref="HEAD"
for arg in "$@"; do
  case "$arg" in
    --json) json=1 ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) ref="$arg" ;;
  esac
done

GITLEAKS="${GITLEAKS:-gitleaks}"
FOXGUARD="${FOXGUARD:-foxguard}"
for tool in "$GITLEAKS" "$FOXGUARD"; do
  command -v "$tool" >/dev/null 2>&1 || { printf 'scan-security: %s is not installed\n' "$tool" >&2; exit 2; }
done

out="$root/scan"
mkdir -p "$out"
# the tracked files at <ref>, and nothing else: a clean export of that commit
tree="$(mktemp -d)"
trap 'rm -rf -- "$tree"' EXIT
git -C "$root" archive "$ref" | tar -x -C "$tree"

rc=0
printf 'scan-security: gitleaks over the history reachable from %s\n' "$ref"
if [[ "$json" == 1 ]]; then
  "$GITLEAKS" git "$root" --log-opts="$ref" --no-banner --exit-code 1 --report-format json --report-path "$out/gitleaks.json" >/dev/null 2>&1 || rc=1
  printf 'gitleaks: %s finding(s), scan/gitleaks.json\n' "$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$out/gitleaks.json" 2>/dev/null || echo '?')"
else
  "$GITLEAKS" git "$root" --log-opts="$ref" --no-banner --exit-code 1 || rc=1
fi

printf 'scan-security: foxguard over the tracked files at %s\n' "$ref"
if [[ "$json" == 1 ]]; then
  "$FOXGUARD" "$tree" --format json > "$out/foxguard.json" 2>/dev/null || rc=1
  printf 'foxguard: %s finding(s), scan/foxguard.json\n' "$(python3 - "$out/foxguard.json" <<'PY' 2>/dev/null || echo '?'
import json, sys
data = json.load(open(sys.argv[1]))
found = data.get("findings") if isinstance(data, dict) else data
print(len(found) if isinstance(found, list) else "?")
PY
)"
else
  "$FOXGUARD" "$tree" || rc=1
fi

if [[ $rc -eq 0 ]]; then printf 'scan-security: clean\n'; else printf 'scan-security: findings above\n'; fi
exit $rc
