#!/bin/sh
# theme_test.sh — regression tests for bin/.local/bin/theme.
#
#   sh tests/theme_test.sh              test the copy in this repo
#   THEME_BIN=~/.local/bin/theme sh tests/theme_test.sh   test the installed one
#
# HOW IT AVOIDS TOUCHING THE LIVE DESKTOP
#   `theme` derives REPO from $HOME, so each case runs with HOME pointed at a
#   throwaway tree containing a miniature of the real repo — the same fragment
#   shapes (`colors-nord.ini` with an extension, `.gtkrc-2.0-nord` and mako's
#   `colors-nord` without one), just five links instead of seventeen.
#
#   PATH is replaced with a stub directory in which swaymsg, sway and makoctl
#   all exit 1, so reload_desktop takes its "sway not running" branch and never
#   reaches `swaymsg reload`. stdin is /dev/null, so reload_icons takes its "no
#   tty for sudo" branch and prints $PAPIRUS_FOLDER instead of calling sudo —
#   that printed value is the observable proving reload_icons was handed the
#   theme name rather than some other variable's contents.
#
# WHY THIS EXISTS
#   sh has no function-local scope. switch_to() once used a loop variable named
#   `target`, the same global holding the requested theme, so it returned with
#   `target` set to the last symlink's old value (`colors-nord.ini`).
#   reload_icons then sourced `theme-colors-nord.ini.env`, which does not exist,
#   and `set -e` killed the script *after* the symlinks had flipped but before
#   papirus-folders ran — so switching took two invocations. Case 1 below is
#   that bug. The rest pin the guarantees the script's comments claim.
#
# NOT COVERED
#   The `[ ! -f "$env_file" ]` guard in reload_icons is unreachable from the CLI
#   (the theme name is validated against $THEMES first). It is a backstop for a
#   future caller, and is deliberately left untested rather than reached by a
#   contrived edit to the script under test.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPT=${THEME_BIN:-$here/../bin/.local/bin/theme}

[ -r "$SCRIPT" ] || { printf 'theme_test: cannot read %s\n' "$SCRIPT" >&2; exit 2; }

pass=0
fail=0

ok() { pass=$((pass + 1)); printf '  ok    %s\n' "$1"; }
no() {
    fail=$((fail + 1))
    printf '  FAIL  %s\n' "$1"
    if [ $# -ge 2 ]; then printf '        %s\n' "$2"; fi
}

contains()  { case "$2" in *"$3"*) ok "$1" ;; *) no "$1" "expected to contain: $3" ;; esac; }
excludes()  { case "$2" in *"$3"*) no "$1" "should not contain: $3" ;; *) ok "$1" ;; esac; }
equals()    { if [ "$2" = "$3" ]; then ok "$1"; else no "$1" "want '$3', got '$2'"; fi; }
exited()    { if [ "$rc" = "$2" ]; then ok "$1"; else no "$1" "want exit $2, got $rc"; fi; }

# ---------------------------------------------------------------- fixture ---

T=""
cleanup() { if [ -n "$T" ]; then rm -rf "$T"; fi; }
trap cleanup EXIT INT TERM

links() {
    printf '%s\n' \
        "$D/theme.env" \
        "$D/colors.conf" \
        "$R/foot/.config/foot/colors.ini" \
        "$R/gtk/.gtkrc-2.0" \
        "$R/mako/.config/mako/colors"
}

point_at() { # point_at <theme>
    ln -sfn "theme-$1.env"   "$D/theme.env"
    ln -sfn "colors-$1.conf" "$D/colors.conf"
    ln -sfn "colors-$1.ini"  "$R/foot/.config/foot/colors.ini"
    ln -sfn ".gtkrc-2.0-$1"  "$R/gtk/.gtkrc-2.0"
    ln -sfn "colors-$1"      "$R/mako/.config/mako/colors"
}

fixture() { # fixture <starting-theme>
    cleanup
    T=$(mktemp -d)
    R=$T/repos/dotfiles
    D=$R/sway/.config/sway
    mkdir -p "$D" "$R/foot/.config/foot" "$R/gtk" "$R/mako/.config/mako" "$T/stub"

    # Same variable names in both, as check_roles requires.
    printf 'BG=#2E3440\nPAPIRUS_FOLDER=nordic\nGTK_THEME_NAME=Nordic\n'  > "$D/theme-nord.env"
    printf 'BG=#282828\nPAPIRUS_FOLDER=yellow\nGTK_THEME_NAME=Colloid\n' > "$D/theme-gruvbox.env"
    printf 'set $bg #2E3440\n' > "$D/colors-nord.conf"
    printf 'set $bg #282828\n' > "$D/colors-gruvbox.conf"
    : > "$R/foot/.config/foot/colors-nord.ini"
    : > "$R/foot/.config/foot/colors-gruvbox.ini"
    : > "$R/gtk/.gtkrc-2.0-nord"
    : > "$R/gtk/.gtkrc-2.0-gruvbox"
    : > "$R/mako/.config/mako/colors-nord"
    : > "$R/mako/.config/mako/colors-gruvbox"
    point_at "$1"

    for c in swaymsg sway makoctl; do
        printf '#!/bin/sh\nexit 1\n' > "$T/stub/$c"
        chmod +x "$T/stub/$c"
    done
    # Silent, so reload_icons sees no active colour and always takes the
    # "would change it" path.
    printf '#!/bin/sh\nexit 0\n' > "$T/stub/papirus-folders"
    chmod +x "$T/stub/papirus-folders"
}

run() { # run [args...] -> sets $out and $rc
    out=$(HOME=$T PATH=$T/stub:/usr/bin:/bin sh "$SCRIPT" "$@" </dev/null 2>&1) && rc=0 || rc=$?
}

all_point_at() { # all_point_at <desc> <theme>
    bad=""
    for l in $(links); do
        t=$(readlink "$l")
        case "$t" in
            *"$2"*) ;;
            *) bad="$bad $(basename "$l")->$t" ;;
        esac
    done
    if [ -z "$bad" ]; then ok "$1"; else no "$1" "not on $2:$bad"; fi
}

# ------------------------------------------------------------------ cases ---

echo
echo "theme_test: $SCRIPT"
echo

echo "one invocation completes the whole switch"
fixture nord
run gruvbox
exited   'exits 0'                        0
contains 'flips every fragment'           "$out" 'Switched 5 symlinks: nord -> gruvbox'
contains 'reload_icons gets the theme'    "$out" 'yellow'
contains 'reaches the closing advisory'   "$out" 'The flipped symlinks are uncommitted'
excludes 'no missing-file error'          "$out" 'No such file or directory'
excludes 'no mangled fragment path'       "$out" '.env.env'
all_point_at 'both extension and extensionless fragments moved' gruvbox

echo
echo "reports the active theme when given no argument"
fixture gruvbox
run
exited 'exits 0' 0
equals 'prints just the theme name' "$out" 'gruvbox'

echo
echo "toggle flips to the other palette"
fixture nord
run toggle
exited   'exits 0'          0
contains 'switches to gruvbox' "$out" 'nord -> gruvbox'
all_point_at 'every link moved' gruvbox

echo
echo "switching to the theme already active is a no-op that still finishes"
fixture gruvbox
run gruvbox
exited   'exits 0'                      0
contains 'says so'                      "$out" 'Already gruvbox.'
contains 'still reaches the advisory'   "$out" 'The flipped symlinks are uncommitted'
contains 'still runs the icon step'     "$out" 'yellow'
all_point_at 'nothing moved' gruvbox

echo
echo "an unknown theme is rejected"
fixture nord
run bogus
exited   'exits 1'      1
contains 'names it'     "$out" "unknown theme 'bogus'"
all_point_at 'nothing moved' nord

echo
echo "a missing sibling aborts before anything is flipped"
fixture nord
rm "$R/foot/.config/foot/colors-gruvbox.ini"
run gruvbox
exited   'exits 1'                   1
contains 'says nothing switched'     "$out" 'missing fragment(s), nothing switched'
contains 'names the absent file'     "$out" 'colors-gruvbox.ini'
all_point_at 'the tree is untouched' nord

echo
echo "palettes defining different roles refuse to switch"
fixture nord
printf 'EXTRA=#ffffff\n' >> "$D/theme-gruvbox.env"
run gruvbox
exited   'exits 1'                   1
contains 'names the two env files'   "$out" 'theme-nord.env and theme-gruvbox.env define different roles'
all_point_at 'the tree is untouched' nord

echo
echo "sway palettes defining different roles refuse to switch"
fixture nord
printf 'set $extra #ffffff\n' >> "$D/colors-gruvbox.conf"
run gruvbox
exited   'exits 1'                   1
contains 'names the two conf files'  "$out" 'colors-nord.conf and colors-gruvbox.conf define different roles'
all_point_at 'the tree is untouched' nord

# ----------------------------------------------------------------- result ---

echo
if [ "$fail" -eq 0 ]; then
    printf 'PASS  %s assertions\n' "$pass"
else
    printf 'FAIL  %s of %s assertions\n' "$fail" "$((pass + fail))"
fi
[ "$fail" -eq 0 ]
