#!/usr/bin/env bash
# phone-install.sh: adb found or downloaded, the APK taken from the release listing or a file,
# the phone's state read and explained, the install and the launch; with stand-ins for curl,
# unzip and adb that record what they were told.

_phone="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/phone-install.sh"

_phone_cleanup() { [[ -n "${1:-}" && -d "$1" && "$1" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$1"; }

# A tree with the three stand-ins. curl answers a release listing (from a file) or writes an
# APK or a zip; unzip "unpacks" by creating platform-tools/adb; adb lists devices from a file.
_phone_tree() {
  local dir="$1"
  mkdir -p "$dir/bin" "$dir/tools" "$dir/path"
  # a PATH with the tools the script needs and no adb, so the download path is the one taken
  local tool
  for tool in bash grep awk sed basename dirname mkdir rm tr head uname cat chmod env; do
    [[ -e "$dir/path/$tool" ]] || ln -s "$(type -P "$tool")" "$dir/path/$tool"
  done
  cat > "$dir/bin/curl" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$dir/curl.log"
out=""
for ((i = 1; i <= \$#; i++)); do [[ "\${!i}" == -o ]] && { j=\$((i + 1)); out="\${!j}"; }; done
url="\${!#}"
[[ -f "$dir/curl-fails" ]] && exit 22
case "\$url" in
  *.apk) printf 'apk-bytes' > "\$out" ;;
  *.zip) printf 'zip-bytes' > "\$out" ;;
  *releases*) cat "$dir/release.json" ;;
esac
STUB
  cat > "$dir/bin/unzip" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$dir/unzip.log"
dest=""
for ((i = 1; i <= \$#; i++)); do [[ "\${!i}" == -d ]] && { j=\$((i + 1)); dest="\${!j}"; }; done
mkdir -p "\$dest/platform-tools"
printf '#!/usr/bin/env bash\nexec "$dir/bin/adb" "\$@"\n' > "\$dest/platform-tools/adb"
chmod +x "\$dest/platform-tools/adb"
STUB
  cat > "$dir/bin/adb" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$dir/adb.log"
case "\$*" in
  devices) printf 'List of devices attached\n'; cat "$dir/devices" 2>/dev/null ;;
  *install*) [[ -f "$dir/install-fails" ]] && exit 1 ;;
esac
exit 0
STUB
  chmod +x "$dir/bin/"*
  printf '{"assets":[{"name":"orphan-parts-0.3.0.apk","browser_download_url":"https://github.com/x/orphan-parts/releases/download/0.3.0/orphan-parts-0.3.0.apk"}]}\n' > "$dir/release.json"
  printf 'ABC123\tdevice\n' > "$dir/devices"
}

_phone_env() {
  local dir="$1"; shift
  env HOME="$dir" TOOLS_DIR="$dir/tools" CURL="$dir/bin/curl" UNZIP="$dir/bin/unzip" PATH="$dir/path" "$@"
}

test_phone_install_downloads_adb_and_the_release_apk_then_installs() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _phone_tree "$dir"
  out="$(_phone_env "$dir" bash "$_phone")" && assert_true true || assert_true false
  assert_true grep -q 'platform-tools-latest-linux.zip\|platform-tools-latest-darwin.zip' "$dir/curl.log"
  assert_true grep -q 'releases/latest' "$dir/curl.log"
  assert_true grep -q 'orphan-parts-0.3.0.apk' "$dir/curl.log"
  assert_true test -f "$dir/tools/orphan-parts-0.3.0.apk"
  assert_true grep -q '^-s ABC123 install -r .*orphan-parts-0.3.0.apk$' "$dir/adb.log"
  assert_true grep -q 'monkey -p com.orphanparts.lens' "$dir/adb.log"
  assert_true grep -q 'Scan to pair' <<<"$out"
  # a version asked for: that tag's release; a file given: no download at all
  : > "$dir/curl.log"
  assert_true _phone_env "$dir" bash "$_phone" --version 0.2.0
  assert_true grep -q 'releases/tags/0.2.0' "$dir/curl.log"
  : > "$dir/curl.log"; printf 'x' > "$dir/mine.apk"
  assert_true _phone_env "$dir" bash "$_phone" --apk "$dir/mine.apk"
  assert_false grep -q 'releases' "$dir/curl.log"
  assert_true grep -q 'install -r .*mine.apk' "$dir/adb.log"
  _phone_cleanup "$dir"
}

test_phone_install_uses_the_adb_it_is_given_and_explains_the_phone() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  _phone_tree "$dir"
  # an adb named in the environment: no platform-tools download
  assert_true _phone_env "$dir" ADB="$dir/bin/adb" bash "$_phone"
  assert_false grep -q 'platform-tools' "$dir/curl.log"
  # no phone, an unauthorized one, two of them, one named by ANDROID_SERIAL
  : > "$dir/devices"
  assert_false _phone_env "$dir" ADB="$dir/bin/adb" bash "$_phone" 2>/dev/null
  printf 'ABC123\tunauthorized\n' > "$dir/devices"
  assert_false _phone_env "$dir" ADB="$dir/bin/adb" bash "$_phone" 2>/dev/null
  printf 'ABC123\tdevice\nDEF456\tdevice\n' > "$dir/devices"
  assert_false _phone_env "$dir" ADB="$dir/bin/adb" bash "$_phone" 2>/dev/null
  : > "$dir/adb.log"
  assert_true _phone_env "$dir" ADB="$dir/bin/adb" ANDROID_SERIAL=DEF456 bash "$_phone"
  assert_true grep -q '^-s DEF456 install' "$dir/adb.log"
  # a release without an APK, a failed download, a failed install, a bad option
  printf '{"assets":[]}\n' > "$dir/release.json"
  assert_false _phone_env "$dir" ADB="$dir/bin/adb" bash "$_phone" 2>/dev/null
  _phone_tree "$dir"; touch "$dir/curl-fails"
  assert_false _phone_env "$dir" ADB="$dir/bin/adb" bash "$_phone" 2>/dev/null
  rm "$dir/curl-fails"; touch "$dir/install-fails"
  assert_false _phone_env "$dir" ADB="$dir/bin/adb" bash "$_phone" 2>/dev/null
  rm "$dir/install-fails"
  assert_false _phone_env "$dir" ADB="$dir/bin/adb" bash "$_phone" --what 2>/dev/null
  assert_true _phone_env "$dir" bash "$_phone" --help
  _phone_cleanup "$dir"
}
