# Command palette (Super+Space) — design

**Date:** 2026-10-08 · **Status:** approved; amended during planning (2026-10-08 — §3.1 `--group`, §3.3, §5 mako) · **Scope:** one
fuzzel-based palette that searches apps and desktop actions together. OCR/QR/screen recording are
out of scope (a later `menu.toml` addition).

## §0 Background

Omarchy's most-praised feature is its Super+Space menu: one fuzzy palette for apps and system
actions ("the panic button… every other one becomes optional"). Omarchy 4's version lives in its
Quickshell shell and calls `omarchy-*` scripts and `hyprctl`, so nothing of it runs on this sway
desktop. Research for this (2026-10-07, light — two web-research passes, not STORM) ranked it first
of the Omarchy features users value, ahead of the web-app installer, live theming and the Super+K
cheat sheet (which this repo already has as `keyhint.py`).

This desktop's actions are scattered today: `power_menu.sh` (its own fuzzel picker), clipboard and
notification bindings, four screenshot bindings, `keyhint.py` behind a waybar icon, and rare
operations — `theme`, `claude_usage.py --limits-reset`, `tp-backup status` — with no binding at
all, by policy (PLAYBOOK §7: "a binding is for something done often", because a binding for a rare
operation rots silently).

**Shelf life.** The Omarchy migration is decided but deferred
(`2026-09-25-omarchy-migration-research.md`, D1). On migration this palette retires — Omarchy's own
Super+Space replaces it — and `menu.toml` becomes the checklist of personal actions to recreate as
Omarchy menu extensions (`extensions/omarchy-menu.jsonc`). That is why the build is small and
reuses fuzzel rather than a new tool.

## §1 Terms

- **Palette** — the Super+Space window: apps and actions in one fuzzel list.
- **Action** — one `[[action]]` row of `menu.toml`; shown as `<group> › <label>`.
- **Group** — an action's category (System, Capture…); a display prefix and a `--group` filter.
- **Second step** — a further fuzzel pick an action opens: a confirm (No/Yes) or a `choices` pick.
- **Action PATH** — the `PATH` actions run with and are checked against (§3.3).

## §2 Decisions (grill, 2026-10-07/08)

| # | Question | Decision |
|---|---|---|
| G1 | Shape | **Merged palette**, Omarchy-4 style: apps and actions in one search |
| G2 | Key | **Super+Space**. `focus mode_toggle` moves to Super+Alt+Space. **Super+D stays plain fuzzel** as the fallback if the palette breaks. Waybar's launcher icon opens the palette |
| G3 | Structure | **Flat list**, group-prefixed actions; a second fuzzel only for confirm/choices. No submenus |
| G4 | Entries | The full list in §4 |
| G5 | Definitions | **`menu.toml` (data) + `menu.py` (engine)**; `confirm` / `when` / `choices` cover every dynamic case |
| G6 | Failures | **Both layers**: runtime critical notification on non-zero exit, and a test that every command resolves |
| G7 | Approach | **B — actions as generated `.desktop` files**, fuzzel in launcher mode (§3.1); rejected: A, own dmenu list with own `.desktop` parsing |
| G8 | Defaults | Files in the folded `sway` package; `power_menu.sh` retires into `menu.py --group System`; freedesktop icon names (not nerd-font glyphs); own frecency cache; confirm lists "No" first; PLAYBOOK §7 paragraph |

**Why approach B over A.** A reimplements fuzzel's launcher — `.desktop` discovery and override
order, `NoDisplay`/`Hidden`/`OnlyShowIn`, `Exec` field codes, `Terminal=true`, detaching — about
80–100 lines plus their tests. B writes each action as a `.desktop` file and lets fuzzel's launcher
mode, the path Super+D already exercises daily, do all of it, including icons and frecency. The
cost is one trap (environment leak, §3.1), which a flag closes and a test pins. (Planning
amendment, 2026-10-08: `--group` uses a dmenu list instead — §3.1 says why.)

## §3 Architecture

### §3.1 Data flow

```
Super+Space / waybar launcher icon
        │ menu.py
        ▼
  1. load + validate menu.toml   (failure → critical notification, exec plain `fuzzel`)
  2. drop rows whose `when` exits non-zero
  3. prune dead palettes' dirs, then write  $XDG_RUNTIME_DIR/fuzzel-menu/<pid>/applications/menu-<id>.desktop
       Type=Application   Name=<group> › <label>   Icon=<icon>   Keywords=<keywords>;
       Exec=<abs path>/menu.py --run <id>
  4. exec fuzzel
       env XDG_DATA_DIRS=$XDG_RUNTIME_DIR/fuzzel-menu:<original>
       --cache ~/.cache/fuzzel-menu
       --launch-prefix "env XDG_DATA_DIRS=<original>"
        │
        ├─ app picked    → fuzzel launches it (as Super+D does; Terminal=true → `kitty -e`)
        └─ action picked → menu.py --run <id>   (§3.2)
```

- **Environment leak.** Without `--launch-prefix`, every app launched from the palette inherits the
  prefixed `XDG_DATA_DIRS`, so a launcher started from that app would list the palette's actions.
  The prefix restores the original value: the inherited `XDG_DATA_DIRS`, or the spec default
  `/usr/local/share:/usr/share` when it was unset.
- **`--group <G>` (Super+Shift+E, waybar's power button) is a dmenu list, not the `.desktop`
  mechanism.** It shows that group's actions only, no apps. Hiding apps through the environment
  does not work: fuzzel reads `$XDG_DATA_HOME/applications` as well, and narrowing `XDG_DATA_DIRS`
  also hides the icon themes under it, so the picker would lose its icons. Instead `menu.py` pipes
  `<id>\t<label>\0icon\x1f<icon>` rows to `fuzzel --dmenu --with-nth=2 --accept-nth=1` (fuzzel
  1.15 supports icons in dmenu mode via rofi's protocol) and hands the returned id to the same code
  as `--run`. No `--cache`: the power picker keeps its fixed file order, Lock first, as
  `power_menu.sh` has it.
- **Runtime directory.** `$XDG_RUNTIME_DIR` is tmpfs; the directory is rewritten on every press.
  Nothing generated lands in the repo or `~/.local`, nothing is gitignored, nothing goes stale.
- **One directory per palette (post-merge fix, 2026-10-08).** The directory is
  `fuzzel-menu/<pid>`, named for `menu.py`'s pid, which `execve` hands on to fuzzel. A second
  Super+Space therefore never rewrites files a running fuzzel may still be reading. Each press
  prunes the directories of palettes whose pid has exited (and the original shared
  `fuzzel-menu/applications`). Frecency is unaffected: fuzzel keys it by desktop-file id, not path.
- **Lifetime.** `menu.py` `exec`s fuzzel, so no Python process stays resident while the palette is
  open. `--run` is a fresh process per action.
- **Ids** come from `id`, defaulting to the slug of `<group>-<label>`. They name the generated file,
  which is fuzzel's frecency key — an explicit `id` keeps frecency across a label rename.

### §3.2 `menu.py --run <id>`

1. Look up the row (unknown id → critical notification, exit 1).
2. `choices` set → run it; its non-blank stdout lines become a `fuzzel --dmenu` pick. Empty output or
   non-zero exit → critical notification, stop. Esc → stop, exit 0.
3. `confirm = true` → `fuzzel --dmenu` with `No` then `Yes`, prompt `<label>?`. Anything but `Yes`
   → stop, exit 0.
4. Substitute the chosen line for `{choice}` in `run`, shell-quoted.
5. `terminal = true` → `kitty --class menu-term bash -c '<run>; printf "\n[press a key]"; read -rsn1'`
   (bash, for `read -n`),
   no capture. Otherwise `sh -c '<run>'` with the action PATH, stderr captured; non-zero exit →
   critical notification (§5).

### §3.3 The action PATH

The desktop session's `PATH` does **not** contain `~/.local/bin` — only `.bashrc` adds it (measured
2026-10-08: waybar's and mako's environment is `/usr/local/sbin:/usr/local/bin:/usr/bin:…`). So
`theme`, `tp-backup` and `herdr-session-backup`, which work in a terminal, would fail from the
palette, and a rot check run from a terminal would pass regardless.

The action PATH is therefore a **constant**, not derived from whatever `menu.py` inherited:
`$HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/bin`. `run`, `when` and `choices` run with it,
and `--check` resolves against it — so a check run from a terminal (whose `PATH` carries mise shims,
`~/go/bin` and the like) judges exactly what a keypress will see. `menu.py`'s *own* tools
(`fuzzel`, `notify-send`, `kitty`) are looked up on the inherited `PATH`; only actions get the
constant one.

## §4 Components

### §4.1 Files

| Path | Status | Purpose |
|---|---|---|
| `sway/.config/sway/scripts/menu.py` | new | The engine |
| `sway/.config/sway/menu.toml` | new | The actions |
| `sway/.config/sway/scripts/cliphist_pick.sh` | new | The Super+Ctrl+V pipeline, moved out of the binding so the palette and the key share it, and so Esc exits 0 |
| `sway/.config/sway/scripts/power_menu.sh` | **deleted** | Replaced by `menu.py --group System` |
| `sway/.config/sway/config.d/default` | edit | Super+Space, Super+Alt+Space, `$powermenu`, Super+Ctrl+V → `cliphist_pick.sh` |
| `sway/.config/sway/config.d/application_defaults` | edit | `for_window [app_id="menu-term"] floating enable, resize set 50 ppt 50 ppt` |
| `waybar/.config/waybar/config` | edit | `custom/launcher` and `custom/power` on-click → `menu.py` |
| `tests/menu_test.py` | new | §6 |
| `tests/theme_test.sh`, `tests/check_consumers.sh` | edit | Run the suite / the live check |
| `PLAYBOOK.md` §7, `CLAUDE.md` Verify | edit | §7 |
| `PLAYBOOK.md` §4.3 (`$mod+Shift+e` … `power_menu.sh`), §9.4 (Nerd Font icons in `power_menu.sh`) | edit | Repoint at the palette's System group; §9.4's point no longer applies to it (freedesktop icons) |

`sway` is folded, so new files appear without `stow -R`. No new stow package, no template: every
fuzzel invocation, second steps included, reads the rendered `colors.gen.ini`.

### §4.2 `menu.toml` schema

| Key | Req. | Type | Meaning |
|---|---|---|---|
| `group` | ✓ | string | Prefix and `--group` filter |
| `label` | ✓ | string | Text after `›` |
| `run` | ✓ | string | `sh -c` command; `{choice}` substituted when `choices` is set |
| `icon` | | string | freedesktop icon name (resolved in Papirus-Dark, fuzzel's theme). Default `system-run` |
| `id` | | string | `[a-z0-9-]+`, unique. Default: slug of `<group>-<label>` |
| `keywords` | | list of strings | Extra search terms. fuzzel's default search fields omit `Keywords`, so the palette passes `--fields filename,name,generic,keywords` (final-review fix) |
| `confirm` | | bool | No/Yes second step |
| `choices` | | string | Command whose stdout lines are the second-step pick |
| `when` | | string | Shell test; row shown only on exit 0 |
| `terminal` | | bool | Run in a floating kitty that waits for a key |

Schema errors — TOML syntax, unknown key, missing required key, wrong type, duplicate id, `{choice}`
in `run` without `choices` or vice versa — reject the whole file (§5). An unknown key is an error, not
ignored: a typo in `confirm` must not silently turn a guarded reboot into an unguarded one.

**Contract for actions:** an action that opens its own picker must exit 0 when that picker is
cancelled, or Esc raises a false failure notification.

### §4.3 The initial actions

`~` is expanded by `sh -c`. Commands outside `~/.local/bin` are written as paths, so no row depends
on the action PATH except the three `~/.local/bin` tools.

| Group › Label | `run` | Extras |
|---|---|---|
| System › Lock | `~/.config/sway/scripts/lock.sh` | icon `system-lock-screen` |
| System › Suspend | `systemctl suspend` | confirm; `when = '[ "$(systemctl is-enabled suspend.target 2>/dev/null)" != masked ]'` (as `power_menu.sh`) |
| System › Log out | `swaymsg exit` | confirm |
| System › Reboot | `systemctl reboot` | confirm; keywords `restart` |
| System › Reboot to UEFI | `systemctl reboot --firmware-setup` | confirm; keywords `bios`, `firmware` |
| System › Shutdown | `systemctl poweroff` | confirm; keywords `power off` |
| Capture › Region → edit | `~/.config/sway/scripts/screenshot_region.sh` | keywords `screenshot` |
| Capture › Region → clipboard | `… screenshot_region.sh --clipboard` | keywords `screenshot` |
| Capture › Window → edit | `~/.config/sway/scripts/screenshot_window.sh` | keywords `screenshot` |
| Capture › Display → edit | `~/.config/sway/scripts/screenshot_display.sh` | keywords `screenshot` |
| Clipboard › History | `~/.config/sway/scripts/cliphist_pick.sh` | |
| Clipboard › Delete an entry | `~/.config/sway/scripts/cliphist_delete.sh` | |
| Notifications › Toggle Do Not Disturb | `makoctl mode -t do-not-disturb` | keywords `dnd` |
| Notifications › Restore last | `makoctl restore` | see §8 |
| Notifications › Dismiss all | `makoctl dismiss --all` | |
| Windows › Switch window | `~/.config/sway/scripts/window_switcher.sh` | |
| Windows › Toggle gaps | `swaymsg gaps inner current toggle 12` | |
| Keys › Show keybindings | `~/.config/waybar/scripts/keyhint.py` | keywords `cheatsheet`, `shortcuts` |
| Style › Theme… | `theme {choice}` | `choices = "theme --list"` |
| Dev › Claude: limits were reset early | `~/.config/waybar/scripts/claude_usage.py --limits-reset && pkill -RTMIN+8 -x waybar` | confirm (writes state). `-x` is load-bearing (§9.29) |
| Dev › Backups: status | `tp-backup status` | terminal |
| Dev › herdr: back up sessions now | `herdr-session-backup` | |
| Sway › Reload config | `sway --validate -c ~/.config/sway/config && swaymsg reload` | a validation failure surfaces through §5 |
| Sway › Displays: re-apply kanshi | `kanshictl reload` | |

## §5 Error handling

Governing rule (§7, `cliphist_delete.sh`, `lock.sh`): **a broken part must never make the key do
nothing.** Every failure is visible, or degrades to something that still works.

| Failure | Behaviour |
|---|---|
| `menu.toml` missing / unparseable / schema error | Critical notification naming the file and row, then `exec fuzzel` plain — the key still launches apps |
| `menu.py` itself crashes before step 4 | Same fallback: the top level catches, notifies, execs plain fuzzel |
| `when` exits non-zero | Row hidden (intended) |
| `when` hangs past 1 s, or cannot execute (exit 126/127, or `sh` itself missing) | Row **shown** — hiding would be silent rot; a really-broken action then fails loudly |
| `choices` fails or prints nothing | Critical notification; nothing runs |
| Second step dismissed | Nothing runs; exit 0; no notification |
| Action exits non-zero | Critical: summary `Menu: "<label>" failed (<code>)`, body = last 5 stderr lines |
| Unknown `--run` id | Critical notification (only reachable if `menu.toml` changed while the palette was open) |
| `terminal = true` action fails | No notification — its output is on screen |
| App launch fails | **Not caught** — same as Super+D today: no window appears |
| `notify-send` missing / no daemon | Message to stderr; nothing else can be done |

Notifications use `notify-send -u critical -a menu`. They persist until dismissed already:
`mako/.config/mako/colors.gen.tmpl` sets `ignore-timeout=1` + `default-timeout=0` under
`[urgency=high]` (mako's alias for critical, §9.21) — no mako change. Under do-not-disturb they are
invisible but land in history (`$mod+Ctrl+n` restores), like every other notification.

## §6 Testing

**`tests/menu_test.py`** — sandboxed. `fuzzel`, `notify-send`, `kitty`, `swaymsg` are logging stubs
on `PATH` (the fuzzel stub answers from a scripted reply); `HOME` and `XDG_RUNTIME_DIR` are
throwaway. Run by `theme_test.sh` beside `keyhint_test.py`. `MENU_BIN` points it at another copy for
mutation checks, as `TPB_BIN`/`WBR_BIN` do.

| # | Asserts |
|---|---|
| T1 | One `.desktop` per visible row; `Name`/`Icon`/`Keywords`/`Exec` correct; each passes `desktop-file-validate`; a second run removes rows that disappeared |
| T2 | fuzzel gets the prefixed `XDG_DATA_DIRS`, `--cache ~/.cache/fuzzel-menu`, and a `--launch-prefix` restoring the **original** `XDG_DATA_DIRS` (and the default when it was unset) |
| T3 | `when`: exit 1 hides, exit 0 shows, a 2 s sleep shows, a missing binary (127) shows |
| T4 | `--group System`: a `fuzzel --dmenu --with-nth=2 --accept-nth=1` list of only System rows in file order, each carrying its icon; the returned id runs through the `--run` path (confirm included); an unknown group notifies |
| T5 | `confirm`: Yes runs; No and Esc don't; No is listed first |
| T6 | `choices`: the picked line reaches `{choice}` shell-quoted; empty or failing `choices` notifies and runs nothing |
| T7 | A failing action → one critical notification with label, exit code and stderr tail; a succeeding one → none; `terminal` rows go to `kitty --class menu-term` and never notify |
| T8 | A bad `menu.toml` (syntax, unknown key, missing `run`, duplicate id, `{choice}` without `choices`) notifies **and** execs plain fuzzel |
| T9 | **Action PATH trap:** a command present only in `~/.local/bin` resolves for `--run` and `--check` even when the test's own `PATH` lacks it; a command on the test's `PATH` but in none of the action PATH's directories fails `--check` **and** fails at `--run` |
| T10 | **Rot guard:** `menu.py --check` on the **repo's** `menu.toml` passes — the first word of every `run`/`when`/`choices` (after `~` expansion) resolves in the action PATH or is an existing file |

**Mutation-checked** before it is called done: against a broken copy, at least these go red — the
launch prefix removed (T2), the `when` timeout made to hide (T3), the plain-fuzzel fallback removed
(T8), the stderr notification removed (T7), `--check` resolving against the inherited PATH (T9).

**`check_consumers.sh` (live half):** `menu.py --check` against the deployed
`~/.config/sway/menu.toml`; `sway --validate` already runs there.

**Unchanged:** `keyhint_test.py` counts the repo's bind lines, so the new bindings are absorbed;
`check_sway_exec.py` is unaffected (no new `exec` lines).

**Manual smoke (once, by Xinye):** Super+Space → type `reb` → Enter → No → nothing happens.
Super+Space → open Chrome → `tr '\0' '\n' </proc/<pid>/environ | grep XDG_DATA_DIRS` has no
`fuzzel-menu`. Super+Shift+E shows only System rows.

## §7 Deployment

Branch `feat/command-palette`, three commits:

1. **Engine + data:** `menu.py`, `menu.toml`, `cliphist_pick.sh`, `tests/menu_test.py`, the
   `theme_test.sh` hook. Nothing bound — try it as `~/.config/sway/scripts/menu.py`.
2. **Wiring:** bindings (Super+Space, Super+Alt+Space, `$powermenu`, Super+Ctrl+V), the
   `menu-term` rule, waybar on-clicks, delete `power_menu.sh`.
   Apply: `sway --validate -c ~/.config/sway/config` → `swaymsg reload` → `pgrep -xc swayidle` = 1
   and every waybar's `PPid` = the supervisor (§9.29); reload waybar's config the way the supervisor
   expects (never `pkill -x waybar` from a test).
3. **Docs:** PLAYBOOK §7 paragraph (what the palette is; rare operations belong here, not on keys,
   now that failures surface; Super+D is the fallback); `CLAUDE.md` Verify line ("run
   `menu_test.py` after any edit to `menu.py`/`menu.toml`"); `check_consumers.sh` hook;
   `desktop-file-utils` into `packages.txt` (the test needs `desktop-file-validate`; installed, not
   listed).

No new runtime packages.

## §8 Honest caveats

- **App launch failures stay silent** (§5) — identical to Super+D today, and out of scope.
- **`makoctl restore` with an empty history** may exit non-zero, which would raise a false failure
  toast. Implementation checks; if so, the row's `run` absorbs that one exit code.
- **fuzzel's exit status on Esc is undocumented** in the 1.15 man page; `menu.py` treats "no
  selection on stdout" as cancel, whatever the code, and T5 pins it.
- **fuzzel's instance lock (final-review fix).** fuzzel allows one instance per display (flock on
  `$XDG_RUNTIME_DIR/fuzzel-$WAYLAND_DISPLAY.lock`) and holds it until teardown is finished — after
  the palette has already started `menu.py --run`. A second-step fuzzel started in that window
  exits 1 with empty stdout, indistinguishable from Esc by stdout alone, so `--run` and `--group`
  first wait (≤ 2 s) for the lock to clear, and notify if it never does. Verified live: with the
  lock held, `fuzzel --dmenu` exits 1 at once with "fuzzel already running?".
- **Frecency starts empty** — the palette's cache is separate from fuzzel's, so Chrome and kitty
  rise again over a few days. Seeding it from `~/.cache/fuzzel` is possible and not worth the code.
- **`when` costs a process per row per press.** One row uses it today; at ~30 rows with a few
  `when`s this stays in milliseconds. A slow `when` is capped at 1 s by design.
- **Shelf life** (§0): written to be discarded at the Omarchy migration. Its lasting output is
  `menu.toml` as the list of personal actions to port.
