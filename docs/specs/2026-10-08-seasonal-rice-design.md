# Seasonal rice: per-palette wallpapers, gaps, a floating bar — design

**Date:** 2026-10-08 · **Status:** approved (2026-10-08); amended in planning (§3 P1, §5 `$mod+g`) · **Scope:** make the two-palette desktop *visibly*
two-season: a wallpaper per palette on the desktop and the lock screen, gaps and 2px borders as
the everyday layout, and a floating waybar. The r/unixporn shoot that motivated it (§7) commits
nothing.

## §0 Background

The desktop's best feature is invisible in a still: one `theme <name>` re-renders sway, waybar,
kitty, nvim, tmux, mako, fuzzel and yazi from `palettes.toml`. But with `gaps 0/0` and a solid
`$desktop` field, nothing on screen says *summer* or *cold snap* — the palettes differ only in hex.
The angle for the post is the inversion: **Nord's cool blues for the summer heat, Gruvbox's warm
ambers for the cold snap.**

This partly walks back one 2026-09-28 cut (`2026-09-28-quickshell-and-slimdown.md` Q5: walls-sync
and the lock wallpapers). What that cut objected to was a 547-line downloader and a 320 MB cache
for one lock picture, not an image as such (PLAYBOOK §9.25 says so). This design brings back one
image per palette, chosen by hand, already on disk, and none of the machinery.

**Shelf life.** The Omarchy migration (D1/D4) retires `palettes.toml` and `theme`. Everything here is
small enough to retire with them; the wallpapers themselves carry over.

## §1 Terms

- **Slot** — `~/Pictures/wallpapers/<palette>`: a symlink, owned by the user, naming that palette's
  image. One per palette (`nord`, `gruvbox`). The slot is the contract; the image behind it is taste.
- **Everyday layout** — what the desktop looks like when nobody is taking a screenshot.
- **Presentation gap** — a wider gap (12) set by hand with `swaymsg` for screenshots; not bound.
- **Staging** — arranging the desktop for the shoot (§7). Nothing staged is committed.

## §2 Decisions (Xinye, 2026-10-08)

| # | Question | Decision |
|---|---|---|
| R1 | What lands in the repo? | **Only what is used daily.** Showcase extras (fastfetch etc.) are installed ad hoc for the shoot, never in `packages.txt` |
| R2 | Wallpaper source | **One curated image per palette**, outside the repo (CLAUDE.md: no binaries) |
| R3 | How `theme` picks it | **Per-palette slot symlinks**; sway reads `~/Pictures/wallpapers/{{palette}}` with `$desktop` as fallback colour |
| R4 | Lock screen | **Yes, the same image**, behind a strict guard (§4) |
| R5 | Layout | **`gaps inner 8`, `gaps outer 4`, `default_border pixel 2`**; `smart_borders on` kept |
| R6 | Bar | **Floating, square**: 12px margin on its left, top and bottom |
| R7 | Shot list | Same busy layout in both palettes, one clean shot, an ~8s recording of the switch |

## §3 The wallpaper on the desktop

`sway/.config/sway/colors.gen.conf.tmpl` gains one non-colour line, because it is the one
sway file `theme` renders and `{{palette}}` is already a binding (`bin/.local/bin/theme:117`):

```
set $wallpaper ~/Pictures/wallpapers/{{palette}}
```

`config.d/theme` replaces `output * bg $desktop solid_color` with:

```
output * bg $wallpaper fill $desktop
```

`man 5 sway-output`: *"If the specified file cannot be accessed … a fallback color may be provided
to cover the rest of the output."* So an empty slot — a fresh clone, a deleted image — is today's
desktop, not an error. The extensionless slot name is fine because gdk-pixbuf sniffs content
(it reads `svg`, `webp`, `jpeg`, `png` here; checked via `GdkPixbuf.Pixbuf.get_formats()`).

`$desktop` keeps its jobs: fallback field, lock fallback, and the colour that shows if the image
is letterboxed. The comment block in `config.d/theme` (lines 54–83) is rewritten to describe the
slot rather than the solid field.

**P1, resolved 2026-10-08:** a *missing* slot passes `sway --validate` (exit 0), and live sway spawns
`swaybg -o * -c <desktop>` — colour only, no error. An extensionless symlink to a PNG loads as an
image (`swaybg … -i <slot> -m fill -c <desktop>`).

## §4 The wallpaper on the lock screen

`lock.sh` keeps every existing rule: no network, no `set -e`, every path ends in `exec swaylock`,
the colour fail-safe stays bare. The image is an *addition* after the colour checks pass. It is
passed as `--image "$slot" --scaling fill` only when **all** of these hold, each a local,
non-blocking check:

1. **Palette name is plain** — `PALETTE` (new line in `theme.gen.env.tmpl`, `PALETTE={{palette}}`)
   matches `^[a-z0-9_-]+$`. Rules out `../` and a colon (swaylock reads `--image
   [[<output>]:]<path>`).
2. **The slot is a symlink whose target is a bare filename** — `readlink` (one level, no `-f`)
   returns a name with no `/`. The image is therefore a sibling in `~/Pictures/wallpapers`, which can
   never be inside an rclone/FUSE mount whose `stat` could hang.
3. **The target is a readable regular file under 8 MB** — bounds decode time, which swaylock spends
   *before* the lock surface exists (v1.8.6 `main.c` `load_image()` runs during argument parsing).
   Today's 22 MB EndeavourOS PNG would fail this and lock over the colour — by design.

Any failure: exactly today's invocation. If swaylock itself cannot decode an image that passed,
`load_image()` frees it and returns, and the lock proceeds over `--color` (verified in v1.8.6
source) — a second, independent fallback.

The ring keeps its colours. **Open in implementation:** whether the ring needs `--inside-color`
alpha to stay legible over a busy image; decide by looking at a real lock, not in advance.

## §5 Everyday layout and the bar

- `config.d/theme`: `gaps inner 8`, `gaps outer 4`, `default_border pixel 2`. The tuning comments
  stay; the "current" markers move. `default_floating_border` goes from 2 to 3 so floats still out-
  weigh tiles.
- `$mod+g` becomes **gaps off/on**. sway's toggle is `*prop = *prop ? 0 : amount`
  (`sway/commands/gaps.c:107`), so with a non-zero default it can only toggle *to zero* — the old
  "toggle to 12" reading is impossible once gaps are on. Binding: `gaps inner current toggle 8,
  gaps outer current toggle 4` (the stale `gaps inner 2` comment at `config.d/default:217` goes with
  it). The presentation gap for the shoot is set directly: `swaymsg gaps inner current set 12`.
- waybar `config`: `"margin-left": 12, "margin-top": 12, "margin-bottom": 12`. `style.css`: square
  corners kept (`border-radius: 0`), so the bar matches sway's windows. The bar keeps `@bg`; the
  wallpaper now shows *around* it rather than the bar sitting on `$desktop`.

**[needs-prototype] P2:** the exclusive zone. With a 12px margin, tiles should start 12px (outer 4 +
inner 8) right of the bar. Verify by screenshot that the bar-to-tile gap equals the tile-to-tile
gap; if waybar's exclusive zone excludes the margin, set `margin-right` or adjust.

## §6 Testing

- **New `tests/lock_test.sh`** (sandboxed; `sh`, like its siblings). A logging stub `swaylock`
  first on `PATH`, a throwaway `HOME`, and `lock.sh` run against fixtures. Cases: valid slot →
  `--image`; no env file; bad palette name; slot missing; slot is a regular file not a link;
  target contains `/`; target unreadable; target ≥ 8 MB; target is a directory. Each fallback
  asserts the args equal today's exact invocation. **It never runs the real swaylock** — that
  would lock the live session. Proven able to fail: `LOCK_BIN` points at a copy with each guard
  removed in turn (the `gate-fixtures` trap, CLAUDE.md).
- `theme_test.sh` runs `lock_test.sh`, like the Python suites.
- `check_hex.py` must still pass: `$wallpaper` is a path, `PALETTE` a word.
- Live: `sway --validate`, reload, then the CLAUDE.md sway checks (`pgrep -xc swayidle` = 1,
  supervised waybar); `check_consumers.sh` after the live checkout carries the branch.
- Live verification waits until the main checkout is free: a parallel session holds
  `~/repos/dotfiles` on `fix/palette-race` (PR #45). Development is in the worktree
  `~/repos/dotfiles-rice`.

## §7 The shoot (not committed)

Staging lives in the session scratchpad and installs nothing permanently (`fastfetch`,
`wf-recorder` ad hoc; remove after if wanted). Shots, all at 3840x2160:

1. **Busy, Nord.** ws 1: nvim on `palettes.toml` | fastfetch over termtris mid-game (termtris draws
   with palette indices, `termtris.c:589`, so it re-themes itself). A mako toast naming the palette.
2. **Busy, Gruvbox.** Same layout, `theme gruvbox`, same frame.
3. **Clean.** Wallpaper, bar, Super+Space open on `Style › Theme…`.
4. **The switch.** ~8s `wf-recorder` clip of `theme gruvbox` flipping the live desktop.

The screenshot bindings are being redesigned in a parallel session (satty); the shoot uses
`grim` directly so it does not depend on that outcome.

## §8 Docs

README (the lock-screen paragraph, the "no wallpaper" lines), PLAYBOOK §9.25 (the image is back,
the guard, the 8 MB rule) and §3.1's `desktop` row, CLAUDE.md's `lock.sh` gotcha and its
"two wallpapers" convention line.

## §9 Honest caveats

- The images live outside the repo, so a fresh clone shows the solid colour until the user creates
  the slots. That is the R2 trade, accepted.
- The 8 MB cap is a heuristic for decode latency, not a measurement; a 7 MB PNG still decodes slower
  than a 2 MB JPEG. The test suite's stub cannot measure this; if locks feel slow, time a decode of
  the slot directly (e.g. `time gdk-pixbuf-thumbnailer -s 3840 <slot> /tmp/x.png`) and tighten the cap.
- Gaps cost ~24 physical px per tile edge in daily use. `$mod+g` doesn't remove them; set
  `gaps inner 0` in `config.d/theme` to revert.
