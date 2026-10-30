#!/usr/bin/env bash
# app-icon.sh: the crops it hands Inkscape and the web mark it writes, with a stand-in Inkscape
# that records each call; a missing Inkscape or an unknown option is said.

_app_icon="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/app-icon.sh"
_app_icon_logo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/docs/assets/logo.svg"

# Only a directory mktemp made is removed: never an empty path, never anything else.
_app_icon_cleanup() { [[ -n "${1:-}" && -d "$1" && "$1" == "${TMPDIR:-/tmp}"/* ]] && rm -rf -- "$1"; }

# A tree with the logo, the app's resources and the web assets, and an inkscape that records its
# arguments and copies the SVG it was given to the PNG path, so the crops can be read back.
_app_icon_tree() {
  local dir="$1"
  mkdir -p "$dir/docs/assets" "$dir/android/app/src/main/res" "$dir/frontend/public" "$dir/bin"
  cp "$_app_icon_logo" "$dir/docs/assets/logo.svg"
  cat > "$dir/bin/inkscape" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$dir/inkscape.log"
[[ "\$1" == "--version" ]] && { printf 'Inkscape 1.2.2 (stand-in)\n'; exit 0; }
out=""; for a in "\$@"; do case "\$a" in --export-filename=*) out="\${a#*=}" ;; esac; done
cp "\${!#}" "\$out"
STUB
  chmod +x "$dir/bin/inkscape"
}

test_app_icon_writes_every_density_and_the_web_mark() {
  local dir res
  dir="$(mktemp -d)" || { assert_true false; return; }
  _app_icon_tree "$dir"
  assert_true env ROOT="$dir" INKSCAPE="$dir/bin/inkscape" bash "$_app_icon"
  res="$dir/android/app/src/main/res"
  # three PNGs per density, at 108dp and 48dp in pixels (rendered aside, then moved into place)
  assert_eq "$(grep -c -- '--export-type=png' "$dir/inkscape.log")" "15"
  assert_true grep -q -- "/mipmap-mdpi/ic_launcher_foreground.png --export-width=108 " "$dir/inkscape.log"
  assert_true grep -q -- "/mipmap-hdpi/ic_launcher.png --export-width=72 " "$dir/inkscape.log"
  assert_true grep -q -- "/mipmap-xxxhdpi/ic_launcher_round.png --export-width=192 " "$dir/inkscape.log"
  # the foreground: 108dp around the viewfinder's center (256,240), the ring (187 units) 66dp
  # across, so 108 * 374 / 66 units; the logo's frame is gone and nothing is clipped
  assert_true grep -q 'viewBox="-50.0018 -66.0018 612.0036 612.0036"' "$res/mipmap-mdpi/ic_launcher_foreground.png"
  assert_false grep -q 'id="rect51"' "$res/mipmap-mdpi/ic_launcher_foreground.png"
  assert_false grep -q 'clip-path' "$res/mipmap-mdpi/ic_launcher_foreground.png"
  assert_true grep -q '<circle cx="256" cy="240" r="204.0012" />' "$res/mipmap-mdpi/ic_launcher_round.png"
  # the web mark: the visible 72dp, a rounded square with no margin
  assert_true grep -q 'viewBox="51.9988 35.9988 408.0024 408.0024"' "$dir/frontend/public/brand.svg"
  assert_true grep -q 'rx="81.6005"' "$dir/frontend/public/brand.svg"
  assert_false grep -q 'id="rect51"' "$dir/frontend/public/brand.svg"
  # every crop is a whole document: the clipped ones close their group, all close the svg
  assert_eq "$(tail -n 1 "$dir/frontend/public/brand.svg")" "</g></svg>"
  assert_eq "$(tail -n 1 "$res/mipmap-mdpi/ic_launcher_round.png")" "</g></svg>"
  assert_eq "$(tail -n 1 "$res/mipmap-mdpi/ic_launcher_foreground.png")" "</svg>"
  _app_icon_cleanup "$dir"
}

test_app_icon_check_names_the_version_and_writes_nothing() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  _app_icon_tree "$dir"
  assert_eq "$(ROOT="$dir" INKSCAPE="$dir/bin/inkscape" bash "$_app_icon" --check)" "app-icon: inkscape 1.2.2"
  assert_false test -e "$dir/frontend/public/brand.svg"
  _app_icon_cleanup "$dir"
}

test_app_icon_without_inkscape_says_so() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  _app_icon_tree "$dir"
  assert_false env ROOT="$dir" INKSCAPE="$dir/bin/no-inkscape" bash "$_app_icon"
  assert_true grep -q 'inkscape is not installed' <(ROOT="$dir" INKSCAPE="$dir/bin/no-inkscape" bash "$_app_icon" 2>&1)
  assert_false test -e "$dir/frontend/public/brand.svg"
  _app_icon_cleanup "$dir"
}

test_app_icon_refuses_an_unknown_option() {
  local rc=0
  ROOT=/nonexistent bash "$_app_icon" --force >/dev/null 2>&1 || rc=$?
  assert_eq "$rc" "2"
}

test_app_icon_refuses_a_logo_whose_frame_moved() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  _app_icon_tree "$dir"
  sed -i 's/id="rect51"/id="frame"/' "$dir/docs/assets/logo.svg"
  assert_false env ROOT="$dir" INKSCAPE="$dir/bin/inkscape" bash "$_app_icon"
  assert_true grep -q 'did not take' <(ROOT="$dir" INKSCAPE="$dir/bin/inkscape" bash "$_app_icon" 2>&1)
  assert_false test -e "$dir/frontend/public/brand.svg"
  _app_icon_cleanup "$dir"
}

test_app_icon_refuses_a_logo_whose_viewbox_changed() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  _app_icon_tree "$dir"
  sed -i 's/viewBox="0 0 512 512"/viewBox="0 0 512 512.0"/' "$dir/docs/assets/logo.svg"
  assert_false env ROOT="$dir" INKSCAPE="$dir/bin/inkscape" bash "$_app_icon"
  assert_false test -e "$dir/frontend/public/brand.svg"
  _app_icon_cleanup "$dir"
}

test_app_icon_keeps_the_icons_when_inkscape_writes_nothing() {
  local dir
  dir="$(mktemp -d)" || { assert_true false; return; }
  _app_icon_tree "$dir"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$dir/bin/inkscape"
  assert_false env ROOT="$dir" INKSCAPE="$dir/bin/inkscape" bash "$_app_icon"
  assert_true grep -q 'wrote nothing' <(ROOT="$dir" INKSCAPE="$dir/bin/inkscape" bash "$_app_icon" 2>&1)
  assert_false test -e "$dir/frontend/public/brand.svg"
  assert_false test -e "$dir/android/app/src/main/res/mipmap-mdpi"
  _app_icon_cleanup "$dir"
}

# An awk that writes decimals with a comma unless it runs in the C locale, as mawk does under a
# comma-decimal locale: the geometry must come out the same.
test_app_icon_geometry_ignores_a_comma_decimal_locale() {
  local dir real_awk
  dir="$(mktemp -d)" || { assert_true false; return; }
  _app_icon_tree "$dir"
  real_awk="$(command -v awk)"
  cat > "$dir/bin/awk" <<STUB
#!/usr/bin/env bash
if [[ "\${LC_ALL:-}" == C ]]; then exec "$real_awk" "\$@"; fi
"$real_awk" "\$@" | tr . ,
STUB
  chmod +x "$dir/bin/awk"
  assert_true env PATH="$dir/bin:$PATH" LC_ALL=el_GR.UTF-8 ROOT="$dir" INKSCAPE="$dir/bin/inkscape" bash "$_app_icon"
  assert_true grep -q 'viewBox="51.9988 35.9988 408.0024 408.0024"' "$dir/frontend/public/brand.svg"
  assert_true grep -q -- '--export-width=108 ' "$dir/inkscape.log"
  _app_icon_cleanup "$dir"
}
