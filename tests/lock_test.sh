#!/bin/sh
# Sandboxed tests for `sway/.config/sway/scripts/lock.sh`'s wallpaper guard.
#
# NEVER runs the real swaylock -- that would lock the live session. A stub
# first on PATH records its argv, one argument per line, and exits.
#
# Point LOCK_BIN at another copy to check the assertions can still fail (the
# gate-fixtures trap, see tp_backup_test.sh).

set -u

LOCK_BIN=${LOCK_BIN:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/sway/.config/sway/scripts/lock.sh}

pass=0; fail=0
ok() { pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
no() { fail=$((fail+1)); printf '  FAIL  %s\n' "$1"; [ $# -lt 2 ] || printf '        %s\n' "$2"; }

sandbox=$(mktemp -d)
trap 'rm -rf "$sandbox"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p "$sandbox/bin"
cat >"$sandbox/bin/swaylock" <<'STUB'
#!/bin/sh
for a in "$@"; do printf '%s\n' "$a"; done >"$ARGS"
STUB
chmod +x "$sandbox/bin/swaylock"
export PATH="$sandbox/bin:$PATH" ARGS="$sandbox/args"

# A colour in the bare spelling lock.sh checks for, built so no literal hex
# sits in this file's source.
c=$(printf '%06x' 1193046)

fresh() {   # fresh HOME ($HOMEDIR, default "home") with a complete env for palette $1 (empty = no PALETTE line)
    rm -rf "$sandbox/home" "$sandbox/ho:me"
    export HOME="$sandbox/${HOMEDIR:-home}"
    mkdir -p "$HOME/.config/sway" "$HOME/Pictures/wallpapers"
    W="$HOME/Pictures/wallpapers"
    {
        for r in BG SURFACE FG FG_BRIGHT ACCENT INDICATOR CRITICAL WARNING SUCCESS DESKTOP; do
            printf '%s=#%s\n' "$r" "$c"
        done
        [ -n "$1" ] && printf 'PALETTE=%s\n' "$1"
    } >"$HOME/.config/sway/theme.gen.env"
}
img() { head -c "${2:-1024}" /dev/zero >"$W/$1"; }   # a file of $2 bytes
run() { : >"$ARGS"; bash "$LOCK_BIN" "$@" </dev/null >/dev/null 2>&1; }
has_image() { grep -qx -- '--image' "$ARGS"; }
expect_image()    { run -f; if has_image; then ok "$1"; else no "$1" "no --image in argv"; fi; }
expect_no_image() { run -f; if has_image; then no "$1" "--image passed: $(grep -A1 -x -- '--image' "$ARGS" | tail -1)"; elif [ -s "$ARGS" ]; then ok "$1"; else no "$1" "swaylock never ran"; fi; }

# 1. the happy path, and the caller's flag still comes last
fresh nord; img a.jpg; ln -s a.jpg "$W/nord"
expect_image "valid slot -> --image"
if [ "$(sed -n '/^--image$/{n;p;}' "$ARGS")" = "$W/nord" ] && [ "$(tail -1 "$ARGS")" = "-f" ] \
   && grep -qx -- '--scaling' "$ARGS"; then ok "image is the slot, --scaling set, caller flag last"
else no "image is the slot, --scaling set, caller flag last" "$(tr '\n' ' ' <"$ARGS")"; fi

# 2. no env file at all -> the bare fail-safe, exactly "-f"
fresh nord; rm "$HOME/.config/sway/theme.gen.env"; img a.jpg; ln -s a.jpg "$W/nord"
run -f; [ "$(cat "$ARGS")" = "-f" ] && ok "no env -> bare fail-safe unchanged" || no "no env -> bare fail-safe unchanged" "$(tr '\n' ' ' <"$ARGS")"

# 3. env from before this change: no PALETTE line
fresh ''; img a.jpg; ln -s a.jpg "$W/nord"
expect_no_image "no PALETTE -> colour lock"

# 4. palette name with a traversal / colon
fresh '../x'; expect_no_image "PALETTE with / -> colour lock"
fresh 'a:b';  img a.jpg; ln -s a.jpg "$W/a:b"; expect_no_image "PALETTE with : -> colour lock"

# 5. slot missing
fresh nord; expect_no_image "missing slot -> colour lock"

# 6. slot is a regular file, not a link
fresh nord; img nord; expect_no_image "slot not a symlink -> colour lock"

# 7. target carries a /
fresh nord; mkdir "$W/sub"; img sub/a.jpg; ln -s sub/a.jpg "$W/nord"
expect_no_image "target with / -> colour lock"

# 8. target is a directory (.. has no slash)
fresh nord; ln -s .. "$W/nord"; expect_no_image "target .. -> colour lock"

# 9. size boundary: 8 MB exactly is rejected, one byte less passes
fresh nord; img big.jpg 8388608; ln -s big.jpg "$W/nord"; expect_no_image "8 MB exactly -> colour lock"
fresh nord; img ok.jpg 8388607; ln -s ok.jpg "$W/nord"; expect_image "8 MB - 1 byte -> --image"

# 10. sibling is itself a symlink out of the folder
fresh nord; head -c 1024 /dev/zero >"$sandbox/outside.jpg"
ln -s "$sandbox/outside.jpg" "$W/a.jpg"; ln -s a.jpg "$W/nord"
expect_no_image "sibling that is itself a link -> colour lock"

# 11. unreadable target
fresh nord; img a.jpg; chmod 000 "$W/a.jpg"; ln -s a.jpg "$W/nord"
if [ "$(id -u)" = 0 ]; then ok "unreadable target (skipped as root)"; else expect_no_image "unreadable target -> colour lock"; fi

# 14. the natural `ln -sfn ~/Pictures/wallpapers/a.jpg …/nord` -- an absolute
# target inside the folder is the same sibling, by string alone
fresh nord; img a.jpg; ln -s "$W/a.jpg" "$W/nord"
expect_image "absolute target inside the folder -> --image"
fresh nord; mkdir "$W/sub"; img sub/a.jpg; ln -s "$W/sub/a.jpg" "$W/nord"
expect_no_image "absolute target in a subfolder -> colour lock"
fresh nord; head -c 1024 /dev/zero >"$sandbox/out.jpg"; ln -s "$sandbox/out.jpg" "$W/nord"
expect_no_image "absolute target outside the folder -> colour lock"

# 12. target is a directory with a plain name (no dots to give it away)
fresh nord; mkdir "$W/d"; ln -s d "$W/nord"; expect_no_image "target is a directory -> colour lock"

# 13. a colon in HOME would split swaylock's [[<output>]:]<path>
HOMEDIR='ho:me' fresh nord; img a.jpg; ln -s a.jpg "$W/nord"
expect_no_image "colon in the slot path -> colour lock"

printf '\nlock_test: %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
