# Sway + Nord: the full playbook

The complete technical reference for this desktop: what it is, how the pieces fit together, and
every way it differs from a stock EndeavourOS Sway install.

This is the document to *read*. For a checklist to *follow* at a terminal, open
[`docs/setup.html`](docs/setup.html) in a browser — same content, structured as steps with
copy buttons and progress that survives a reboot.

---

## 1. Scope and assumptions

Built on and tested against:

| | |
|---|---|
| Distro | EndeavourOS (Arch), **Sway Community Edition** |
| Display manager | greetd |
| Compositor | sway (wlroots, Wayland-only) |
| Audio | pipewire + wireplumber |
| Hardware | Dell laptop, single 3840×2160 internal panel (`eDP-1`), touchpad, lid switch |

The Sway Community Edition matters. It ships an opinionated `~/.config/sway/config.d/` split, a
`scripts/` directory, and a set of chosen applications (foot, fuzzel, mako, nwg-drawer, gtklock,
azote, swappy, cliphist). This playbook is written as a **diff against that**, not against
upstream sway's bare default config. On vanilla Arch + sway you would be starting from
`/etc/sway/config`, and the "what stock does" column below would not apply.

**Not covered:** installing EndeavourOS, greetd configuration beyond one specific fix, NVIDIA,
multi-GPU, or non-Arch distros.

---

## 2. Architecture — how the pieces actually fit

### 2.1 Session startup chain

```
greetd
  └─ sway
       ├─ ~/.config/sway/config          (5 lines; only includes config.d/*)
       │    └─ ~/.config/sway/config.d/*  (read in alphabetical order)
       │         ├─ application_defaults  for_window / assign rules
       │         ├─ autostart_applications exec / exec_always
       │         ├─ default               keybindings, $variables
       │         ├─ input                 touchpad, keyboard, lid switch
       │         ├─ output                displays, scale, workspace pinning
       │         └─ theme                 colours, fonts, gaps, background, bar
       └─ children spawned by exec/exec_always:
            waybar, mako, kanshi, swayidle, foot --server, autotiling,
            nm-applet, cliphist watchers, polkit agent, nwg-drawer
```

**Alphabetical order is load-bearing.** `application_defaults` is read before `default`, and
`theme` last. Anything that must win a conflict belongs in a later-sorted file.

`exec` runs **only at sway startup**. `exec_always` runs at startup *and* on every
`swaymsg reload`. Choosing wrong is the single most common bug in this config — see §6.2 and §9.2.

### 2.2 How GTK theming actually reaches applications

There are four parallel mechanisms, and they do not agree with each other by default:

```
~/.config/gtk-3.0/settings.ini ──┬──> GTK3 apps read this file directly
                                 │
                                 └──> scripts/import-gsettings (exec_always from
                                      config.d/theme) parses it and pushes to:
                                        gsettings org.gnome.desktop.interface
                                          ├─ gtk-theme
                                          ├─ icon-theme
                                          ├─ cursor-theme
                                          ├─ font-name
                                          └─ color-scheme   ← added by us

~/.gtkrc-2.0                    ────>  GTK2 apps (legacy; lxappearance-era)
~/.config/gtk-4.0/settings.ini  ────>  GTK4 apps
~/.config/gtk-4.0/gtk.css       ────>  libadwaita apps  ← the one that matters
~/.config/xsettingsd/           ────>  XSettings protocol, for XWayland clients
```

**The critical thing to understand:** *libadwaita apps ignore `gtk-theme-name` completely.*
Installing the Nordic GTK theme does nothing for them. They read named colours
(`@window_bg_color`, `@accent_bg_color`, …) and decide light vs dark from the gsettings
`color-scheme` key. That is why this repo carries a hand-written
`gtk/.config/gtk-4.0/gtk.css` redefining those colours, and why `import-gsettings` was extended
to set `color-scheme`.

### 2.3 Where the palette lives

There is no central colour file — every application parses its own config format, so the palette is
duplicated by necessity. The full 16 colours are declared in
`waybar/.config/waybar/style.css` as GTK `@define-color` names, which is the closest thing to a
canonical listing. Everywhere else the hexes are inlined with a comment naming the nord index.

---

## 3. The Nord palette

```
Polar Night   nord0  #2E3440    nord1  #3B4252    nord2  #434C5E    nord3  #4C566A
Snow Storm    nord4  #D8DEE9    nord5  #E5E9F0    nord6  #ECEFF4
Frost         nord7  #8FBCBB    nord8  #88C0D0    nord9  #81A1C1    nord10 #5E81AC
Aurora        nord11 #BF616A    nord12 #D08770    nord13 #EBCB8B    nord14 #A3BE8C    nord15 #B48EAD
```

### 3.1 Role convention

**This section is the point of the whole document.** The desktop drifted into four incompatible
palettes because each config was themed ad hoc. Adding anything new means picking from this table,
not choosing a colour that looks nice in isolation:

| Role | Colour | Used by |
|---|---|---|
| Background | `nord0` `#2E3440` | desktop bg, waybar bg, terminal bg, gtklock bg |
| Raised surface | `nord1` `#3B4252` | mako body, popovers, cards, fuzzel-adjacent chrome |
| Selection | `nord2` `#434C5E` | fuzzel selection, terminal selection bg |
| Inactive / muted | `nord3` `#4C566A` | unfocused text, placeholders, separators, calendar weeks |
| Foreground | `nord4` `#D8DEE9` | body text everywhere |
| Bright foreground | `nord6` `#ECEFF4` | focused window title, active text |
| **Focus / accent** | `nord8` `#88C0D0` | sway focused border, waybar focused workspace, GTK accent, fuzzel border |
| Secondary accent | `nord9`/`nord10` | calendar weekdays, gtklock buttons, waybar mode |
| **Urgent / critical** | `nord11` `#BF616A` | urgent window, critical CPU/battery, destructive actions |
| Warning | `nord13` `#EBCB8B` | warning states, "today" in the calendar, idle inhibitor on |
| Success | `nord14` `#A3BE8C` | battery charging, success states |

### 3.2 Nord is not Nordic

A trap worth stating plainly, because this repo previously contained both. **Nordic** is a separate
scheme with a `#242933` background and warm yellow/green accents. **Nord** is `#2E3440` with cool
blue accents. `alacritty-theme` ships `nord.toml`, `nordic.toml`, `nordfox.toml` and
`nord_light.toml` — three of those are wrong for this setup.

**Two exceptions where "Nordic" is nonetheless correct**, and both will look like mistakes later:

- The **GTK theme** is genuinely named `Nordic` (AUR `nordic-theme`). It implements Nord. There is
  no GTK theme called "Nord".
- **papirus-folders** calls its Nord folder colour `nordic`, and rejects `nord` outright with
  *"Unable to find 'nord' color"*. The icons really are Nord — `folder-nordic.svg` is drawn in
  `#5E81AC` (nord10), `#81A1C1` (nord9) and `#ECEFF4` (nord6). Use `-C nordic`.

---

## 4. Package manifest

### 4.1 Required — the setup is broken without these

| Package | Source | Why | Symptom if missing |
|---|---|---|---|
| `sway` `swaybg` `swayidle` | repo | Compositor, background, idle daemon | — |
| `waybar` | repo | The bar | No bar |
| `foot` | repo | Terminal. `$term` is `footclient`; a `foot --server` daemon is exec'd at startup | `$mod+Return` does nothing |
| `fuzzel` | repo | Launcher (`$mod+d`) and the cliphist picker | Launcher and clipboard history dead |
| `mako` | repo | Notifications | Silent desktop |
| `gtklock` | repo | Lock screen. Used by `$mod+f1`, the idle timeout, and before-sleep | **Machine never locks** |
| `nwg-drawer` | repo | App grid (`$mod+Shift+d`), also the waybar launcher button | |
| `grim` `slurp` `swappy` `wl-clipboard` | repo | Screenshots and clipboard | Print bindings dead |
| `cliphist` | repo | Clipboard history | `$mod+Ctrl+v` dead |
| `autotiling` | repo | Splits along the longer axis automatically | Manual `$mod+v`/`$mod+b` for every split |
| `pamixer` `brightnessctl` `playerctl` | repo | Media/brightness keys | Function keys dead |
| `polkit-gnome` | repo | Auth prompts for GUI privilege escalation | GUI admin actions fail silently |
| `stow` | repo | Deploys this repo | |

### 4.2 Added by this setup

| Package | Source | Why |
|---|---|---|
| `nordic-theme` | **AUR** | The GTK2/3/4 Nord theme. `/usr/share/themes/Nordic`. Nothing in the base install provides a Nord GTK theme. |
| `papirus-icon-theme` | repo | Icon theme, referenced by mako, fuzzel and GTK |
| `papirus-folders` | **AUR** | Recolours Papirus folder icons to Nord. Needs `sudo papirus-folders -C nordic -t Papirus-Dark` run once |
| `ttf-jetbrains-mono-nerd` | repo | **The patched Nerd Font.** See §9.4 — the base install has only `ttf-nerd-fonts-symbols`, a symbols-only fallback |
| `kanshi` | repo | Display hotplug profiles |

### 4.3 Deliberately not used

`swaylock` (gtklock does the job and is already themed), `wofi`/`rofi` (fuzzel), `dunst` (mako),
`lxappearance` (GTK3+ only reads settings.ini), `qt5ct`/`qt6ct` (no Qt apps in this setup yet —
add them if that changes, as Qt apps will otherwise ignore the theme entirely).

---

## 5. The stow model

### 5.1 Why `.stowrc` exists

The repo lives at `~/repos/dotfiles`, **not** in `$HOME`. Stow's default `--target` is the parent of
the package directory — here that would be `~/repos`, which is wrong. `.stowrc` pins
`--target=~`. Do not remove it, and do not run stow from another directory.

Stow **exits 0 when it links to the wrong target.** "The config didn't apply" is diagnosed by
looking at where the symlink actually landed, never by exit code:

```sh
ls -la ~/.config | grep <pkg>
readlink -f ~/.config/<pkg>
```

### 5.2 Folded vs unfolded, and why each package is what it is

If the target directory does not exist, stow symlinks the **whole directory** ("folded") and new
files in the package appear with no further action. If it already exists as a real directory, stow
links **file by file** and a newly added file is silently absent until `stow -R <pkg>`.

| Package | Folded? | Reason |
|---|---|---|
| `sway` `mako` `fuzzel` `nwg-drawer` `gtklock` `kanshi` `foot` `waybar` | **Yes** | Nothing writes into these directories. New files appear for free. |
| `alacritty` | **No** | `themes/` is an untracked clone of alacritty/alacritty-theme living inside `~/.config/alacritty`. Folding would put the clone inside the repo. |
| `gtk` | **No** | **nwg-look writes into `~/.config/gtk-{3,4}.0`.** See §9.1. Only specific files are tracked; `bookmarks` is left alone as machine-specific. |

The rule: **never fold a directory that a tool writes into, or that holds untracked content.**
Check which a directory is with `ls -la ~/.config | grep <pkg>` — a symlink means folded, a real
directory means `-R` is required after adding files.

To fold one that isn't: `stow -D <pkg> && rmdir <the now-empty target dirs> && stow <pkg>`.

### 5.3 Adopting an existing config

Stow refuses to replace a real file with a symlink, so an existing config must be moved out of the
way first. The procedure used for all six adopted packages:

```sh
cd ~/repos/dotfiles
mkdir -p <pkg>/.config/<app>
cp -a ~/.config/<app>/. <pkg>/.config/<app>/
diff -r ~/.config/<app> <pkg>/.config/<app>     # verify BEFORE deleting anything
rm -rf ~/.config/<app>
stow -n -v <pkg>                                 # dry run
stow <pkg>
ls -la ~/.config | grep <app>                    # must be a symlink into the repo
```

`stow --adopt` does this in one step but moves files into the package *and* overwrites them with
package contents — fine when the package is empty, dangerous otherwise. The explicit copy is
slower and never surprises you.

**Commit the adopted config verbatim before changing anything.** Otherwise the retheme diff is
indistinguishable from the import, and you lose the ability to see what you actually changed.

---

## 6. Deviations from stock EndeavourOS

The core reference. Each row: what stock does → what this repo does → why → how to check.

### 6.1 Theming

| | Stock | Here | Why |
|---|---|---|---|
| sway borders | Dracula `#6272A4` / `#282A36` / `#F8F8F2` | Nord, `nord8` focus | Consistency; stock clashed with the terminals |
| sway border bg | `bground` == `border` (accent-filled titlebar) | `bground` = `nord0` | The accent belongs on the border, not flooding the title area |
| sway font | `Noto Sans Regular 10` | `JetBrainsMono Nerd Font 10` | Matches bar and launcher; glyph coverage |
| Terminals | *Nordic* (`#242933`) | *Nord* (`#2E3440`) | See §3.2 — different scheme despite the name |
| waybar | `@highlight #685878`, `@base1 #19191e`, literal `orange`/`red` | All 16 Nord colours as `@define-color` | One-off hexes matched nothing else |
| waybar calendar | pastel pink `#ff6699` `#ecc6d9` `#99ffdd` | Nord | Loudest palette break in the setup |
| waybar font | `JetBrainsMono` | `"JetBrainsMono Nerd Font"` | §9.4 |
| mako | Arc blue `#5294e2` on `#404552` | Nord, `nord1` body / `nord8` border | |
| mako icons | `/usr/share/icons/Arc-X-D` | `/usr/share/icons/Papirus-Dark` | **The stock path does not exist** — icons were silently falling back |
| fuzzel | purple/navy `08052bdd`, Dracula selection `44475add` | Nord | Related to nothing else |
| fuzzel font | `JetBrainsMono-Regular` | `JetBrains Mono` | §9.4 — file name vs fontconfig family |
| nwg-drawer | `rgba(38,18,57,.9)` purple | `rgba(46,52,64,.9)` = nord0 | |
| gtklock | 22 MB background image, purple accents | Solid `nord0`, Nord accents | Image moved to `~/Pictures/wallpapers`; a 22 MB binary has no place in a config dir |
| GTK theme | `Arc-Dark` / `Qogir-Dark` | `Nordic` / `Papirus-Dark` | |
| GTK dark hint | `gtk-application-prefer-dark-theme=0` | `=1` | Was `0` while the theme name was a *dark* variant — libadwaita apps rendered light |
| libadwaita | *(nothing)* | `gtk-4.0/gtk.css` + `color-scheme` in gsettings | §2.2 — the only way to reach these apps |
| Wallpaper | 3.3 MB PNG via untracked `~/.azotebg` | `output * bg #2E3440 solid_color` | Native to sway; no loose script, no tracked binary |

### 6.2 Defects fixed

| Defect | Detail | Fix | Verify |
|---|---|---|---|
| **swayidle process leak** | `exec_always swayidle …` re-ran on every reload without killing the previous instance. **40 were alive** when found, all racing to lock the screen | `exec_always pkill -x swayidle; swayidle …` | `pgrep -xc swayidle` → `1`, still `1` after a second reload |
| **No idle locking at all** | Stock had `before-sleep` only — no `timeout` clauses, so an unattended machine never locked or blanked | `timeout 300` lock, `timeout 600` dpms off + resume | Leave it 5 minutes |
| **`XDG_CURRENT_DESKTOP` empty** | greetd doesn't set it; stock imported the *empty* value into systemd and dbus. `xdg-desktop-portal` picks its backend from it, with portal-gtk and portal-wlr both installed — the choice was arbitrary | `systemctl --user set-environment` + `dbus-update-activation-environment`, both `exec_always`. Full fix in §6.4 | `systemctl --user show-environment \| grep XDG_CURRENT` |
| **Undeclared display scale** | `config.d/output` was 100% comments. `eDP-1` runs 3840×2160 at scale 2 by autodetection — worked here, would silently not reproduce elsewhere | `output eDP-1 { scale 2 }` | `swaymsg -t get_outputs` |
| **Unhandled lid switch** | A `Lid_Switch` input exists; nothing bound to it | `bindswitch --reload --locked lid:on/off` | Close the lid |
| **mako icon path** | Points at a directory that does not exist | Papirus-Dark | `notify-send -i firefox test` |
| **waybar workspaces 1–2** | `format-icons` covered `"3"`–`"10"` only; 1 and 2 fell through to the raw name | Added, plus a `default` | Harmless for numeric workspaces; breaks the moment one is renamed |
| **No Nerd Font** | Only the symbols-only fallback was installed; every glyph rendered via fontconfig fallback | `ttf-jetbrains-mono-nerd` | §9.4 |

### 6.3 Added capability

| Addition | Binding / file | Notes |
|---|---|---|
| Workspace back-and-forth | `$mod+Tab`, plus `workspace_auto_back_and_forth yes` | Re-pressing the current workspace's number returns to the previous one |
| Dropdown terminal | `$mod+grave` | `footclient --app-id dropdown`, parked in the scratchpad. `swaymsg … scratchpad show` exits 2 when nothing matches, so `\|\| footclient …` creates it on first press |
| Modal resize | `$mod+r` | vim keys and arrows; `Escape`/`Return` exits. Indicator drawn by waybar's `sway/mode` module |
| Gaps toggle | `$mod+g` | `gaps inner current toggle 12` — for screen sharing and screenshots |
| Screenshot to clipboard | `Ctrl+Shift+Print` | Skips the swappy editor. The three stock Print bindings are untouched |
| Workspace → output | `$mod+Ctrl+Shift+{h,j,k,l}` | **Not** `$mod+Ctrl` — already bound to resize |
| Workspace pinning | `config.d/output` | 1–5 on `eDP-1`; 6–10 prefer an external and fall back. sway ignores a disconnected output name, so it's safe undocked |
| App placement | `config.d/application_defaults` | `assign` (not `for_window … move`) so windows don't flash on the wrong workspace first. X11 apps need `class`, Wayland apps `app_id` |
| Display hotplug | `kanshi` package | `laptop` profile verified; **docked profiles are untested templates** — only one display has ever been attached |

### 6.4 Known-incomplete: `XDG_CURRENT_DESKTOP`

The fix in `autostart_applications` sets the variable in the systemd user manager and the dbus
activation environment. Portals are dbus-activated, so **this is the part that fixes portal backend
selection**. But it does *not* put the variable in sway's own process environment, so plainly-exec'd
children (waybar, mako) still don't see it.

The complete fix is at session start, in `/etc/greetd/config.toml`:

```toml
command = "env XDG_CURRENT_DESKTOP=sway sway"
```

Not applied by this repo: it is system configuration outside `$HOME`, needs root, and cannot be
stowed. Do it by hand on a new machine if you care about the remaining gap.

---

## 7. Keybinding reference

`$mod` is Super. `$left/$down/$up/$right` = `h/j/k/l`. **Bold** = added by this repo.

### Launching
| Key | Action |
|---|---|
| `$mod+Return` | Terminal (`footclient`) |
| **`$mod+grave`** | **Dropdown terminal (toggle)** |
| `$mod+d` | fuzzel launcher |
| `$mod+Shift+d` | nwg-drawer app grid |
| `$mod+n` | thunar |
| `$mod+o` | firefox |
| `$mod+p` | Window switcher |
| `$mod+Shift+e` | Power menu |
| `$mod+f1` | Lock (gtklock) |

### Windows
| Key | Action |
|---|---|
| `$mod+q` | Kill |
| `$mod+{h,j,k,l}` / arrows | Focus |
| `$mod+Shift+{h,j,k,l}` | Move |
| `$mod+f` | Fullscreen |
| `$mod+Shift+space` | Floating toggle |
| `$mod+space` | Focus tiling ↔ floating |
| `$mod+a` | Focus parent |
| `$mod+{v,b}` | Split vertical / horizontal |
| `$mod+{s,w,e}` | Stacking / tabbed / toggle split |
| `$mod+Ctrl+{arrows,hjkl}` | Resize |
| **`$mod+r`** | **Resize mode** |
| **`$mod+g`** | **Gaps toggle** |

### Workspaces
| Key | Action |
|---|---|
| `$mod+{1..0}` | Switch (via `bindcode`, for Azerty compatibility) |
| `$mod+Shift+{1..0}` | Move container to workspace |
| **`$mod+Tab`** | **Back and forth** |
| **`$mod+Ctrl+Shift+{h,j,k,l}`** | **Move workspace to output** |
| `$mod+Shift+minus` / `$mod+minus` | Scratchpad move / show |

### Screenshots & clipboard
| Key | Action |
|---|---|
| `Print` | Region → swappy |
| `Ctrl+Print` | Window → swappy |
| `Shift+Print` | Display → swappy |
| **`Ctrl+Shift+Print`** | **Region → clipboard** |
| `$mod+Ctrl+v` | cliphist picker |
| `$mod+Ctrl+x` | cliphist delete |

### Other
`$mod+Shift+c` reload · `$mod+button4/5` resize floating by scroll · media/brightness keys via
`pamixer`, `playerctl`, `brightnessctl`.

---

## 8. Post-install steps that cannot be stowed

```sh
# Nord-tint the Papirus folder icons (one-off, writes into /usr/share/icons)
sudo papirus-folders -C nordic -t Papirus-Dark

# alacritty colour schemes — an untracked clone; alacritty.toml imports nord.toml from it
git clone https://github.com/alacritty/alacritty-theme ~/.config/alacritty/themes

# vim status bar
git clone https://github.com/itchyny/lightline.vim ~/.vim/pack/plugins/start/lightline

# ~/.bashrc already exists from /etc/skel and stow will not overwrite a real file
mv ~/.bashrc ~/.bashrc.bak && stow bash
```

Optional, if you want the greetd-level environment fix from §6.4, edit `/etc/greetd/config.toml`.

---

## 9. Gotchas and failure modes

### 9.1 nwg-look clobbers the GTK config

`~/.config/nwg-look/config` has all five export toggles set to `true`:
`export-settings-ini`, `export-gtkrc-20`, `export-index-theme`, `export-xsettingsd`,
`export-gtk4-symlinks`.

**Opening nwg-look and clicking Apply rewrites every GTK file this repo tracks.** If it writes in
place, the write flows harmlessly through the stow symlink into the repo and shows up as a git diff.
If it unlinks and recreates, **the stow symlinks are silently destroyed** and the repo quietly stops
being the source of truth. `export-gtk4-symlinks` in particular replaces `~/.config/gtk-4.0/gtk.css`
with a symlink into `/usr/share/themes/` — destroying the libadwaita overrides from §2.2.

nwg-look is not needed at runtime: `settings.ini` is the source of truth and
`scripts/import-gsettings` pushes it to gsettings on every reload. **After ever opening nwg-look:**

```sh
ls -la ~/.config/gtk-3.0/ ~/.config/gtk-4.0/ ~/.gtkrc-2.0
git -C ~/repos/dotfiles status
# if clobbered:
stow -R gtk
```

### 9.2 `exec` vs `exec_always` — two distinct bugs

- **`exec_always` without cleanup leaks processes.** Every reload spawns another copy. This is what
  produced 40 swayidle processes. Any `exec_always` that starts a long-lived daemon needs
  `pkill -x <name>;` in front of it. `pkill -x` matches the exact name — without `-x`, `pkill sway`
  would kill sway itself.
- **`exec` cannot be repaired by a reload.** It only runs at startup, so a fix that uses `exec`
  appears not to work until you log out and back in. This bit the `XDG_CURRENT_DESKTOP` fix during
  development.

Also: `exec export FOO=bar` does nothing. sway runs the command in a subshell that exits
immediately, taking the variable with it. Use `systemctl --user set-environment`.

### 9.3 azote rewrites `~/.azotebg`

The GUI wallpaper picker writes `~/.azotebg` and starts its own `swaybg`, which paints over sway's
native `output bg`. If the background stops being Nord, that's why: `pkill swaybg` and reload.

### 9.4 Font family names vs file names

`fc-match` will happily return *something* for any string, so a wrong font name looks like it works:

```sh
fc-match "JetBrainsMono Nerd Font"    # before installing: falls back to NotoSansMono
```

Two distinct traps:
- **`JetBrainsMono-Regular` is a file-style name**, not a fontconfig family. fuzzel had this. It
  matched by luck. The family is `JetBrains Mono`, with a space.
- **`JetBrains Mono` ≠ `JetBrainsMono Nerd Font`.** The unpatched family has no icon glyphs. waybar,
  `power_menu.sh` and `keyhint.sh` are full of Nerd Font icons; without the patched font they render
  via a fontconfig fallback to `Symbols Nerd Font`. That *works*, which is exactly why it went
  unnoticed — but it is a fallback, not a configuration.

### 9.5 Stow exits 0 having done the wrong thing

Covered in §5.1. Always verify with `readlink -f`, never with `$?`.

### 9.6 config.d ordering

Files are read alphabetically. `theme` sorts last and wins conflicts against `default`. Adding a
file called `zz-local` is a clean way to override anything without editing the tracked files.

### 9.7 The dead waybar keyboard-layout signal

`custom/keyboard-layout` in the waybar config declares `"signal": 1`, meaning it refreshes on
`SIGRTMIN+1`. **Nothing ever sends that signal** — the only `pkill -RTMIN+1 waybar` in the repo is
inside a commented-out layout-toggle example in `config.d/input`. The module still updates on its
30-second `interval`, so this is latent rather than broken. If you ever enable layout switching,
uncomment that example and the module becomes instant.

---

## 10. Troubleshooting

| Symptom | Likely cause | Check / fix |
|---|---|---|
| Config change had no effect | Package unfolded, new file not linked | `ls -la ~/.config \| grep <pkg>`; `stow -R <pkg>` |
| Config change had no effect | Symlink points outside the repo | `readlink -f ~/.config/<pkg>` |
| Change needs a full logout to apply | Used `exec` instead of `exec_always` | §9.2 |
| Screen never locks | swayidle not running, or many are | `pgrep -xc swayidle` — must be exactly `1` |
| Screen locks immediately / repeatedly | Multiple swayidle instances racing | Same check; the `pkill` prefix is missing |
| GTK apps still not Nord | `nordic-theme` not installed | `ls /usr/share/themes/Nordic` |
| *Some* apps still light | libadwaita | §2.2; check `gsettings get org.gnome.desktop.interface color-scheme` → `prefer-dark` |
| GTK theme reverted | nwg-look was opened | §9.1 |
| Boxes instead of icons | Nerd Font missing | `fc-match "JetBrainsMono Nerd Font"` |
| Wrong/blurry scale | Output scale not declared | `swaymsg -t get_outputs` |
| External monitor ignored | kanshi profile doesn't match | `pkill -x kanshi; kanshi` in a terminal and read the error |
| Screen share / file picker misbehaves | Portal backend | `systemctl --user show-environment \| grep XDG_CURRENT`; §6.4 |
| Background reverted to an image | azote | §9.3 |
| Notification icons missing | mako `icon-path` | Must be a directory that exists |
| `$mod+Return` does nothing | `foot --server` not running | `pgrep -a foot` |

### Verification sweep

```sh
sway --validate -c ~/.config/sway/config     # before any reload
pgrep -xc swayidle                            # exactly 1
fc-match "JetBrainsMono Nerd Font"            # not NotoSansMono
swaymsg -t get_outputs                        # scale 2 on eDP-1
gsettings get org.gnome.desktop.interface color-scheme    # 'prefer-dark'
systemctl --user show-environment | grep XDG_CURRENT      # =sway
readlink -f ~/.config/sway ~/.config/waybar ~/.gtkrc-2.0  # all inside the repo
```

Then trigger each themed surface by hand: `$mod+d`, `notify-send test`, `$mod+Shift+d`, the waybar
clock tooltip, `$mod+f1`, thunar, a GTK4 app, `$mod+Return`.
