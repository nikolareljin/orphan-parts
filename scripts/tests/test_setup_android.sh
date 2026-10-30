#!/usr/bin/env bash
# setup-android.sh: what it checks and what it installs, with stand-ins for java, curl, unzip,
# sdkmanager and the package manager, in a temporary SDK directory.

_setup_android="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/setup-android.sh"

_sa_cleanup() { [[ -n "${1:-}" && -d "$1" && "$1" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$1"; }

# Stand-ins: a java of a given major, a sdkmanager that creates the package directory it is
# asked for, a curl that writes a zip holding cmdline-tools/bin/sdkmanager, the real unzip.
_sa_tree() {
  local dir="$1" major="${2:-21}"
  mkdir -p "$dir/bin" "$dir/sdk"
  printf '#!/usr/bin/env bash\nprintf "openjdk version \\"%s.0.1\\" 2026-01-01\\n" >&2\n' "$major" > "$dir/bin/java"
  cat > "$dir/bin/sdkmanager" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$dir/sdkmanager.log"
root=""
for a in "\$@"; do case "\$a" in --sdk_root=*) root="\${a#--sdk_root=}";; esac; done
for a in "\$@"; do case "\$a" in --*) ;; *) mkdir -p "\$root/\${a//;//}";; esac; done
EOF
  printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$@" >> "%s/installer.log"\n' "$dir" > "$dir/bin/installer"
  chmod +x "$dir/bin/java" "$dir/bin/sdkmanager" "$dir/bin/installer"
}

test_check_reports_what_is_missing_and_present() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _sa_tree "$dir" 21
  out="$(env ANDROID_HOME="$dir/sdk" JAVA="$dir/bin/java" bash "$_setup_android" --check 2>&1)" && assert_true false || assert_true true
  assert_true grep -q "java: openjdk version" <<<"$out"
  assert_true grep -q "command-line tools are missing" <<<"$out"
  # everything present
  mkdir -p "$dir/sdk/cmdline-tools/latest/bin" "$dir/sdk/platform-tools" "$dir/sdk/platforms/android-35" "$dir/sdk/build-tools/35.0.0"
  cp "$dir/bin/sdkmanager" "$dir/sdk/cmdline-tools/latest/bin/sdkmanager"
  out="$(env ANDROID_HOME="$dir/sdk" JAVA="$dir/bin/java" bash "$_setup_android" --check 2>&1)" && assert_true true || assert_true false
  assert_true grep -q "everything the app needs is here" <<<"$out"
  assert_false test -f "$dir/sdkmanager.log"  # --check runs nothing
  _sa_cleanup "$dir"
}

test_an_old_java_is_installed_through_the_package_manager() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _sa_tree "$dir" 11
  mkdir -p "$dir/sdk/cmdline-tools/latest/bin" "$dir/sdk/platform-tools" "$dir/sdk/platforms/android-35" "$dir/sdk/build-tools/35.0.0"
  cp "$dir/bin/sdkmanager" "$dir/sdk/cmdline-tools/latest/bin/sdkmanager"
  # the stand-in installer "installs" nothing, so the script must say java is still missing
  out="$(env ANDROID_HOME="$dir/sdk" JAVA="$dir/bin/java" INSTALLER="$dir/bin/installer" bash "$_setup_android" 2>&1)" && assert_true false || assert_true true
  assert_true grep -q "openjdk-17-jdk\|openjdk@17" "$dir/installer.log"
  assert_true grep -q "java still not found after the install" <<<"$out"
  _sa_cleanup "$dir"
}

test_packages_are_installed_after_the_licences() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _sa_tree "$dir" 21
  mkdir -p "$dir/sdk/cmdline-tools/latest/bin"
  cp "$dir/bin/sdkmanager" "$dir/sdk/cmdline-tools/latest/bin/sdkmanager"
  out="$(env ANDROID_HOME="$dir/sdk" JAVA="$dir/bin/java" bash "$_setup_android" 2>&1)" && assert_true true || assert_true false
  assert_true grep -q "^--sdk_root=$dir/sdk --licenses$" "$dir/sdkmanager.log"
  assert_true grep -q "^--sdk_root=$dir/sdk platform-tools$" "$dir/sdkmanager.log"
  assert_true grep -q "^--sdk_root=$dir/sdk platforms;android-35$" "$dir/sdkmanager.log"
  assert_true grep -q "^--sdk_root=$dir/sdk build-tools;35.0.0$" "$dir/sdkmanager.log"
  assert_true test -d "$dir/sdk/build-tools/35.0.0"
  assert_true grep -q "ready: ANDROID_HOME=$dir/sdk" <<<"$out"
  _sa_cleanup "$dir"
}

test_the_tools_download_is_checked_before_it_is_unpacked() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _sa_tree "$dir" 21
  # a curl stand-in that writes a zip with the expected layout, whatever the URL
  mkdir -p "$dir/zipsrc/cmdline-tools/bin"
  cp "$dir/bin/sdkmanager" "$dir/zipsrc/cmdline-tools/bin/sdkmanager"
  (cd "$dir/zipsrc" && zip -qr "$dir/tools.zip" cmdline-tools)
  printf '#!/usr/bin/env bash\nout=""\nwhile [[ $# -gt 0 ]]; do [[ "$1" == -o ]] && out="$2"; shift; done\ncp "%s/tools.zip" "$out"\n' "$dir" > "$dir/bin/curl"
  chmod +x "$dir/bin/curl"
  # the checksum of the stand-in zip does not match Google's: refused, nothing installed
  out="$(env ANDROID_HOME="$dir/sdk" JAVA="$dir/bin/java" CURL="$dir/bin/curl" bash "$_setup_android" 2>&1)" && assert_true false || assert_true true
  assert_true grep -q "checksum does not match" <<<"$out"
  assert_false test -d "$dir/sdk/cmdline-tools/latest"
  _sa_cleanup "$dir"
}
