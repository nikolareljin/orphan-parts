#!/usr/bin/env bash
# android.sh: the adb calls a smoke run makes, with stand-ins for gradlew and adb that record
# what they were told; what is missing is said.

_android="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/android.sh"

# Only a directory mktemp made is removed: never an empty path, never anything else.
_android_cleanup() { [[ -n "${1:-}" && -d "$1" && "$1" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$1"; }

# A tree with an app, a gradlew that records its task and writes the APK, and an adb that
# records every call and answers like a device with the app on screen.
_android_tree() {
  local dir="$1"
  mkdir -p "$dir/android/app/build/outputs/apk/debug" "$dir/bin"
  cat > "$dir/android/gradlew" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$@" >> "$dir/gradlew.log"
case "\$*" in
  *assembleDebug*) printf 'apk' > "$dir/android/app/build/outputs/apk/debug/app-debug.apk" ;;
  *assembleRelease*) mkdir -p "$dir/android/app/build/outputs/apk/release"; printf 'apk' > "$dir/android/app/build/outputs/apk/release/app-release.apk" ;;
esac
EOF
  cat > "$dir/bin/adb" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$dir/adb.log"
case "\$*" in
  devices) printf 'List of devices attached\n%s\tdevice\n' "\${FAKE_DEVICE:-emulator-5554}" ;;
  "devices -l") printf 'List of devices attached\n%s                 device product:sdk model:sdk_gphone device:emu transport_id:1\n' "\${FAKE_DEVICE:-emulator-5554}" ;;
  "shell getprop sys.boot_completed") printf '1\n' ;;
  *"shell dumpsys activity activities") printf 'ResumedActivity: com.orphanparts.lens/.MainActivity\n' ;;
  *"exec-out screencap -p") printf 'PNG' ;;
esac
EOF
  chmod +x "$dir/android/gradlew" "$dir/bin/adb"
}

test_smoke_installs_launches_checks_the_screen_and_stops() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  _android_tree "$dir"
  assert_true env ROOT="$dir" ADB="$dir/bin/adb" SMOKE_OUT="$dir/shots" bash "$_android" smoke
  # the APK was built first, since there was none
  assert_eq "$(cat "$dir/gradlew.log" | tr '\n' ' ')" "--quiet assembleDebug "
  assert_true grep -q "^-s emulator-5554 install -r $dir/android/app/build/outputs/apk/debug/app-debug.apk$" "$dir/adb.log"
  assert_true grep -q "^-s emulator-5554 shell am start -W -n com.orphanparts.lens/.MainActivity$" "$dir/adb.log"
  assert_true grep -q "^-s emulator-5554 shell dumpsys activity activities$" "$dir/adb.log"
  assert_true grep -q "^-s emulator-5554 shell am force-stop com.orphanparts.lens$" "$dir/adb.log"
  assert_eq "$(cat "$dir/shots/smoke.png")" "PNG"
  # no emulator was started or stopped: a device was there
  assert_false grep -q "^emu kill$" "$dir/adb.log"
  _android_cleanup "$dir"
}

test_without_a_device_or_an_avd_the_smoke_run_is_refused() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _android_tree "$dir"
  printf '#!/usr/bin/env bash\ncase "$*" in devices*) printf "List of devices attached\\n";; esac\nexit 0\n' > "$dir/bin/adb"
  chmod +x "$dir/bin/adb"
  out="$(env ROOT="$dir" ADB="$dir/bin/adb" ANDROID_AVD= bash "$_android" smoke 2>&1)" && assert_true false || assert_true true
  assert_true grep -q "no device connected and ANDROID_AVD is not set" <<<"$out"
  _android_cleanup "$dir"
}

test_build_test_and_release_run_their_gradle_tasks() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _android_tree "$dir"
  assert_true env ROOT="$dir" bash "$_android" build
  assert_true env ROOT="$dir" bash "$_android" test
  out="$(env ROOT="$dir" KEYSTORE_PATH= bash "$_android" release)"
  assert_true grep -q "debug key: installs, not for a store" <<<"$out"
  assert_eq "$(grep -c "" "$dir/gradlew.log")" "6"
  assert_true grep -q "^assembleDebug$" "$dir/gradlew.log"
  assert_true grep -q "^testDebugUnitTest$" "$dir/gradlew.log"
  assert_true grep -q "^assembleRelease$" "$dir/gradlew.log"
  out="$(env ROOT="$dir" KEYSTORE_PATH=/k/store.jks bash "$_android" release)"
  assert_true grep -q "(release key)" <<<"$out"
  _android_cleanup "$dir"
}

test_no_app_and_a_bad_word_are_refused() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  assert_false env ROOT="$dir" bash "$_android" build 2>/dev/null
  _android_tree "$dir"
  assert_false env ROOT="$dir" bash "$_android" fly 2>/dev/null
  _android_cleanup "$dir"
}

test_an_emulator_that_exits_is_said_with_its_reason() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _android_tree "$dir"
  # no device; an "emulator" that writes the fatal line and exits at once
  printf '#!/usr/bin/env bash\ncase "$*" in devices*) printf "List of devices attached\\n";; esac\nexit 0\n' > "$dir/bin/adb"
  mkdir -p "$dir/sdk/emulator"
  printf '#!/usr/bin/env bash\nprintf "FATAL        | the image is for another CPU\\n"\nexit 1\n' > "$dir/sdk/emulator/emulator"
  chmod +x "$dir/bin/adb" "$dir/sdk/emulator/emulator"
  out="$(env ROOT="$dir" ADB="$dir/bin/adb" ANDROID_HOME="$dir/sdk" ANDROID_AVD=Some_AVD TMPDIR="$dir" bash "$_android" smoke 2>&1)" && assert_true false || assert_true true
  assert_true grep -q "the emulator exited: FATAL        | the image is for another CPU" <<<"$out"
  _android_cleanup "$dir"
}

test_launch_and_install_file_and_an_unauthorized_phone() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _android_tree "$dir"
  assert_true env ROOT="$dir" ADB="$dir/bin/adb" bash "$_android" launch
  assert_true grep -q "^-s emulator-5554 shell am start -W -n com.orphanparts.lens/.MainActivity$" "$dir/adb.log"
  printf 'apk' > "$dir/other.apk"
  assert_true env ROOT="$dir" ADB="$dir/bin/adb" bash "$_android" install-file "$dir/other.apk"
  assert_true grep -q "^-s emulator-5554 install -r $dir/other.apk$" "$dir/adb.log"
  assert_false env ROOT="$dir" ADB="$dir/bin/adb" bash "$_android" install-file "$dir/missing.apk" 2>/dev/null
  # a phone that has not accepted the computer is said, not waited for
  printf '#!/usr/bin/env bash\ncase "$*" in "devices -l") printf "List of devices attached\\nR5XYZ                 unauthorized usb:1-1 transport_id:1\\n";; devices) printf "List of devices attached\\nR5XYZ\\tunauthorized\\n";; esac\nexit 0\n' > "$dir/bin/adb"
  chmod +x "$dir/bin/adb"
  out="$(env ROOT="$dir" ADB="$dir/bin/adb" bash "$_android" launch 2>&1)" && assert_true false || assert_true true
  assert_true grep -q "accept the USB debugging prompt" <<<"$out"
  _android_cleanup "$dir"
}

test_several_devices_are_offered_and_one_is_picked() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _android_tree "$dir"
  cat > "$dir/bin/adb" <<ADB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$dir/adb.log"
case "\$*" in
  "devices -l") printf 'List of devices attached\nAAA111                 device usb:1-1 product:p model:Pixel_7 device:d transport_id:1\nBBB222                 device usb:1-2 product:p model:Galaxy_S21 device:d transport_id:2\n' ;;
  devices) printf 'List of devices attached\nAAA111\tdevice\nBBB222\tdevice\n' ;;
  "-s BBB222 shell dumpsys activity activities") printf 'ResumedActivity: com.orphanparts.lens/.MainActivity\n' ;;
  "-s BBB222 exec-out screencap -p") printf 'PNG' ;;
esac
ADB
  chmod +x "$dir/bin/adb"
  # picked by number without a terminal
  out="$(env ROOT="$dir" ADB="$dir/bin/adb" ANDROID_PICK=2 ANDROID_NO_TTY=1 bash "$_android" launch 2>&1)" && assert_true true || assert_true false
  assert_true grep -q "using BBB222" <<<"$out"
  assert_true grep -q "^-s BBB222 shell am start -W -n com.orphanparts.lens/.MainActivity$" "$dir/adb.log"
  # a number out of range is refused; no terminal and no pick: said, with the serials
  assert_false env ROOT="$dir" ADB="$dir/bin/adb" ANDROID_PICK=9 ANDROID_NO_TTY=1 bash "$_android" launch 2>/dev/null
  out="$(env ROOT="$dir" ADB="$dir/bin/adb" ANDROID_NO_TTY=1 bash "$_android" launch 2>&1)" && assert_true false || assert_true true
  assert_true grep -q "set ANDROID_SERIAL to one of: AAA111 BBB222" <<<"$out"
  # ANDROID_SERIAL picks without asking, and must be one of them
  assert_true env ROOT="$dir" ADB="$dir/bin/adb" ANDROID_SERIAL=BBB222 ANDROID_NO_TTY=1 SMOKE_OUT="$dir/shots" bash "$_android" smoke
  assert_false env ROOT="$dir" ADB="$dir/bin/adb" ANDROID_SERIAL=CCC333 ANDROID_NO_TTY=1 bash "$_android" launch 2>/dev/null
  _android_cleanup "$dir"
}

test_no_device_at_all_points_at_the_page_that_says_how() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _android_tree "$dir"
  printf '#!/usr/bin/env bash\ncase "$*" in devices*) printf "List of devices attached\\n";; esac\nexit 0\n' > "$dir/bin/adb"
  chmod +x "$dir/bin/adb"
  out="$(env ROOT="$dir" ADB="$dir/bin/adb" ANDROID_AVD= bash "$_android" launch 2>&1)" && assert_true false || assert_true true
  assert_true grep -q "guides/android/#allow-the-phone" <<<"$out"
  _android_cleanup "$dir"
}

test_serial_prints_the_picked_device_and_nothing_else() {
  local dir out
  dir="$(mktemp -d)" || { assert_true false; return; }
  _android_tree "$dir"
  # two phones, the second picked without a terminal: stdout is the serial, the list goes to stderr
  cat > "$dir/bin/adb" <<EOF
#!/usr/bin/env bash
case "\$*" in
  "devices -l") printf 'List of devices attached\nAAA111                 device product:a model:one device:a transport_id:1\nBBB222                 device product:b model:two device:b transport_id:2\n' ;;
esac
EOF
  chmod +x "$dir/bin/adb"
  out="$(env ROOT="$dir" ADB="$dir/bin/adb" ANDROID_PICK=2 ANDROID_NO_TTY=1 bash "$_android" serial 2>/dev/null)"
  assert_eq "$out" "BBB222"
  # one phone: its serial, no question asked
  cat > "$dir/bin/adb" <<EOF
#!/usr/bin/env bash
case "\$*" in
  "devices -l") printf 'List of devices attached\nAAA111                 device product:a model:one device:a transport_id:1\n' ;;
esac
EOF
  out="$(env ROOT="$dir" ADB="$dir/bin/adb" bash "$_android" serial 2>/dev/null)"
  assert_eq "$out" "AAA111"
  _android_cleanup "$dir"
}
