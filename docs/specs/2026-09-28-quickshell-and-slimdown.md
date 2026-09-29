# Quickshell on sway, and slimming the desktop against Omarchy's choices

*Research and decisions, 2026-09-28. Light research (not STORM): one web-research pass on Quickshell
plus a review of this repo and the live machine. Consumer: Xinye. Context: the Omarchy 4 migration
is decided but waiting (`2026-09-25-omarchy-migration-research.md`, D1); this document is not about
whether to migrate. It asks whether a Quickshell shell on the current sway desktop would give an
Omarchy-like unified, lightweight setup, and what can be cut from the current system using Omarchy's
tool choices as the yardstick, without adding tools.*

## Decisions (Xinye, 2026-09-28)

| # | Question | Decision |
|---|---|---|
| Q1 | Build a Quickshell shell on sway now? | **No.** Feasible, but not worth it now (§1–§2) |
| Q2 | Terminal | **Keep kitty, retire foot, no Ghostty** |
| Q3 | GTK look | **Plain Adwaita dark for both palettes**; drop per-palette GTK themes and the papirus tint |
| Q4 | htop / btop | **Keep htop** (package and config); **uninstall btop** |
| Q5 | The smaller cuts | **All taken:** nwg-drawer, the vim package (`EDITOR=nvim`), firewall-applet, eos-welcome, walls-sync and the lock wallpapers, the keyhint rewrite |

What shipped is §3; what is left for a human with `sudo` is §4.

## 1. Quickshell on sway — feasible

Quickshell 0.3.1 is in Arch `extra`. On this machine (sway 1.12, wlroots 0.20, qt6-declarative
6.11.2) every surface Omarchy 4's shell provides has a working module:

| Surface | Module | On sway |
|---|---|---|
| Bar / panels | `PanelWindow` (wlr-layer-shell) | Yes |
| Workspaces, focused output | `Quickshell.I3` ("I3/Sway IPC integration") | Yes |
| Lock screen | `WlSessionLock` (ext-session-lock-v1) | Yes |
| Idle | `IdleMonitor` / `IdleInhibitor` (ext-idle-notify-v1; added in 0.3.0) | Yes |
| Window list | `ToplevelManager` (wlr-foreign-toplevel) | Yes |
| Notifications, tray, audio, media, battery, polkit, network, bluetooth | D-Bus services | Yes; compositor-independent |
| Global shortcuts | `GlobalShortcut` | **No**: Hyprland-only. Every key becomes `bindsym … exec qs ipc call …` |
| Close a popup on an outside click | `HyprlandFocusGrab` | **No**: needs a workaround |
| Per-window thumbnails, blur | `hyprland-toplevel-export`, `BackgroundEffect` | **No** (blur unverified) |

`IpcHandler` plus `qs ipc call <target> <fn>` would cleanly replace the `pkill -RTMIN+N` signals
this repo sends to waybar.

**Maturity:**
- There is no stable-API promise. Both 0.2 and 0.3 shipped breaking changes, and the FAQ promises
  migration guides, not stability.
- Quickshell uses Qt private APIs, so every Qt point release needs a rebuild. When Arch's rebuild
  lags, the bar, notifications, lock and polkit go down together.
- Files are live-reloaded on save, so editing a tracked file in this repo reloads the running
  desktop.

Sources:
- https://quickshell.org/docs/v0.3.1/types/
- https://quickshell.org/changelog/
- https://outfoxxed.me/blog/quickshell-0-3
- https://gitlab.archlinux.org/archlinux/packaging/packages/quickshell/-/issues/2

## 2. …but not worth building now

- **It unifies the shell only.** Omarchy looks unified for two reasons: a theme renderer (one
  colour table rendered into per-app templates), which this repo already has in `palettes.toml` →
  `theme`, and a shell that owns every desktop surface. Quickshell supplies only the second. It
  would have absorbed 5 of the then-19 templates (waybar ×2, mako, fuzzel, nwg-drawer).
  GTK, the terminals, the editors, tmux and yazi are untouched by it.
- **No memory win.**
  - Measured here: waybar, mako, polkit-gnome, swayidle and `waybar_run.sh` total ≈105 MB RSS.
  - The research agent found no clean benchmark for a lean Quickshell bar. Its estimate, labelled
    unmeasured, is 80–150 MB.
  - Full Quickshell shells have leaked badly: Omarchy 4.0.2 hit the out-of-memory killer
    (omacom/omarchy#9897), and Caelestia reached 900 MB in 20 minutes.
  - Noctalia left Qt in v5 over memory.
- **Config surface grows rather than shrinks.** About 520 lines of waybar JSON and CSS would become
  a QML codebase you own: 12 bar modules, the Claude and herdr widgets, a notification UI and a
  lock screen. Omarchy's own shell is ~39,700 lines of QML/JS across 15 plugins.
- **It is not portable, and nothing ready-made fits:**
  - **Omarchy's shell** imports `Quickshell.Hyprland` (bar, workspaces, idle, popups), calls
    `hyprctl` in 6 files and 98 distinct `omarchy-*` scripts, and reads Omarchy's theme state. It
    is useful to read, not to lift.
  - **DankMaterialShell** supports sway and can read an external colour file via
    `customThemeFile`, but it is effectively a whole desktop environment.
  - **Noctalia v5** no longer uses Quickshell.
  - **Caelestia and end-4** are Hyprland-only.
- **The migration plan already adopts Omarchy's shell.** QML written for sway now would be
  discarded if the migration goes ahead.

**Revisit if** the Omarchy migration is dropped and sway stays long-term. Then start with a small
hand-written bar, keeping mako and swaylock, and not with DankMaterialShell. Keep swaylock as the
lock even then: a shell crash must not take the lock with it.

## 3. What shipped (branch `chore/slim-down`)

| Commit | Change | Removed |
|---|---|---|
| `feat(gtk)` | Plain Adwaita dark (`gtk-theme-name=Adwaita` + prefer-dark; there is no `Adwaita-dark` without `gnome-themes-extra`, and naming it renders GTK3 light). `settings.ini` files static; `theme` loses papirus-folders, `--no-icons` and its only `sudo` | 6 templates, `gtk_theme_name`/`papirus_folder`, `.gtkrc-2.0`, `xsettingsd.conf`, 2 AUR packages |
| `chore(foot)` | kitty is the one terminal | foot package, template, consumer check |
| `chore(nwg-drawer)` | fuzzel is the one launcher; the waybar button opens fuzzel; `$mod+Shift+d` unbound | package, template, the last unprefixed `exec_always` |
| `chore(vim)` | `EDITOR`/`VISUAL` = nvim; vim binary kept, unconfigured | package, template, consumer check, §8 plugin clones |
| `chore(sway)` | — | firewall-applet (~40 MB tray icon), eos-welcome autostart |
| `feat(lock)` | Lock over the solid `$desktop` colour the desktop itself shows | `walls-sync` (547 lines), the ~320 MB wallpaper cache's reader |
| `feat(waybar)` | Keybinding list parsed from the sway config at click time, shown in fuzzel from waybar's keyboard icon; tested | `keyhint.sh`, yad |

The net result:
- **Templates:** 19 → 10.
- **Stow packages:** foot, nwg-drawer and vim retired; gtk static.
- **Packages removed from `packages.txt`/`packages-aur.txt`:** foot, nwg-drawer, yad,
  firewall-applet, welcome, nordic-theme, papirus-folders.

**Verification:**
- `theme_test.sh`: 22/22 passing.
- `check_consumers.sh`: all passing.
- `keyhint_test.py`: 11 tests, mutation-checked.
- `check_waybar_paint.py`: now renders under Adwaita, and is mutation-checked to still go red on an
  unscoped `.warning` paint.
- `dim` still clears 4.5:1 on Adwaita's tooltip under both palettes (gruvbox 4.55:1 over white;
  §9.28).

## 4. Left for Xinye (needs `sudo`, or is a deletion outside the repo)

```sh
sudo papirus-folders -D --theme Papirus-Dark      # reset the folder tint BEFORE removing the tool
sudo pacman -Rns btop foot nwg-drawer yad firewall-applet nordic-theme
yay -Rns papirus-folders
rm -rf ~/.themes/Colloid-Yellow-Dark-Gruvbox*     # the hand-installed gruvbox GTK theme
rm -rf ~/Pictures/walls                           # ~320 MB lock-wallpaper cache, now unread
rm -rf ~/.vim                                     # 14 MB of vim plugin clones, now unconfigured
```

**Another existing checkout** (none today; the live one was migrated in place). Deleting a template
does not delete what it rendered, and the six GTK paths are no longer gitignored, so after `git
pull` there, remove the leftovers and dangling links before re-stowing:

```sh
cd ~/repos/dotfiles
rm -f gtk/.config/gtk-{3,4}.0/gtk.css gtk/.config/xsettingsd/xsettingsd.conf gtk/.gtkrc-2.0
git clean -ndX foot nwg-drawer vim     # review, then -fdX: their rendered, ignored outputs
stow -R gtk bin && find ~ ~/.config -maxdepth 3 -xtype l   # remove what points into the repo
```

Optional and not decided: `pacman -Rns welcome` (EndeavourOS's greeter, no longer autostarted), and
`nwg-look`, which has nothing left to set and whose only effect now is §9.1's clobbering.
