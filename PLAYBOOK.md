# Sway, Nord and Gruvbox: the full playbook

The complete technical reference for this desktop: what it is, how the pieces fit together, and
every way it differs from a stock EndeavourOS Sway install.

It carries **two palettes**, Nord and Gruvbox Dark, and switches between them with one keystroke
(`$mod+Shift+t`, or `theme <name>` at a shell). Nord is the default and the original; Gruvbox was
added by making every colour in the setup a *role* rather than a hex, which is the single change
that most of this document now turns on. §3.3 is the mechanism.

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

Every application parses its own config format, so the palette is still duplicated by necessity —
but it is no longer duplicated *ad hoc*. Each package carries a matched **pair of fragments** and a
theme-neutral **symlink** that the package's main config includes:

```
waybar/.config/waybar/colors-nord.css       one fragment per theme
waybar/.config/waybar/colors-gruvbox.css
waybar/.config/waybar/colors.css  ->  colors-nord.css     tracked symlink; `theme` flips it
```

There are 17 such symlinks, one per colour-bearing file. They are **committed**, so the active
theme is part of the repo's state and `git status` after a switch shows exactly 17 modified
symlinks and nothing else.

Two of the fragment pairs are the canonical listing of the roles:

- **`waybar/.config/waybar/colors-{nord,gruvbox}.css`** — the thirteen roles as GTK
  `@define-color` names. gtklock's and nwg-drawer's fragments define the same thirteen, so a rule
  can be moved between the three files unchanged.
- **`sway/.config/sway/theme-{nord,gruvbox}.env`** — the same thirteen as shell variables, for the
  things that cannot parse CSS: `scripts/screenshot_*.sh`, waybar's `keyhint.sh`, and `theme`
  itself. It also carries the two per-theme names that are *not* colours, `PAPIRUS_FOLDER` and
  `GTK_THEME_NAME`.

sway needs a third copy, `sway/.config/sway/colors-{nord,gruvbox}.conf`, as `set $role` lines: sway
has no shell and cannot source the `.env`. All three must agree, and §3.1 is the authority.

Everything else (foot, fuzzel, mako, alacritty, vim, the GTK settings files) spells the values in
its own key syntax, inside a fragment. **A hex inlined in a main config is now a bug** — it will
survive a theme switch and stand out against everything around it.

---

## 3. The palettes

```
Nord
Polar Night   nord0  #2E3440    nord1  #3B4252    nord2  #434C5E    nord3  #4C566A
Snow Storm    nord4  #D8DEE9    nord5  #E5E9F0    nord6  #ECEFF4
Frost         nord7  #8FBCBB    nord8  #88C0D0    nord9  #81A1C1    nord10 #5E81AC
Aurora        nord11 #BF616A    nord12 #D08770    nord13 #EBCB8B    nord14 #A3BE8C    nord15 #B48EAD
```

```
Gruvbox Dark
Backgrounds   bg0_h  #1D2021    bg0    #282828    bg1    #3C3836    bg2    #504945    bg4 #7C6F64
Foregrounds   fg0    #FBF1C7    fg1    #EBDBB2    fg4    #A89984    gray   #928374
Neutral       red #CC241D  green #98971A  yellow #D79921  blue #458588  purple #B16286  aqua #689D6A  orange #D65D0E
Bright        red #FB4934  green #B8BB26  yellow #FABD2F  blue #83A598  purple #D3869B  aqua #8EC07C  orange #FE8019
```

The two are not interchangeable in temperature. Nord's accent is a cool frost blue with the warning
colour a long way off in yellow; gruvbox's accent *is* the yellow, with warning one hue step away in
orange. Warning states therefore read as **hotter** under Gruvbox rather than as a different colour.
That is a property of gruvbox, not a mistake in the mapping.

### 3.1 Role convention

**This section is the point of the whole document.** The desktop drifted into four incompatible
palettes because each config was themed ad hoc; it now carries two palettes only because every
colour is named by role. Adding anything new means picking a row from this table and supplying
**both** values — never choosing a colour that looks nice in isolation, and never adding a role to
one palette alone (§9.10):

| Role | Nord | Gruvbox | Used by |
|---|---|---|---|
| `bg` | `nord0` `#2E3440` | `bg0` `#282828` | window bg, waybar bg, terminal bg, gtklock bg |
| `surface` | `nord1` `#3B4252` | `bg1` `#3C3836` | mako body, popovers, cards, fuzzel-adjacent chrome |
| `sel` | `nord2` `#434C5E` | `bg2` `#504945` | fuzzel selection, terminal selection bg |
| `muted` | `nord3` `#4C566A` | `bg4` `#7C6F64` | unfocused border and text, placeholders, calendar weeks |
| `fg` | `nord4` `#D8DEE9` | `fg1` `#EBDBB2` | body text everywhere |
| `fg_bright` | `nord6` `#ECEFF4` | `fg0` `#FBF1C7` | focused window title, active text |
| **`accent`** | `nord8` `#88C0D0` | `yellow` `#FABD2F` | sway focused border, waybar focused workspace, GTK accent, fuzzel border |
| `accent2` | `nord10` `#5E81AC` | `neutral orange` `#D65D0E` | focused-inactive border, calendar weekdays, gtklock buttons, waybar mode |
| `indicator` | `nord7` `#8FBCBB` | `aqua` `#8EC07C` | sway split indicator — where the next window will open |
| **`critical`** | `nord11` `#BF616A` | `red` `#FB4934` | urgent window, critical CPU/battery, destructive actions |
| `warning` | `nord13` `#EBCB8B` | `orange` `#FE8019` | warning states, "today" in the calendar, idle inhibitor on |
| `success` | `nord14` `#A3BE8C` | `green` `#B8BB26` | battery charging, success states |
| `desktop` | `#272B33` | `bg0_h` `#1D2021` | the wallpaper-less background, one shade below `bg` |

`desktop` is the one row that is not drawn from the palette on the Nord side: Nord has nothing below
`nord0`, so it is a hand-darkened `nord0`. Gruvbox ships exactly this idea as `bg0_h`, so no
off-palette value is needed there. It earns the exception — the desktop being darker than the window
background is what turns the gaps into visible channels and lets `smart_borders on` be safe.

Two per-theme names in `theme-*.env` are not colours and still have to be chosen per palette:
`GTK_THEME_NAME` (`Nordic` / `Colloid-Yellow-Dark-Gruvbox`) and `PAPIRUS_FOLDER` (`nordic` /
`yellow` — see §3.2).

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

**The parallel gruvbox trap: papirus-folders has no gruvbox colour at all.** `papirus-folders -l`
lists 25 names and gruvbox is not among them, so `PAPIRUS_FOLDER=yellow` in `theme-gruvbox.env` is a
*stand-in*, chosen because gruvbox's signature accent is its yellow. It is the one place in the
setup where the Gruvbox theme is approximated rather than matched. Do not "fix" it by inventing a
hex — papirus-folders only accepts names from its own list.

**The GTK themes are asymmetric too.** Nord's is `Nordic` in `/usr/share/themes` from the AUR;
Gruvbox's is `Colloid-Yellow-Dark-Gruvbox` in **`~/.themes`**, installed by hand (§4.2, §8). Both
names are read out of `theme-*.env` as `GTK_THEME_NAME`, so nothing else needs to know where they
live — but `ls /usr/share/themes` will not find the gruvbox one, and that is not a fault.

### 3.3 Switching

`theme` (`bin/.local/bin/theme` → `~/.local/bin/theme`, bound to **`$mod+Shift+t`**):

```sh
theme                       print the active theme
theme nord | theme gruvbox  switch to a named theme
theme toggle                switch to the other one          <- what the keybinding runs
```

| Flag | Effect |
|---|---|
| `--no-icons` | Skip papirus-folders. It writes into `/usr/share/icons`, so it is the one step that needs `sudo`; this is the flag to use in a script or over ssh |
| `--restart-terminals` | Also `pkill -x foot` and re-exec `foot --server`, applying the palette to the terminal immediately — at the cost of every open shell (§9.11) |

**How it finds what to switch.** It walks the repo for symlinks whose target matches
`*-nord`, `*-nord.*`, `*-gruvbox` or `*-gruvbox.*` and repoints each at its sibling. Nothing is
hardcoded, so adding a themed application means adding two fragments and a symlink and changing no
code. The corollary is the sharp edge: **a themed file not named to that pattern is silently not
switched.** There is no manifest to fall out of step with, and equally no manifest to complain.

The active theme is read back from `sway/.config/sway/theme.env`'s own link target rather than from
a state file, so it cannot disagree with reality.

Before it flips anything it checks that both palettes define the same role names, in
`theme-*.env` and in `colors-*.conf`, and refuses if they differ. That guard exists because of §9.10.

**stow is deliberately not involved.** A `theme-nord` / `theme-gruvbox` pair of stow packages was
the obvious design and is wrong: a second package writing into `~/.config/waybar` forces stow to
**unfold** that directory, and every themed package would lose the "new files appear for free"
property described in §5.2. Flipping a symlink *inside* the package leaves fold state untouched.
This is why §5.2's table is unchanged by the theming work.

**The symlinks are committed.** From a clean tree, a switch leaves exactly 17 modified paths and
nothing else:

```sh
theme gruvbox --no-icons
git -C ~/repos/dotfiles status --short    # 17 lines, every one a symlink
```

Commit them (or `git checkout .`) — leaving them dirty makes every later diff noisy.

**What a switch does *not* update immediately:**

| | Why | Remedy |
|---|---|---|
| foot | No config-reload signal exists (§9.11) | `--restart-terminals`, or log out |
| Running GTK apps | They read `settings.ini` once, at startup (§9.9) | Restart the app |
| Folder icons | papirus-folders needs `sudo`; skipped when there is no tty to prompt on | Run the printed `sudo papirus-folders …` line |

Everything else — sway, waybar, mako, gsettings/libadwaita, nwg-drawer, fuzzel, gtklock, new
terminals, new vim sessions — is live by the time the command returns. `theme` runs
`sway --validate` before `swaymsg reload` and refuses to reload an invalid config.

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
| `Colloid-Yellow-Dark-Gruvbox` | **source** | The GTK theme for the Gruvbox palette, in `~/.themes`. Not a package — see §8 for the two-line install |
| `papirus-icon-theme` | repo | Icon theme, referenced by mako, fuzzel and GTK |
| `papirus-folders` | **AUR** | Recolours Papirus folder icons. `theme` drives it per palette (`nordic` / `yellow`), and it is the one step needing `sudo` |
| `ttf-jetbrains-mono-nerd` | repo | **The patched Nerd Font.** See §9.4 — the base install has only `ttf-nerd-fonts-symbols`, a symbols-only fallback |
| `kanshi` | repo | Display hotplug profiles |
| `nord-vim`, `gruvbox` | **source** | vim colorschemes, cloned into `~/.vim/pack/plugins/start/` — §8. Without them vim still starts; `vim/.vimrc` guards the `source` with `filereadable` |

**Why the gruvbox GTK theme is not the AUR package.** `gruvbox-gtk-theme-git` depends on
`gtk-engine-murrine`, which on a current Arch pulls in a **from-source `gtk2` build** — and gtk2 is
not installed here, nor wanted for one theme. `vinceliuice/Colloid-gtk-theme` has a gruvbox tweak
that produces the same result, installs into `~/.themes` without root, and needs no engine.

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
| `htop` | **Yes** | Nothing else writes into `~/.config/htop`. Note htop rewrites `htoprc` *itself* on exit, so settings changed in its UI arrive as a git diff through the symlink — that is the folded behaviour working, not a fault. |
| `alacritty` | **No** | `themes/` is an untracked clone of alacritty/alacritty-theme living inside `~/.config/alacritty`. Folding would put the clone inside the repo. |
| `gtk` | **No** | **nwg-look writes into `~/.config/gtk-{3,4}.0`.** See §9.1. Only specific files are tracked; `bookmarks` is left alone as machine-specific. |
| `bin` | **No** | `~/.local/bin` is a real directory holding untracked binaries — `claude`, `coderabbit` (104 MB), `herdr` (22 MB), `uv`. Folding would pull all of it into the repo. A newly added script therefore needs `stow -R bin`. |
| `vim` | **No** | `~/.vim` holds untracked plugin clones (`lightline`, and now `nord-vim` and `gruvbox`), so folding would pull them into the repo. A newly added file in the package — such as a future theme fragment — is silently absent until `stow -R vim`. That is exactly the trap this section exists to document. |

The rule: **never fold a directory that a tool writes into, or that holds untracked content.**
Check which a directory is:

```sh
[ -L ~/.config/waybar ] && echo folded || echo unfolded
```

Use the `[ -L ]` test, not `ls -la ~/.config | grep -E ' waybar$'`. `ls` renders a symlink as
`waybar -> ...`, so a `$`-anchored grep matches only the **unfolded** case — the command prints
nothing and silently "passes" exactly when folding is healthy, and prints a line exactly when it is
broken. The anchored form shipped in this plan's own verification step and had to be corrected.

To fold one that isn't: `stow -D <pkg> && rmdir <the now-empty target dirs> && stow <pkg>`.

**The theming work did not change a single row of this table, by design.** Each theme fragment and
its symlink live *inside* the package that owns them, so switching writes into the repo, never into
`~/.config`. The alternative — a `theme-nord` / `theme-gruvbox` pair of stow packages — would have
put a second package's files into `~/.config/waybar`, `~/.config/foot` and the rest, forcing stow to
unfold every one of them and costing all seven themed folded packages their "new files appear for
free" property in exchange for nothing. See §3.3.

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
| sway borders | Dracula `#6272A4` / `#282A36` / `#F8F8F2` | `$accent` focus, `$accent2` focused-inactive, `$muted` unfocused | Consistency; stock clashed with the terminals. Role names, so both palettes get the same ladder |
| sway border bg | `bground` == `border` (accent-filled titlebar) | `bground` = `$bg` | The accent belongs on the border, not flooding the title area |
| sway font | `Noto Sans Regular 10` | `JetBrainsMono Nerd Font 10` | Matches bar and launcher; glyph coverage |
| Terminals | *Nordic* (`#242933`) | *Nord* (`#2E3440`) | See §3.2 — different scheme despite the name |
| waybar | `@highlight #685878`, `@base1 #19191e`, literal `orange`/`red` | The thirteen roles as `@define-color`, from a switchable fragment | One-off hexes matched nothing else, and named roles are what make two palettes possible |
| waybar calendar | pastel pink `#ff6699` `#ecc6d9` `#99ffdd` | `$accent2` weekdays, `$warning` today, `$muted` week numbers | Loudest palette break in the setup. The weekday colour moved nord9 → nord7 in the role rewrite — the one deliberate visual change on the Nord side |
| waybar font | `JetBrainsMono` | `"JetBrainsMono Nerd Font"` | §9.4 |
| mako | Arc blue `#5294e2` on `#404552` | `$surface` body / `$accent` border | |
| mako icons | `/usr/share/icons/Arc-X-D` | `/usr/share/icons/Papirus-Dark` | **The stock path does not exist** — icons were silently falling back |
| fuzzel | purple/navy `08052bdd`, Dracula selection `44475add` | `$bg` / `$sel` / `$accent` border | Related to nothing else |
| fuzzel font | `JetBrainsMono-Regular` | `JetBrains Mono` | §9.4 — file name vs fontconfig family |
| nwg-drawer | `rgba(38,18,57,.9)` purple | `@bg` with alpha | |
| gtklock | 22 MB background image, purple accents | Solid `@bg`, role-named accents | Image moved to `~/Pictures/wallpapers`; a 22 MB binary has no place in a config dir |
| GTK theme / icons | `Arc-Dark` / `Qogir-Dark` | `Nordic` or `Colloid-Yellow-Dark-Gruvbox`, `Papirus-Dark` | Per palette, from `GTK_THEME_NAME` in `theme-*.env` |
| GTK dark hint | `gtk-application-prefer-dark-theme=0` | `=1` | Was `0` while the theme name was a *dark* variant — libadwaita apps rendered light |
| libadwaita | *(nothing)* | `gtk-4.0/gtk.css` + `color-scheme` in gsettings | §2.2 — the only way to reach these apps |
| Wallpaper | 3.3 MB PNG via untracked `~/.azotebg` | `output * bg $desktop solid_color` | Native to sway; no loose script, no tracked binary |

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
| **Cursor theme never resolved** | The name was written `Qogir-dark` in 13 places; the directory is `/usr/share/icons/Qogir-Dark`. XCursor resolves by **case-sensitive path**, so it silently fell back to the default cursor everywhere | `Qogir-Dark` throughout, plus `seat * xcursor_theme` and `~/.icons/default/index.theme` so it reaches XWayland and the compositor cursor too | `ls -d /usr/share/icons/Qogir-dark` errors, `-Dark` does not — that one letter was the whole bug |
| **Dangling GTK2 include** | `.gtkrc-2.0` ended with `include "/home/xinye/.gtkrc-2.0.mine"` — a file that has never existed on this machine | Line dropped | `grep -rl gtkrc-2.0.mine ~/repos/dotfiles --exclude-dir=.git --exclude-dir=docs` → nothing but this file |
| **Stale, untracked xsettingsd** | `~/.config/xsettingsd/xsettingsd.conf` was untracked and still named `Arc-Dark` / `Qogir-Dark`, disagreeing with `settings.ini`. **xsettingsd is not running**, which is exactly why the drift was invisible | Tracked in the `gtk` package, per-theme, generated from the same names as everything else | `readlink -f ~/.config/xsettingsd/xsettingsd.conf` is inside the repo |
| **alacritty depended on an untracked clone** | Its palette was imported from `~/.config/alacritty/themes`, so the repo alone did not describe the colours | Self-contained `colors-{nord,gruvbox}.toml` fragments; the clone is now optional | The only `import` in `alacritty.toml` is `~/.config/alacritty/colors.toml` |
| **Cancelled screenshot ran anyway** | `grim -g "$(slurp)"` — pressing Escape gave slurp a non-zero exit and an empty string, and grim was handed an empty geometry | `scripts/screenshot_region.sh` captures slurp's exit status and bails | `Print`, then Escape: nothing is written and swappy does not open |

### 6.3 Added capability

| Addition | Binding / file | Notes |
|---|---|---|
| Workspace back-and-forth | `$mod+Tab`, plus `workspace_auto_back_and_forth yes` | Re-pressing the current workspace's number returns to the previous one |
| Dropdown terminal | `$mod+grave` | `footclient --app-id dropdown`, parked in the scratchpad. `swaymsg … scratchpad show` exits 2 when nothing matches, so `\|\| footclient …` creates it on first press |
| Modal resize | `$mod+r` | vim keys and arrows; `Escape`/`Return` exits. Indicator drawn by waybar's `sway/mode` module |
| Gaps toggle | `$mod+g` | `gaps inner current toggle 12` — for screen sharing and screenshots |
| Screenshot to clipboard | `Ctrl+Shift+Print` | Skips the swappy editor. All four Print bindings now go through `scripts/screenshot_*.sh`, which theme the slurp selection box and bail out when the selection is cancelled — §6.2, §9.13 |
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
| **`$mod+Shift+t`** | **Toggle Nord ↔ Gruvbox (`theme toggle`, §3.3)** |

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
# Tint the Papirus folder icons (writes into /usr/share/icons, so root).
# `theme` re-runs this on every switch when the colour differs; this is just
# the first one. nordic for Nord, yellow for Gruvbox — see §3.2.
sudo papirus-folders -C nordic -t Papirus-Dark

# The Gruvbox GTK theme. Not a package: see §4.2 for why not the AUR one.
# NEVER add -l/--libadwaita — it overwrites ~/.config/gtk-4.0/gtk.css, which is
# precisely the nwg-look failure mode of §9.1.
git clone https://github.com/vinceliuice/Colloid-gtk-theme /tmp/colloid
cd /tmp/colloid && ./install.sh -d ~/.themes -c dark -s standard -t yellow --tweaks gruvbox

# vim: status bar, and one colorscheme per palette
git clone https://github.com/itchyny/lightline.vim ~/.vim/pack/plugins/start/lightline
git clone https://github.com/arcticicestudio/nord-vim ~/.vim/pack/plugins/start/nord-vim
git clone https://github.com/morhetz/gruvbox   ~/.vim/pack/plugins/start/gruvbox

# The theme switcher, so `theme` and $mod+Shift+t work
stow bin

# ~/.bashrc already exists from /etc/skel and stow will not overwrite a real file
mv ~/.bashrc ~/.bashrc.bak && stow bash
```

**Optional now, not required:**

```sh
# alacritty's palette is self-contained since the two-palette work. This clone
# is only worth having if you want other schemes to hand.
git clone https://github.com/alacritty/alacritty-theme ~/.config/alacritty/themes
```

Also optional: the greetd-level environment fix from §6.4, in `/etc/greetd/config.toml`.

`bin` is **not** folded (§5.2), so a script added to the package later needs `stow -R bin` before it
appears on `PATH`.

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

**Two `exec_always` lines here lack the `pkill` prefix**, and they do not behave the same way:

```
exec_always nwg-drawer -r -c 7 -is 90 …      # single instance in practice
exec_always --no-startup-id foot --server    # single: a 2nd server cannot bind the socket
```

`nwg-drawer -r` is resident mode and stays at one process across reloads (`pgrep -xc nwg-drawer`
→ `1` after 15 hours and many reloads).

`foot --server` is safe for a different and stronger reason: **it cannot double-start.** The second
instance fails to bind the socket and exits immediately:

```
$ foot --server
 err: server.c:589: /run/user/1000/foot-wayland-1.sock is already accepting connections;
      is 'foot --server' already running
```

So a reload spawns a process that dies on the spot. This is not the swayidle shape.

**Two `foot --server` processes can nonetheless be alive at once, and that is not a leak.**
`pkill -x foot` — which `theme --restart-terminals` runs — makes the old server release its
listening socket, but it stays up serving the windows already attached to it and exits when the last
one closes. A replacement server then takes the socket. During that overlap `pgrep -a foot` shows
two, the older one holding real memory and an open `foot-wayland-shm-buffer-pool`. It is draining,
not orphaned. Distinguish them by which owns the socket:

```sh
pgrep -a foot                                  # more than one --server?
ls -l $XDG_RUNTIME_DIR/foot-wayland-1.sock     # its mtime marks the live one
```

**Do not add `pkill -x foot` to the `exec_always` line.** It is unnecessary — nothing leaks — and it
would kill every open terminal on every `swaymsg reload`. That destructiveness is precisely why
`theme --restart-terminals` is opt-in.

### 9.3 azote rewrites `~/.azotebg`

The GUI wallpaper picker writes `~/.azotebg` and starts its own `swaybg`, which paints over sway's
native `output bg`. If the background stops matching the palette, that's why: `pkill swaybg` and
reload.

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

### 9.8 Border and gap changes do not fully apply on reload

Three separate surprises, all hit while tuning the borders:

- **`default_border` only affects windows created after the reload.** Existing windows keep the
  width they were born with, so a reload looks like it did nothing. Fix them in place:
  ```sh
  swaymsg '[title=".*"] border pixel 2'
  ```
- **Runtime `gaps` changes survive `swaymsg reload`.** Once you run `swaymsg gaps inner all set 20`,
  that value sticks for existing workspaces; the config line only sets the default for new ones.
  Reloading will *not* put it back. Reset explicitly:
  ```sh
  swaymsg gaps inner all set 8 && swaymsg gaps outer all set 4
  ```
  This makes live experimentation safe *and* confusing — you can end up convinced the config file
  is being ignored.
- **`smart_borders on` hides borders when a workspace holds one window** — which is precisely when
  a maximised window and the bar most need distinguishing. Set to `off`.

For a single window on a workspace, the visible margin is `outer + inner` (with `outer 4 inner 8`,
measured 12 px on all sides).

### 9.9 GTK apps need restarting after a theme change

GTK3 apps read `settings.ini` at startup. A long-running app keeps its old theme indefinitely — a
Thunar started before the retheme was still rendering light a day later, while a freshly launched
GTK3 app picked up Nordic correctly. Diagnose by launching a *different* GTK3 app that was not
already running; if the new one looks right, nothing is broken:

```sh
thunar -q && thunar &        # Thunar runs as a daemon; -q is the way to stop it
```

This is also what `theme` means by "already-running GTK apps keep the old theme". It is not a bug in
the switcher and there is nothing it can do about it.

### 9.10 An undefined GTK colour renders black, silently

The single nastiest failure mode of the two-palette model, and the reason `theme` has a
pre-flight check at all.

GTK CSS resolves `@name` at parse time. If the name is not defined, **the rule takes black** and
nothing is logged — no warning on stderr, no fallback to the previous value, no visual hint that a
name is involved. A widget simply turns black, which reads as a rendering bug rather than a missing
definition. On a `#2E3440` bar a black region is easy to miss entirely.

The way to produce it is to add a role to one palette and forget the other, so `theme` refuses to
switch when `theme-nord.env` and `theme-gruvbox.env` (or the two `colors-*.conf`) do not define
exactly the same names:

```
theme: theme-nord.env and theme-gruvbox.env define different roles
```

That is the guard working. Add the role to *both* fragments and it goes away. The same discipline
applies to the four GTK CSS fragments — waybar, gtklock, nwg-drawer, and `gtk-{3,4}.0/gtk.css` —
which the check cannot cover, because it reads the shell and sway copies.

Related: **a raw hex in an application config is now a bug**, not a style choice. It will survive a
switch and sit there in the wrong palette. §2.3 lists where values are allowed to live.

### 9.11 foot cannot be told to re-read its colours

foot has **no config-reload signal.** `SIGUSR1` and `SIGUSR2` look like one and are not: they toggle
between the `[colors-dark]` and `[colors-light]` blocks *that were loaded at startup*. Sending them
after editing the config does nothing new.

**The rejected trick, recorded so it is not re-proposed:** park Nord in `[colors-dark]` and Gruvbox
in `[colors-light]`, then switch with `SIGUSR1`. It works, and it was still rejected twice over —
it caps the setup at exactly two themes forever, and it makes the config lie, with a dark palette
declared as the light one. Restarting the server is the honest answer:

```sh
theme gruvbox --restart-terminals    # pkill -x foot; foot --server
```

That costs every open shell, so it is opt-in rather than the default. Without it, existing terminals
and the running server keep the old palette until the next login.

Separately: **foot's plain `[colors]` section is deprecated** and warns on every launch. The
fragments use `[colors-dark]`. With no `[colors-light]` block defined anywhere, foot picks
`[colors-dark]` unconditionally, which is what makes the section name a formality rather than a
light/dark switch.

### 9.12 waybar's `include` is overridden by the *including* file

Backwards from every other config format in this setup. In waybar, a key defined in `config` **wins**
over the same key coming from an `"include"`, regardless of where the `"include"` line sits.

So moving the clock's colours into `colors.json` while leaving a `"clock"` object behind in `config`
does not merge them — the `config` copy silently wins and the fragment has no effect at all. The
`clock` module had to be **deleted from `config` entirely** and defined only in the fragment. The
symptom is a module that ignores the theme while every other module switches correctly.

### 9.13 sway `$variables` cannot cross `config.d` ordering

`config.d/*` is read alphabetically (§9.6), so `default` — which holds the keybindings — is parsed
**before** `theme`, which is where `include ../colors.conf` defines the palette. A `$role` used in a
binding in `default` is therefore not yet defined, and sway rejects the whole config:

```
Invalid border color $accent
```

This is why the screenshot bindings call `scripts/screenshot_region.sh` instead of inlining
`slurp -c $accent`: the script sources `~/.config/sway/theme.env` at *runtime*, sidestepping parse
order completely. Any future binding that needs a colour should do the same rather than move files
around to fix the sort order.

### 9.14 Moving a config block wholesale loses whatever stayed behind

When the waybar clock moved into the colour fragment, its `actions` block — scroll to shift the
calendar month — was left in the old file and dropped. **Every check in this repo still passed**:
`sway --validate` does not read waybar's config, the JSON stayed valid, waybar started clean, and
the clock rendered correctly. Only scrolling on it revealed the loss.

This repo's verification is entirely syntactic. There is no test that a feature still exists. When
relocating a block, diff the *old* block against the new one key by key before deleting it —
`git show HEAD:path/to/file` is the cheap way to get the old text back.

### 9.15 `bash -lc` does not read `.bashrc`

Line 6 of `bash/.bashrc` is the stock Arch guard:

```sh
[[ $- != *i* ]] && return
```

A login-but-not-interactive shell returns there, so **everything below it — the prompt, `LS_COLORS`,
mise, starship — is skipped**. Testing a change with `bash -lc '…'` shows an unthemed shell and
looks like the change did not land. Use `bash -ic '…'` for anything sourced from `.bashrc`.

---

## 10. Troubleshooting

| Symptom | Likely cause | Check / fix |
|---|---|---|
| Config change had no effect | Package unfolded, new file not linked | `[ -L ~/.config/<pkg> ] && echo folded \|\| echo unfolded` (§5.2 — `ls -la \| grep` silently passes when it shouldn't); `stow -R <pkg>` |
| Config change had no effect | Symlink points outside the repo | `readlink -f ~/.config/<pkg>` |
| Change needs a full logout to apply | Used `exec` instead of `exec_always` | §9.2 |
| Screen never locks | swayidle not running, or many are | `pgrep -xc swayidle` — must be exactly `1` |
| Screen locks immediately / repeatedly | Multiple swayidle instances racing | Same check; the `pkill` prefix is missing |
| GTK apps still not Nord | `nordic-theme` not installed | `ls /usr/share/themes/Nordic` |
| GTK apps still not Gruvbox | `Colloid-Yellow-Dark-Gruvbox` not installed | `ls -d ~/.themes/Colloid-Yellow-Dark-Gruvbox` — it lives in `~/.themes`, not `/usr/share/themes` |
| *Some* apps still light | libadwaita | §2.2; check `gsettings get org.gnome.desktop.interface color-scheme` → `prefer-dark` |
| GTK theme reverted | nwg-look was opened | §9.1 |
| Boxes instead of icons | Nerd Font missing | `fc-match "JetBrainsMono Nerd Font"` |
| Wrong/blurry scale | Output scale not declared | `swaymsg -t get_outputs` |
| External monitor ignored | kanshi profile doesn't match | `pkill -x kanshi; kanshi` in a terminal and read the error |
| Screen share / file picker misbehaves | Portal backend | `systemctl --user show-environment \| grep XDG_CURRENT`; §6.4 |
| Background reverted to an image | azote | §9.3 |
| Notification icons missing | mako `icon-path` | Must be a directory that exists |
| Border width change ignored | Applies to new windows only | `swaymsg '[title=".*"] border pixel 2'`; §9.8 |
| Gaps stuck at an old value | A runtime `gaps` command overrode the config | `swaymsg gaps inner all set 8`; §9.8 |
| A window has no border at all | `smart_borders on` with one window | Set `smart_borders off`; §9.8 |
| One GTK app is the wrong theme | It predates the theme change | Restart it; §9.9 |
| `$mod+Return` does nothing | `foot --server` not running | `pgrep -a foot` |
| Terminal still the old palette after a switch | foot cannot reload colours | `theme <name> --restart-terminals`, or log out; §9.11 |
| One surface still the old palette, everything else switched | A running GTK app, or a file whose name does not match `<base>-<theme>.<ext>` so `theme` never saw it | `theme` prints how many symlinks it flipped — it must say **17**; §3.3 |
| A widget renders **black** | A role used but not defined in that palette's fragment | §9.10 — define it in *both* fragments |
| `theme: missing fragment: …` | A theme symlink (not necessarily `colors.*` — could be `settings.ini`, `.gtkrc-2.0`, etc.) exists with no counterpart for the target theme | Create the sibling fragment, or remove the symlink |
| `theme: … define different roles` | The two palettes have drifted | §9.10. This is the guard, not a fault |
| Folder icons don't match the theme | papirus-folders was skipped — it needs `sudo` and there was no tty to prompt on | Run the `sudo papirus-folders -C <colour> -t Papirus-Dark` line `theme` printed |
| Cursor is the default X arrow | Theme name case | `ls -d /usr/share/icons/<name>` — XCursor resolves by case-sensitive path; §6.2 |
| A `$role` breaks `sway --validate` | `Invalid border color $accent` — the binding is in `default`, parsed before `theme` | §9.13; source `theme.env` from a script instead |

### Verification sweep

```sh
sway --validate -c ~/.config/sway/config     # before any reload
pgrep -xc swayidle                            # exactly 1
fc-match "JetBrainsMono Nerd Font"            # not NotoSansMono
swaymsg -t get_outputs                        # scale 2 on eDP-1
gsettings get org.gnome.desktop.interface color-scheme    # 'prefer-dark'
systemctl --user show-environment | grep XDG_CURRENT      # =sway
readlink -f ~/.config/sway ~/.config/waybar ~/.gtkrc-2.0  # all inside the repo

theme                                                     # nord | gruvbox
readlink ~/repos/dotfiles/sway/.config/sway/theme.env     # theme-<that>.env
```

Folding — the property §5.2 depends on, and the one that a stray file in `~/.config` quietly breaks:

```sh
for p in sway waybar foot mako fuzzel gtklock nwg-drawer htop; do
    printf '%-12s ' "$p"
    if [ -L ~/.config/$p ]; then echo "folded (symlink)"; else echo "UNFOLDED (real dir)"; fi
done
```

Eight lines, every one `folded (symlink)`. Use this form, not `ls -la ~/.config | grep -E ' foo$'` —
see §5.2 for why that one passes silently when things are fine and only speaks up when they break.

Then trigger each themed surface by hand: `$mod+d`, `notify-send test`, `$mod+Shift+d`, the waybar
clock tooltip (and *scroll* on it — §9.14), `$mod+f1`, thunar, a GTK4 app, `$mod+Return`, `Print`,
`vim`, `ls`.
