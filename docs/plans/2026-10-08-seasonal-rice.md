# Seasonal Rice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One wallpaper per palette on the desktop and lock screen, gaps and 2px borders as the
everyday layout, and a floating waybar — so a `theme` switch is visible in a still.

**Architecture:** `theme` already binds `{{palette}}`; one templated sway line points `output bg`
at the slot `~/Pictures/wallpapers/<palette>` with `$desktop` as fallback colour. `lock.sh` reads
a new `PALETTE` from `theme.gen.env` and adds `--image` only behind three local guards. Layout and
bar are config edits. The images themselves live outside the repo.

**Tech Stack:** sway 1.12, swaylock 1.8.6, waybar, bash/POSIX sh, Python 3 (`theme`).

**Spec:** `docs/specs/2026-10-08-seasonal-rice-design.md` (read it first). Repo rules: `CLAUDE.md`,
`PLAYBOOK.md`.

## Global Constraints

- Work only in the worktree `~/repos/dotfiles-rice` (branch `feat/seasonal-rice`). `~/repos/dotfiles`
  belongs to a parallel session (PR #45) — never edit, checkout or stash there.
- `lock.sh`: no network, no `set -e`, every path ends in `exec swaylock`; the colour fail-safe
  `exec swaylock "$@"` stays flagless.
- No literal hex outside `palettes.toml` (`check_hex.py`; `tests/` and `docs/` are exempt).
- Never run the real `swaylock` from a test — it locks the live session.
- Never run the worktree's `bin/.local/bin/theme` with the real `HOME`: it reloads the live desktop.
- Image cap: `< 8388608` bytes (8 MB). Slot dir: `$HOME/Pictures/wallpapers`.
- Everyday layout: `gaps inner 8`, `gaps outer 4`, `default_border pixel 2`,
  `default_floating_border pixel 3`; waybar margins 12 left/top/bottom, square corners.

## Review Focus

1. **Slot is a symlink to a symlink** (`nord -> a.jpg`, `a.jpg -> /mnt/x.jpg`) — the bare-name check
   passes, but `[ -f ]` follows the chain into the mount. Expect: colour lock. Test in Task 1 (case 10).
2. **Slot target is `..` or `.`** — no `/`, but a directory. Expect: colour lock. Task 1 (case 8).
3. **`PALETTE` absent** (env rendered before this change, i.e. the live machine between merge and
   the next `theme`). Expect: colour lock, not an error. Task 1 (case 3).
4. **Image exactly 8 MB** — boundary. Expect: rejected (`<` not `<=`). Task 1 (case 9).
5. **`$mod+g` pressed twice** — must return to 8/4, not to 0/0 or 12. Checked by reading sway's
   toggle semantics (`*prop ? 0 : amount`) and live in Task 5.

---

### Task 1: Lock screen image behind the guard (TDD)

**Files:**
- Modify: `sway/.config/sway/theme.gen.env.tmpl`
- Create: `tests/lock_test.sh`
- Modify: `sway/.config/sway/scripts/lock.sh`
- Modify: `tests/theme_test.sh` (run the new suite next to the Python suites, ~line 247)

**Interfaces:**
- Produces: `PALETTE=<name>` in `theme.gen.env`; `lock.sh` passes `--image <slot> --scaling fill`
  immediately before `"$@"` when the guard passes. `LOCK_BIN` overrides the script under test.

- [ ] **Step 1: Add `PALETTE` to the env template.** After the `DESKTOP={{desktop}}` line append:

```sh

# The palette's own name, not a colour: lock.sh builds the wallpaper slot
# ~/Pictures/wallpapers/$PALETTE from it (PLAYBOOK §9.25).
PALETTE={{palette}}
```

- [ ] **Step 2: Write `tests/lock_test.sh`** (stub swaylock records argv one per line):

```sh
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

fresh() {   # fresh HOME with a complete env for palette $1 (empty = no PALETTE line)
    rm -rf "$sandbox/home"; mkdir -p "$sandbox/home/.config/sway" "$sandbox/home/Pictures/wallpapers"
    export HOME="$sandbox/home"
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

printf '\nlock_test: %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
```

- [ ] **Step 3: Run it — expect red.** `sh tests/lock_test.sh` → the two `expect_image` cases and
  the order check FAIL (lock.sh has no image yet); every no-image case passes.

- [ ] **Step 4: Implement in `lock.sh`.** Insert after the colour `for` loop (after line 69), and add
  `"${image[@]}" \` as the line before the final `"$@"`:

```bash
# THE WALLPAPER (§9.25) -- an addition on top of a lock that already works,
# never a precondition for it. ~/Pictures/wallpapers/$PALETTE is a slot: a
# symlink the user points at an image. It is passed only when every check
# below holds, each local and non-blocking; any miss leaves today's colour lock.
#
#   PALETTE is a plain word      no ../ and no ':' -- swaylock reads --image as
#                                [[<output>]:]<path>
#   the slot is a symlink whose  a sibling in this folder, so never inside an
#   target is a bare name        rclone/FUSE mount whose stat could hang
#   that sibling is a regular,   not itself a link out of the folder; and
#   readable file under 8 MB     small, because swaylock decodes it BEFORE the
#                                lock surface exists (main.c load_image)
#
# If swaylock still cannot decode it, load_image() drops the image and locks
# over --color: a second fallback that does not depend on this one.
image=()
walls=$HOME/Pictures/wallpapers
if [[ ${PALETTE-} =~ ^[a-z0-9_-]+$ ]] && [[ $walls != *:* ]] && [ -L "$walls/$PALETTE" ]; then
    target=$(readlink -- "$walls/$PALETTE")
    if [[ -n $target && $target != */* && $target != . && $target != .. ]] \
       && [ ! -L "$walls/$target" ] && [ -f "$walls/$target" ] && [ -r "$walls/$target" ]; then
        size=$(stat -c %s -- "$walls/$target" 2>/dev/null)
        if [[ $size =~ ^[0-9]+$ ]] && (( size < 8388608 )); then
            image=(--image "$walls/$PALETTE" --scaling fill)
        fi
    fi
fi
```

Also update the header comment (lines 5–8): "Plain swaylock over the palette's wallpaper slot, or
the solid $desktop colour when there is none … §9.25 why the image is guarded."

- [ ] **Step 5: Run — expect green.** `sh tests/lock_test.sh` → all pass. `bash -n` the script.

- [ ] **Step 6: Prove it can fail.** For each guard, make a copy with that guard deleted and run
  `LOCK_BIN=/tmp/…/lock-mutant.sh sh tests/lock_test.sh`; each must go red on its case(s):
  palette regex → 4; `[ -L slot ]` → 6; `*/*` → 7; `. ..` → 8 (the `-f` also catches it, so
  expect 8 to stay green — record that as defence in depth, not a gap); `! -L sibling` → 10;
  size → 9. Record which went red in the commit body.

- [ ] **Step 7: Wire into `theme_test.sh`** after the `menu_test.py` line:

```sh
# The lock screen's wallpaper guard (PLAYBOOK §9.25). A stub swaylock only;
# the real one would lock the session. A failure aborts.
sh "$REPO/tests/lock_test.sh" >/dev/null
```

  Run `sh tests/theme_test.sh` → green, including `check_hex` and `check_syntax` over the new env line.

- [ ] **Step 8: Commit** — `feat(lock): the palette's wallpaper slot on the lock screen, behind a local guard`.

### Task 2: Desktop wallpaper slot, everyday gaps and borders

**Files:**
- Modify: `sway/.config/sway/colors.gen.conf.tmpl` (header comment + one line)
- Modify: `sway/.config/sway/config.d/theme` (gaps 30–31, borders 37–38, bg 54–83, smart_borders note)
- Modify: `sway/.config/sway/config.d/default:214-218` (`$mod+g`)

- [ ] **Step 1:** In `colors.gen.conf.tmpl` change the header to "sway's copy of the fourteen theme
  roles, and the wallpaper slot" and append:

```
# Not a colour: the palette's wallpaper slot, a symlink the user owns
# (PLAYBOOK §9.25). Missing is fine -- output bg falls back to $desktop.
set $wallpaper ~/Pictures/wallpapers/{{palette}}
```

- [ ] **Step 2:** `config.d/theme`: `gaps inner 8`, `gaps outer 4`, `default_border pixel 2`,
  `default_floating_border pixel 3`; update the tuning comments' "current" markers. Replace
  `output * bg $desktop solid_color` and its comment block with the slot version:

```
# Background: the active palette's wallpaper slot, ~/Pictures/wallpapers/<palette>
# -- a symlink you point at an image; re-point it to change wallpaper, no repo
# change. $wallpaper comes from colors.gen.conf. If the slot is missing or
# unreadable (fresh clone), sway falls back to the solid $desktop colour: no
# error, `sway --validate` passes (measured 2026-10-08, spec §3 P1).
#
# $desktop stays one shade darker than $bg -- it is the fallback field, the
# letterbox colour, and the lock screen's colour when there is no image.
#
# azote (the GUI wallpaper picker) starts its own swaybg, which paints over
# this -- `pkill swaybg` to undo.
output * bg $wallpaper fill $desktop
```

  Keep the `$desktop` darker-than-`$bg` rationale.

- [ ] **Step 3:** `config.d/default`:

```
    # Gaps off and back on, for when a tile needs every pixel. sway's toggle is
    # `value ? 0 : amount` (sway/commands/gaps.c), so these amounts must match
    # the everyday gaps in config.d/theme or the second press lands elsewhere.
    bindsym $mod+g gaps inner current toggle 8, gaps outer current toggle 4
```

- [ ] **Step 4: Validate in a sandbox** (never the live HOME):

```sh
T=$(mktemp -d); cp -r ~/repos/dotfiles-rice "$T/repo"; rm -rf "$T/repo/.git"
mkdir -p "$T/bin" "$T/.config"; for s in swaymsg sway makoctl kitty; do printf '#!/bin/sh\nexit 1\n' >"$T/bin/$s"; chmod +x "$T/bin/$s"; done
HOME=$T XDG_STATE_HOME=$T/state XDG_CONFIG_HOME=$T/.config PATH=$T/bin:$PATH "$T/repo/bin/.local/bin/theme" gruvbox
ln -s "$T/repo/sway/.config/sway" "$T/.config/sway"
HOME=$T /usr/bin/sway --validate -c "$T/.config/sway/config"; echo "exit=$?"; grep wallpaper "$T/.config/sway/colors.gen.conf"
rm -rf "$T"
```
  Expected: `exit=0`, and `set $wallpaper ~/Pictures/wallpapers/gruvbox`.

- [ ] **Step 5:** `sh tests/theme_test.sh` (keyhint count unchanged — still one `$mod+g` bind line).
- [ ] **Step 6: Commit** — `feat(sway): per-palette wallpaper slot; 8/4 gaps and 2px borders as the everyday layout`.

### Task 3: Floating waybar

**Files:** Modify `waybar/.config/waybar/config` (top-level, near `"width": 45`), `waybar/.config/waybar/style.css` (`window#waybar` comment ~70–75).

- [ ] **Step 1:** Add after `"spacing": 0,`:

```jsonc
    // Floats: 12px off the left, top and bottom edges -- sway's outer 4 + inner 8,
    // so the bar sits in the same channel geometry as the tiles. Square corners
    // to match sway's windows, which cannot be rounded (spec §5).
    "margin-left": 12,
    "margin-top": 12,
    "margin-bottom": 12,
```

- [ ] **Step 2:** In `style.css`, rewrite the "No edge rule needed" comment: the bar now sits on the
  wallpaper, not on `$desktop`; `@bg` is its fill. Keep `border-radius: 0`.
- [ ] **Step 3:** `sh tests/theme_test.sh` (check_syntax parses the JSONC). Commit —
  `feat(waybar): float the bar in the gap geometry`.

### Task 4: Docs

**Files:** `README.md` (lock paragraph ~88–97), `PLAYBOOK.md` §3.1 `desktop` row (178), §4 swaylock
row (270), ~305, §9.25 (1174–), `CLAUDE.md` (`lock.sh` gotcha; "No binaries" convention line; Verify
list gains `sh tests/lock_test.sh`).

- [ ] **Step 1:** §9.25 retitled "The lock screen: the palette's wallpaper, guarded, and never the
  network". Keep the history paragraph; add: the slot, the four guards and why each, the 8 MB cap and
  its basis (decode before lock surface), swaylock's own decode fallback, and the
  `gdk-pixbuf-thumbnailer` timing recipe from spec §9.
- [ ] **Step 2:** The other rows: `desktop` = "the fallback behind the wallpaper slot; the lock colour
  when there is no image". README: same facts, short. CLAUDE.md gotcha: "locks over the palette's
  slot image when the guard passes, else `$desktop`"; convention line: "No binaries. Wallpapers are
  slots in `~/Pictures/wallpapers/<palette>` (symlinks), not here." Add a `lock_test.sh` paragraph
  under Verify in the style of `waybar_run_test.sh`'s.
- [ ] **Step 3:** `sh tests/theme_test.sh`; commit — `docs: wallpaper slots, the lock guard, everyday gaps`.

### Task 5: Ship and verify live (after PR #45 leaves the main checkout)

- [ ] **Step 1:** Push `feat/seasonal-rice` (SSH remote), open the PR, run CodeRabbit; address findings.
- [ ] **Step 2:** Merge only after the parallel session's PR #45 is merged and `~/repos/dotfiles` is
  back on a clean `main`. Then in `~/repos/dotfiles`: `git pull`, `theme` (re-applies the remembered
  palette, renders `PALETTE`), and the CLAUDE.md sway checks: `sway --validate`, `pgrep -xc swayidle`
  = 1 (twice), supervised waybar. `sh tests/check_consumers.sh`.
- [ ] **Step 3: P2** — screenshot; the bar-to-tile gap must equal tile-to-tile gap (12 logical px).
  If not, adjust `margin-right` / gaps and amend spec §5.
- [ ] **Step 4:** `$mod+g` once → tiles flush (screenshot), again → 8/4 restored (screenshot matches Step 3). `$mod+f1` with the slot set → the image lock (the user unlocks with their password).

### Task 6 (user, outside the repo): pick the wallpapers

- [ ] Shortlist provided by Claude (4K, JPEG/WebP, < 8 MB): Nord *summer*, Gruvbox *cold snap*.
- [ ] `ln -sfn <file> ~/Pictures/wallpapers/nord` and `…/gruvbox`; `swaymsg reload`.
