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
#   `colors-nord` without one), just five pairs instead of seventeen.
#
#   PATH is replaced with a stub directory in which swaymsg, sway and makoctl
#   all exit 1, so reload_desktop takes its "sway not running" branch and never
#   reaches `swaymsg reload`. pkill and foot are stubbed for safety rather than
#   for assertions: --restart-terminals runs `pkill -x foot`, and with the real
#   binary on PATH a test would kill the terminals of whoever ran the suite.
#   stdin is /dev/null, so reload_icons takes its "no tty for sudo" branch and
#   prints $PAPIRUS_FOLDER instead of calling sudo — that printed value is the
#   observable proving reload_icons was handed the palette name rather than
#   some other variable's contents.
#
# WHAT THIS PINS
#   The switcher's contract: `.theme` is the single source of truth, the
#   pointers are derived from it and from the fragments on disk, applying is
#   idempotent and repairs damage, and nothing half-applies. Two of these
#   started as real bugs — a switch that needed two invocations, and a flag
#   that was silently discarded — and both have a case here.
#
# NOT COVERED
#   The `[ ! -f "$env_file" ]` guard in reload_icons is unreachable from the
#   CLI (the palette name is validated against $THEMES first). It is a backstop
#   for a future caller, deliberately left untested rather than reached by a
#   contrived edit to the script under test.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPT=${THEME_BIN:-$here/../bin/.local/bin/theme}
REALREPO=$(CDPATH= cd -- "$here/.." && pwd)

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

pointers() {
    printf '%s\n' \
        "$D/theme.env" \
        "$D/colors.conf" \
        "$R/foot/.config/foot/colors.ini" \
        "$R/gtk/.gtkrc-2.0" \
        "$R/mako/.config/mako/colors"
}

# A clone as git would leave it: fragments only. No pointers, no state — the
# state the switcher has to be able to bootstrap from.
fixture_bare() {
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

    for c in swaymsg sway makoctl pkill foot; do
        printf '#!/bin/sh\nexit 1\n' > "$T/stub/$c"
        chmod +x "$T/stub/$c"
    done
    # Silent, so reload_icons sees no active colour and always takes the
    # "would change it" path.
    printf '#!/bin/sh\nexit 0\n' > "$T/stub/papirus-folders"
    chmod +x "$T/stub/papirus-folders"
}

# A tree with a palette already applied: pointers in place and state written.
fixture() { # fixture <applied-theme>
    fixture_bare
    point_at "$1"
    printf '%s\n' "$1" > "$R/.theme"
}

point_at() { # point_at <theme>
    ln -sfn "theme-$1.env"   "$D/theme.env"
    ln -sfn "colors-$1.conf" "$D/colors.conf"
    ln -sfn "colors-$1.ini"  "$R/foot/.config/foot/colors.ini"
    ln -sfn ".gtkrc-2.0-$1"  "$R/gtk/.gtkrc-2.0"
    ln -sfn "colors-$1"      "$R/mako/.config/mako/colors"
}

run() { # run [args...] -> sets $out and $rc
    out=$(HOME=$T PATH=$T/stub:/usr/bin:/bin sh "$SCRIPT" "$@" </dev/null 2>&1) && rc=0 || rc=$?
}

all_point_at() { # all_point_at <desc> <theme>
    bad=""
    for l in $(pointers); do
        t=$(readlink "$l" 2>/dev/null || true)
        case "$t" in
            *"$2"*) ;;
            *) bad="$bad $(basename "$l")->${t:-MISSING}" ;;
        esac
    done
    if [ -z "$bad" ]; then ok "$1"; else no "$1" "not on $2:$bad"; fi
}

state_is() { # state_is <desc> <theme>
    s=$(cat "$R/.theme" 2>/dev/null || true)
    equals "$1" "$s" "$2"
}

# ------------------------------------------------------------------ cases ---

echo
echo "theme_test: $SCRIPT"
echo

echo "a clone with no pointers and no state bootstraps from the fragments"
fixture_bare
run gruvbox
exited   'exits 0'                       0
contains 'creates every pointer'         "$out" 'Applied gruvbox: 5 pointers, 5 updated'
contains 'reload_icons gets the palette' "$out" 'yellow'
excludes 'no missing-file error'         "$out" 'No such file or directory'
all_point_at 'both extension and extensionless pointers exist' gruvbox
state_is 'and the state file is written' gruvbox

echo
echo "one invocation completes the whole switch"
fixture nord
run gruvbox
exited   'exits 0'                       0
contains 'moves every pointer'           "$out" 'Applied gruvbox: 5 pointers, 5 updated'
contains 'reload_icons gets the palette' "$out" 'yellow'
excludes 'no mangled fragment path'      "$out" '.env.env'
all_point_at 'every pointer moved'       gruvbox
state_is 'state follows'                 gruvbox

echo
echo "re-applying the palette already on is idempotent, not a no-op"
fixture gruvbox
run gruvbox
exited   'exits 0'                    0
contains 'says nothing needed doing'  "$out" 'Applied gruvbox: 5 pointers, already correct'
contains 'still runs the icon step'   "$out" 'yellow'
all_point_at 'nothing moved'          gruvbox

echo
echo "re-applying repairs a pointer that was deleted or corrupted"
fixture gruvbox
rm "$R/foot/.config/foot/colors.ini"
ln -sfn colors-nord.ini "$R/mako/.config/mako/colors"
run gruvbox
exited   'exits 0'                  0
contains 'repairs exactly the two'  "$out" 'Applied gruvbox: 5 pointers, 2 updated'
all_point_at 'all consistent again' gruvbox

echo
echo "the state file is the source of truth for the active palette"
fixture gruvbox
run
exited 'exits 0' 0
equals 'reports what .theme says' "$out" 'gruvbox'

# Trees written before .theme existed must keep working, so the pointers are
# the documented fallback — but only the fallback.
fixture_bare
point_at nord
run
exited 'exits 0 with no state file'      0
equals 'falls back to reading a pointer' "$out" 'nord'

fixture_bare
run
exited 'exits 1 with neither'  1
contains 'and says why'        "$out" 'cannot determine the active theme'

echo
echo "toggle flips to the other palette"
fixture nord
run toggle
exited   'exits 0'             0
contains 'switches to gruvbox' "$out" 'Applied gruvbox'
all_point_at 'every pointer moved' gruvbox
state_is 'state follows' gruvbox

echo
echo "a flag with no palette named is refused, not silently ignored"
fixture nord
run --restart-terminals
exited   'exits 1'                     1
contains 'names the ignored flag'      "$out" '--restart-terminals'
contains 'suggests the active palette' "$out" 'theme nord --restart-terminals'
contains 'prints the help page'        "$out" 'theme nord|gruvbox    switch'
all_point_at 'nothing moved'           nord

fixture gruvbox
run --no-icons
exited   'exits 1 for --no-icons too' 1
contains 'names that flag'            "$out" '--no-icons'

fixture nord
run gruvbox --restart-terminals
exited   'the suggested form works'     0
contains 'and reaches the restart step' "$out" 'foot --server restarted'
all_point_at 'having switched'          gruvbox

echo
echo "an unknown palette is rejected"
fixture nord
run bogus
exited   'exits 1'      1
contains 'names it'     "$out" "unknown theme 'bogus'"
all_point_at 'nothing moved' nord
state_is 'state untouched' nord

echo
echo "a fragment with no counterpart aborts before anything is written"
fixture nord
rm "$R/foot/.config/foot/colors-gruvbox.ini"
run gruvbox
exited   'exits 1'                   1
contains 'says nothing applied'      "$out" 'no counterpart, nothing applied'
contains 'names the absent file'     "$out" 'colors-gruvbox.ini'
all_point_at 'the tree is untouched' nord
state_is 'state untouched'           nord

# The other direction: a fragment added for one palette only is invisible to
# nord-driven discovery, so it needs its own check or it would switch cleanly
# and leave that application stranded forever.
fixture nord
: > "$R/mako/.config/mako/extra-gruvbox"
run gruvbox
exited   'an orphan gruvbox fragment is caught too' 1
contains 'naming the missing nord side'             "$out" 'extra-nord'
all_point_at 'the tree is untouched'                nord

echo
echo "palettes defining different roles refuse to switch"
fixture nord
printf 'EXTRA=#ffffff\n' >> "$D/theme-gruvbox.env"
run gruvbox
exited   'exits 1'                   1
contains 'names the two env files'   "$out" 'theme-nord.env and theme-gruvbox.env define different roles'
all_point_at 'the tree is untouched' nord

fixture nord
printf 'set $extra #ffffff\n' >> "$D/colors-gruvbox.conf"
run gruvbox
exited   'exits 1'                   1
contains 'names the two conf files'  "$out" 'colors-nord.conf and colors-gruvbox.conf define different roles'
all_point_at 'the tree is untouched' nord

# ------------------------------------------------------- the real repo ---
#
# The point of the state file is that switching never dirties the tree. That
# only holds if every pointer, and the state file, are actually ignored — and
# that list is maintained by hand in .gitignore, so it is exactly the kind of
# thing that silently falls behind when a themed application is added.
echo
echo "in the real repo, nothing the switcher writes is tracked"
if git -C "$REALREPO" rev-parse --git-dir >/dev/null 2>&1; then
    unignored=""
    tracked=""
    for frag in $(find "$REALREPO" -name .git -prune -o \
                    \( -type f \( -name '*-nord' -o -name '*-nord.*' \) \) -print); do
        case $frag in
            *-nord.*) neutral="${frag%-nord.*}.${frag##*.}" ;;
            *-nord)   neutral="${frag%-nord}" ;;
            *)        continue ;;
        esac
        rel=${neutral#"$REALREPO"/}
        if ! git -C "$REALREPO" check-ignore -q "$rel"; then
            unignored="$unignored $rel"
        fi
        if git -C "$REALREPO" ls-files --error-unmatch "$rel" >/dev/null 2>&1; then
            tracked="$tracked $rel"
        fi
    done
    if [ -z "$unignored" ]; then ok 'every pointer is gitignored'; else no 'every pointer is gitignored' "not ignored:$unignored"; fi
    if [ -z "$tracked" ];   then ok 'no pointer is tracked';       else no 'no pointer is tracked' "still tracked:$tracked"; fi

    if git -C "$REALREPO" check-ignore -q .theme; then ok '.theme is gitignored'; else no '.theme is gitignored'; fi
    if git -C "$REALREPO" ls-files --error-unmatch .theme >/dev/null 2>&1; then
        no '.theme is not tracked'
    else
        ok '.theme is not tracked'
    fi
else
    echo "  --    skipped (not a git work tree)"
fi

# ----------------------------------------------------------------- result ---

echo
if [ "$fail" -eq 0 ]; then
    printf 'PASS  %s assertions\n' "$pass"
else
    printf 'FAIL  %s of %s assertions\n' "$fail" "$((pass + fail))"
fi
[ "$fail" -eq 0 ]
