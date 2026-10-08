# Focus-safe capture: shoot first, then select — design

**Date:** 2026-10-08 · **Status:** approved in grill · **Scope:** screenshots (region, focused window,
display), OCR, QR and screen recording, from the Print keys and the command palette.

## §0 Background

The screenshot keys could not capture two things Xinye wanted:

- **The waybar claude widget while its tooltip is open.**
- **termtris mid-game.** It pauses on terminal focus loss (`termtris.c:474`: `K_FOCUS_OUT` →
  `pause_game()`), and the pause screen hides the board.

**Cause (from the code, 2026-10-08).** A Print key is a sway binding, so pressing it moves no focus.
The damage is done by **slurp**. `screenshot_region.sh` and `screenshot_window.sh` run `slurp`
first and `grim` only after the selection. slurp's overlay takes the keyboard, so kitty gets
FocusOut and termtris pauses. The overlay also covers waybar (layer `top`), so the pointer leaves
the widget and the tooltip closes. By the time `grim` runs, both are gone.
`screenshot_display.sh` (Shift+Print) never runs slurp and was not affected.

**Fix principle:** capture at the keypress, before anything can change focus. Choose the region
afterwards, on the frozen image.

This was the third pick from the 2026-10-07 Omarchy feature research ("capture extras"). Omarchy 3
used the same grim → satty pipeline.

## §1 Terms

- **Shot** — the full-resolution image `grim` takes at the keypress (`$XDG_RUNTIME_DIR/capture/`).
- **Freeze** — satty opened fullscreen on the shot, so the screen appears frozen while you crop.
- **Focused output / focused window** — sway's `focused` output / container at the keypress.

## §2 Decisions (grill, 2026-10-08)

| # | Question | Decision |
|---|---|---|
| C1 | How to select on the frozen shot | **satty** (Arch `extra`). The shot opens fullscreen with the crop tool; Enter copies and saves; Esc discards. **swappy retires.** Rejected: `wayfreeze` (AUR, 2 votes) + slurp + scale-×2 crop; and selecting on the live screen, where you can't see what you crop |
| C2 | Print bindings | **3 modes.** Print = region (freeze + crop). Ctrl+Print = focused window, instant. Shift+Print = display. **Ctrl+Shift+Print retires**, because Enter in satty already copies |
| C3 | Palette Capture rows | Shoot once the palette's fuzzel has released its lock, plus a short repaint pause, so the palette isn't in the shot. Plus **Capture › Display in 5 s** for re-creating a transient state |
| C4 | Extras | **OCR** (tesseract, English), **QR** (zbarimg), **screen recording** (wf-recorder) |
| C5 | Defaults | One Python tool, `capture.py`, replaces the three `screenshot_*.sh`. Shots go to `~/Pictures/Screenshots/<ts>.png`, recordings to `~/Videos/Recordings/<ts>.mp4`. satty is driven by flags with no config file. Only the focused output is captured. Recordings have no audio. Super+Print toggles recording. OCR and QR are palette-only. waybar signal **10** |

## §3 Architecture

```
Print            → capture.py region      shoot output   → satty --fullscreen --initial-tool crop
Ctrl+Print       → capture.py window      shoot window   → satty --fullscreen
Shift+Print      → capture.py display     shoot output   → satty --fullscreen
Super+Print      → capture.py record-toggle
palette rows     → capture.py <mode> [--after-palette] [--delay 5]

SHOOT (always first, no focus change):
  output: name of the focused output (swaymsg -t get_outputs), grim -o <name> <shot>
  window: rect of the focused node (swaymsg -t get_tree), grim -g "x,y wxh" <shot>
          (logical coordinates: grim applies the scale-2 factor itself)
EDIT:  satty --filename <shot> --fullscreen [--initial-tool crop]
             --output-filename ~/Pictures/Screenshots/<ts>.png --copy-command wl-copy
             --early-exit  (+ Enter = copy + save, per the §6 probe)
OCR/QR: SHOOT output → satty crop → saved crop in the runtime dir → tesseract - / zbarimg --raw
        → text to wl-copy + notification (first line); nothing found → a normal notification
RECORD: slurp (theme colours from theme.gen.env, as today) or the focused output →
        wf-recorder -c h264_vaapi -f ~/Videos/Recordings/<ts>.mp4  (detached)
        pid → $XDG_RUNTIME_DIR/capture/recording.pid ; pkill -RTMIN+10 -x waybar
STOP:   SIGINT the pid (wf-recorder finalises the file) → wait → notification with the path → signal 10
STATUS: capture.py record-status → waybar JSON {"text":"●","class":"recording","tooltip":…} or {"text":""}
```

- **`--after-palette`** (used by the palette rows) waits for the fuzzel instance lock to clear, using
  the same lock as `menu.py`'s `wait_for_fuzzel` (`$XDG_RUNTIME_DIR/fuzzel-$WAYLAND_DISPLAY.lock`,
  ≤ 2 s), then sleeps 150 ms for sway to repaint and hand focus back. Without it the palette window
  would be in the shot. The Print keys never use it.
- **`--delay N`** shows a notification "Capturing in N s" that expires after N−1 s, sleeps N s, then
  shoots.

## §4 Components

| Path | Status | Purpose |
|---|---|---|
| `sway/.config/sway/scripts/capture.py` | new | The tool (§3) |
| `sway/.config/sway/scripts/screenshot_{region,window,display}.sh` | **deleted** | Replaced by `capture.py` |
| `sway/.config/sway/config.d/default` | edit | Print / Ctrl+Print / Shift+Print → `capture.py`; Ctrl+Shift+Print removed; Super+Print → `record-toggle` |
| `sway/.config/sway/menu.toml` | edit | Capture rows (below); `when` hides Record or Stop according to state |
| `waybar/.config/waybar/config`, `style.css` | edit | `custom/recording` (exec `record-status`, `return-type` json, signal 10); `.recording` styled with the `critical` role, no literal hex |
| `tests/capture_test.py` | new | §6 |
| `packages.txt` | edit | + `satty`, `tesseract`, `tesseract-data-eng`, `wf-recorder`; − `swappy` |
| `PLAYBOOK.md` §7, §9 (new: capture), `CLAUDE.md` | edit | Docs |

**Palette rows (Capture group):** Region, Focused window, Display, Display in 5 s, Text from region
(OCR), QR code from region, Record region, Record display, Stop recording. All shot rows pass
`--after-palette`. The record and stop rows use `when = "capture.py record-status --quiet"` (exit 0
while recording) or its negation.

## §5 Error handling

| Situation | Behaviour |
|---|---|
| Esc in satty or slurp | Nothing saved, exit 0, no toast (the palette's §4.2 contract) |
| grim fails, or no focused output/window | Critical notification, exit 1. Window mode with nothing focused shoots the display and says so |
| satty missing | Critical notification naming the package. **Print falls back to `grim -g "$(slurp)" - \| wl-copy`**, so the key still captures (not focus-safe, and the notification says so) |
| tesseract / zbarimg / wf-recorder missing | Critical notification naming the package, exit 1 |
| OCR finds no text, QR finds no code | Normal-urgency notification, exit 0, clipboard untouched |
| Record while recording | `record-toggle` stops it. Palette rows are gated by `when`, so a second recorder is never started |
| Stale pid (recorder died) | `record-status` reports idle and removes the file, so the waybar dot cannot lie |
| Screenshots/Recordings dir missing | Created (`mkdir -p` semantics) |

The runtime shot files are deleted on exit, except the crop OCR/QR reads, which is deleted after reading.

## §6 Testing

**Probe first (`[needs-prototype]`, plan Task 1, after Xinye installs the packages).** Record in the
plan's ledger what satty 0.22 does with:
- `--actions-on-enter` and `--early-exit`
- the exit code on Esc and on window close
- `--fullscreen` on a scale-2 output

and whether `wf-recorder -c h264_vaapi` records on this Intel GPU (otherwise `-c libx264 -p
preset=ultrafast`). `capture.py` is written against the probe's findings, not against this spec's
guesses.

**`tests/capture_test.py`.** Same style as `menu_test.py`: stubs log argv and the order of calls;
throwaway `HOME`/`XDG_RUNTIME_DIR`; nothing reaches the desktop; `CAPTURE_BIN` points it at a copy
for mutation checks.

| # | Asserts |
|---|---|
| K1 | **The bug:** in region, window, display, ocr and qr, grim is called before satty and before any slurp |
| K2 | Window mode passes the focused node's rect to `grim -g`; with no focused window, it shoots the output and notifies |
| K3 | satty gets the shot, the save path under `~/Pictures/Screenshots`, and `--copy-command wl-copy`; the region mode adds `--initial-tool crop` |
| K4 | Esc (satty exits as the probe found, nothing saved) → exit 0, no notification |
| K5 | OCR: text → wl-copy + notification; empty → normal notification, no wl-copy. QR: same, with zbarimg |
| K6 | Record: start writes the pid, signals `-RTMIN+10 -x waybar`; stop sends SIGINT and notifies the path; a stale pid reads as idle and is removed; `record-status` JSON in both states |
| K7 | satty missing → fallback path plus a critical notification; tesseract missing → notification naming it |
| K8 | `--after-palette` waits for a held fuzzel lock before shooting |

**Mutation-checked:** "grim after the picker" must turn K1 red, and dropping the lock wait must turn
K8 red. `menu_test.py`'s rot guard covers the new `menu.toml` rows (every command resolves).

## §7 Rollout

Branch `feat/capture`. Xinye runs `sudo pacman -S satty tesseract tesseract-data-eng wf-recorder`
first; `sudo pacman -Rns swappy` is a post-merge step, because nothing references swappy once the
three scripts are deleted. Apply with `sway --validate` → `swaymsg reload` → the §9.29 checks.

**Manual smoke:**
- Hover the claude widget, press Print, crop: the tooltip is in the image.
- During a termtris game, Ctrl+Print: the bricks are in the image.
- OCR some terminal text.
- Record five seconds and stop.

## §8 Honest caveats

- **What you crop is the freeze, not the live screen.** That is the point, but a video or animation
  keeps running behind satty.
- **Shift+Print and region mode capture the focused output only.** On two monitors, the other one
  needs its own press.
- **Recording is not focus-safe by nature**: slurp's region pick takes focus before recording starts,
  so a game would pause first. Record display (no slurp) avoids that.
- **The satty-missing fallback is the old focus-stealing behaviour**: better than nothing, and the
  notification says so.
- **Shelf life:** like the palette, this retires at the Omarchy migration (D1). Omarchy 4 ships its
  own capture (Omasnap/Tensaku).
