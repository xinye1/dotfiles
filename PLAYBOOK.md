# Sway, Nord and Gruvbox: the full playbook

The complete technical reference for this desktop: what it is, how the pieces fit together, and
every way it differs from a stock EndeavourOS Sway install.

It carries **two palettes**, Nord and Gruvbox Dark, and switches between them with one keystroke
(`theme <name>` at a shell). Nord is the default and the original; Gruvbox was
added by making every colour in the setup a *role* rather than a hex, which is the single change
that most of this document now turns on. §3.3 is the mechanism.

This is the document to *read*. The thing to *run* on a new machine is `./setup.sh` (README).

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
azote, swappy, cliphist). Two of those have since been replaced here: kitty is the default terminal
instead of foot (§9.11), and swaylock is the lock screen instead of gtklock (§4.3).
This playbook is written as a **diff against that**, not against
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
            waybar, mako, kanshi, swayidle, autotiling,
            nm-applet, cliphist watchers, polkit agent, nwg-drawer
```

**Alphabetical order is load-bearing.** `application_defaults` is read before `default`, and
`theme` last. Anything that must win a conflict belongs in a later-sorted file.

`exec` runs **only at sway startup**. `exec_always` runs at startup *and* on every
`swaymsg reload`. Choosing wrong is the single most common bug in this config — see §9.2.

### 2.2 How GTK theming actually reaches applications

There are five parallel mechanisms, and they do not agree with each other by default:

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
                                       ← CONFIGURED BUT NOT INSTALLED (below)
```

**Four of those five are live; the xsettingsd one is not.** `xsettingsd` is not installed on this
machine — there is no binary, nothing starts one, and nothing reads
`~/.config/xsettingsd/xsettingsd.conf`. `theme` renders it with every switch and the result is
inert. It is kept because it costs one template, and because the alternative is finding out at
install time that the one mechanism carrying GTK settings to XWayland clients was never themed;
`pacman -S xsettingsd` plus something to start it is what makes the arrow above real. Until then
XWayland clients fall back to what `gtk-3.0/settings.ini` and Xft give them. Note this is *not* the
same as the nwg-look `export-xsettingsd` toggle in §9.1 — that one writes the file, and would
clobber the template's output whether or not the daemon exists.

**The critical thing to understand:** *libadwaita apps ignore `gtk-theme-name` completely.*
Installing the Nordic GTK theme does nothing for them. They read named colours
(`@window_bg_color`, `@accent_bg_color`, …) and decide light vs dark from the gsettings
`color-scheme` key. That is why this repo carries a hand-written
`gtk/.config/gtk-4.0/gtk.css` redefining those colours, and why `import-gsettings` was extended
to set `color-scheme`.

### 2.3 Where the palette lives

Every application parses its own config format, so the palette must reach each of them in that
application's own syntax. It is not, however, *written* more than once.

`palettes.toml` at the repo root holds both palettes. Each themed file exists once, as a template
of `{{role}}` placeholders, and `theme` renders it:

```
palettes.toml                                  both palettes, one table
waybar/.config/waybar/colors.gen.css.tmpl      @define-color bg {{bg}};
        rendered by `theme` to
waybar/.config/waybar/colors.gen.css           @define-color bg #282828;
        included by
waybar/.config/waybar/style.css                @import url("colors.gen.css");
```

The include is static — `style.css` always names `colors.gen.css`, whichever palette is loaded.
That is what makes switching a re-render rather than a reconfiguration.

**Rendered files are build artefacts.** They match `*.gen.*` — or a bare `*.gen`, which is what
mako's `colors.gen` is, since its `include=` names the file with no suffix; `.gitignore` carries
both globs for that reason. Git ignores them, and editing one is pointless because the next switch
overwrites it. Seven files are the exception and cannot carry the
marker, because the application reads them at a hardcoded path and takes no include: GTK and
xsettingsd account for six — `gtk-{3,4}.0/gtk.css`, `gtk-{3,4}.0/settings.ini`,
`xsettingsd/xsettingsd.conf` and `.gtkrc-2.0` — and yazi's `theme.toml` for the seventh.
Those seven are listed individually in `.gitignore`. That list is structural — it can only change if
an application with a hardcoded config filename joins the desktop, which is exactly what happened
when yazi arrived on 2026-08-16.

(The pre-render scheme this replaced is described in
`docs/archive/2026-08-17-stock-deviations.md`.)

starship sits outside this whole scheme, deliberately. It has no `.tmpl` and sets no colours of its
own — its upstream defaults are mostly named-ANSI styles, which take their actual colour from the
terminal's palette and so already track a switch for free. A few modules pin fixed 256-colour
indices instead, which do not: `starship print-config` — the defaults merged with the tracked
overrides, fully resolved — shows `style = "149 bold"` for the C module among others, with indices
149, 208 and 147 all appearing. Fixing those to the palette would mean giving starship a template,
and `starship.toml`'s own header says "Only deviations from the defaults live here" — a template
means restating every upstream default just to own the file, and inheriting whatever upstream
changes next is worth more than exact parity on a handful of language modules.

---

## 3. The palettes

### 3.1 Role convention

**This section is the point of the whole document.** The desktop drifted into four incompatible
palettes because each config was themed ad hoc. It now carries two palettes *only* because every
colour is named by role.

The values live in `palettes.toml`; this is what the roles are **for**. Adding a colour means
picking a row, or adding one to both palettes — never choosing a colour that looks nice in
isolation.

| Role | What it is for |
|---|---|
| `bg` | window bg, waybar bg, terminal bg, swaylock indicator inside |
| `surface` | mako body, popovers, cards, fuzzel-adjacent chrome |
| `sel` | fuzzel selection, terminal selection bg |
| `muted` | unfocused border, placeholders, calendar weeks — **structure, not prose** |
| `dim` | secondary *text* that still has to be read: tooltip subtitles, reset countdowns, chart labels, footers (§9.28) |
| `fg` | body text everywhere |
| `fg_bright` | focused window title, active text |
| **`accent`** | sway focused border, waybar focused workspace, GTK accent, fuzzel border |
| `accent2` | focused-inactive border, calendar weekdays, waybar mode |
| `indicator` | sway split indicator — where the next window will open |
| **`critical`** | urgent window, critical CPU/battery, destructive actions |
| `warning` | warning states, "today" in the calendar, idle inhibitor on |
| `success` | battery charging, success states |
| `desktop` | the wallpaper-less background, one shade below `bg`; also the swaylock screen when no wallpaper is cached (§9.25) |

**`muted` and `dim` are not shades of one idea, and the split is the whole point.** `muted` says
"this is chrome" — a border, a rule, a weekday header — and is allowed to be almost invisible.
`dim` says "this is text you are meant to read, quietly", and therefore carries a floor: **4.5:1
against the background it lands on**, in *both* palettes — and where that background is
translucent, against the worse of its composites, not the flattering one (§9.28). Before it
existed, everything secondary
used `muted`, which measured 1.87:1 on the GTK tooltip under nord — the widget was written under
gruvbox, where the same role scrapes 3.64:1 and merely looks quiet (§9.28). If a new role is ever
added for text, give it a measured floor in this table or it will drift the same way.

`desktop` being darker than `bg` is what turns the gaps between windows into visible channels, and
is what makes `smart_borders on` safe. Nord has nothing below `nord0`, so its value is a
hand-darkened one; Gruvbox ships the idea as `bg0_h`. `palettes.toml` records both.

Two per-palette values are not colours and still have to be chosen per palette: `gtk_theme_name`
and `papirus_folder`. They live in the same table.

A third group is the **16-colour terminal ramp**, under `[<palette>.ansi]`. Eight of its slots are
role colours; the other eight are not, and are shared by kitty and foot. They used to be
duplicated across the terminals with a comment asking that they be kept in step by hand.

**Both palettes must define exactly the same keys.** `theme` refuses to render otherwise. This
matters more than it looks: an undefined `@name` in GTK CSS renders as **black, with no warning**,
which is near-impossible to diagnose from the symptom. The old code checked role parity at runtime
with a bespoke comparison; one table with two sections makes the failure a missing key, named at
render time.


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
lists 25 names and gruvbox is not among them, so `papirus_folder = "yellow"` in `palettes.toml` is a
*stand-in*, chosen because gruvbox's signature accent is its yellow. It is the one place in the
setup where the Gruvbox theme is approximated rather than matched. Do not "fix" it by inventing a
hex — papirus-folders only accepts names from its own list.

**The GTK themes are asymmetric too.** Nord's is `Nordic` in `/usr/share/themes` from the AUR;
Gruvbox's is `Colloid-Yellow-Dark-Gruvbox` in **`~/.themes`**, installed by hand (§4.2, §8). Both
names are `gtk_theme_name` in `palettes.toml`, so nothing else needs to know where they live — but `ls /usr/share/themes` will not find the gruvbox one, and that is not a fault.

### 3.3 Switching

```sh
theme              # re-render the current palette
theme nord         # switch
theme --list       # what is available
theme --no-icons   # skip papirus-folders, which needs sudo
```

`theme` renders every template, records the palette in `$XDG_STATE_HOME/theme/palette`,
then reloads: `sway --validate` before `swaymsg reload` (which also restarts waybar, re-runs
`import-gsettings` and re-execs nwg-drawer), then `makoctl reload` separately, because mako is
`exec`'d rather than `exec_always`'d and a sway reload does not restart it.

**Switching is not a repo change.** The state file lives outside the repo and every rendered file is gitignored, so a switch
leaves `git status` untouched. `tests/theme_test.sh` asserts it.

**`theme` must run before `stow` on a fresh clone.** The rendered files do not exist in a clone,
and the unfolded packages that carry templates (`gtk`, `vim`, `yazi` — `bin` and `claude`
are also unfolded but carry none) link file-by-file — a file created
after `stow` is silently absent until `stow -R`. The folded packages pick it up for free. See
§5.2.

Applying is idempotent: re-running repairs a deleted or edited artefact.

**foot does not reload.** It has no config-reload signal at all; `SIGUSR1`/`SIGUSR2` only pick
between the `[colors-dark]` and `[colors-light]` blocks loaded at startup. A switch needs a foot
server restart or a logout.

---

## 4. Package manifest

The install lists a new machine actually consumes are `packages.txt` (official repos) and
`packages-aur.txt` (AUR) at the repo root — `sudo pacman -S --needed $(cat packages.txt)`, then
`yay -S --needed $(cat packages-aur.txt)`. One entry needs a repo beyond Arch's own
`core`/`extra`/`multilib`: `welcome` comes from `endeavouros`, enabled by default on this distro
(§1) — EndeavourOS's own new-user greeter, resolved by a plain `pacman -S`, not AUR, and not the
same package as the unrelated KDE `plasma-welcome`. `setup.sh` warns about anything from either
list that is not installed. The files also carry the tools the configs here invoke that the
tables below assume (vim, neovim, starship, htop, and yazi's
`fd`/`ripgrep`/`fzf`/`jq`/`poppler`/`imagemagick`). The tables say *why* each package is here
and what breaks without it; the two `Source: source` entries (the Colloid GTK theme, the vim
colorschemes) cannot live in either file and are §8's job.

### 4.1 Required — the setup is broken without these

| Package | Source | Why | Symptom if missing |
|---|---|---|---|
| `sway` `swaybg` `swayidle` | repo | Compositor, background, idle daemon | — |
| `waybar` | repo | The bar | No bar |
| `kitty` | repo | **The terminal.** `$term` is `kitty`; also the dropdown, fuzzel's `terminal=`, and waybar's htop/nmtui click targets. One process per window, no daemon — §9.11 has the measurements | `$mod+Return` does nothing |
| `foot` | repo | Standalone fallback, still themed. No longer `$term` and no server is started; run `foot`. Wayland-only, which is why it is not the default | Nothing — `foot` is optional now |
| `fuzzel` | repo | Launcher (`$mod+d`) and the cliphist picker | Launcher and clipboard history dead |
| `mako` | repo | Notifications | Silent desktop |
| `swaylock` | repo | Lock screen, driven by `sway/scripts/lock.sh` — `$mod+f1`, the 300s idle timeout (via `idle.sh`, §9.26), before-sleep, and the power menu's Lock entry. No config file of its own: the script derives every colour from the live palette and passes them as flags (§9.13), and picks a random wallpaper out of `~/Pictures/walls/<palette>/` (§9.25) | **Machine never locks** — `lock.sh` execs a binary that is not there, and swayidle's timeout fires into nothing |
| `nwg-drawer` | repo | App grid (`$mod+Shift+d`), also the waybar launcher button | |
| `grim` `slurp` `swappy` `wl-clipboard` | repo | Screenshots and clipboard | Print bindings dead |
| `cliphist` | repo | Clipboard history | `$mod+Ctrl+v` dead |
| `autotiling` | repo | Splits along the longer axis automatically | Manual `$mod+v`/`$mod+b` for every split |
| `pamixer` `brightnessctl` `playerctl` | repo | Media/brightness keys | Function keys dead |
| `polkit-gnome` | repo | Auth prompts for GUI privilege escalation | GUI admin actions fail silently |
| `stow` | repo | Deploys this repo | |

**Optional — the setup is not broken without these; each has its own fallback.**

| Resource | Source | Why | Symptom if missing |
|---|---|---|---|
| `~/Pictures/walls/` | **`walls-sync`** | The lock screen's wallpapers, one directory per palette, populated by `bin/.local/bin/walls-sync` from [dharmx/walls](https://github.com/dharmx/walls). Optional, ~320 MB, and a cache in the strict sense — deleting it loses nothing but time (§9.25) | Lock screen falls back to the solid `$desktop` colour. Nothing else changes; it still locks |

### 4.2 Added by this setup

| Package | Source | Why |
|---|---|---|
| `nordic-theme` | **AUR** | The GTK2/3/4 Nord theme. `/usr/share/themes/Nordic`. Nothing in the base install provides a Nord GTK theme. |
| `Colloid-Yellow-Dark-Gruvbox` | **source** | The GTK theme for the Gruvbox palette, in `~/.themes`. Not a package — see §8 for the two-line install |
| `papirus-icon-theme` | repo | Icon theme, referenced by mako, fuzzel and GTK |
| `papirus-folders` | **AUR** | Recolours Papirus folder icons. `theme` drives it per palette (`nordic` / `yellow`), and it is the one step needing `sudo` |
| `ttf-jetbrains-mono-nerd` | repo | **The patched Nerd Font.** See §9.4 — the base install has only `ttf-nerd-fonts-symbols`, a symbols-only fallback |
| `google-chrome` | **AUR** | **The browser.** `$mod+o` and `$BROWSER`, and the default handler for `http`/`https`/`text/html` — §8 sets that, it is not stowed. The package ships `/usr/bin/google-chrome-stable` **only**: no bare `google-chrome`, and `Google-chrome` is the X11 WM_CLASS (`application_defaults` matches on it to assign workspace 2), never a command. Get the name wrong and `$mod+o` fails silently |
| `kanshi` | repo | Display hotplug profiles |
| `tmux` | repo | Terminal multiplexer. Optional to the desktop, but its status bar is themed from `palettes.toml` like everything else, so a machine without it simply renders a `colors.gen.conf` nobody reads. `git` is a soft dependency of the bar's right-hand segment — absent, the branch is blank rather than broken |
| `nord-vim`, `gruvbox` | **source** | vim colorschemes, cloned into `~/.vim/pack/plugins/start/` — §8. Without them vim still starts; `vim/.vimrc` guards the `source` with `filereadable` |
| `yazi` | repo | Terminal file manager, themed from `palettes.toml` like everything else. Optional to the desktop; a machine without it renders a `theme.toml` nobody reads. Launched as `y` from any interactive bash — the wrapper in `bash/.bashrc` leaves the shell in whatever directory yazi ended up in, which plain `yazi` cannot do. **Optional extras, none required:** `7zip` (archive preview and the `extract` opener — without it archives show nothing), `ffmpegthumbnailer` (video thumbnails), `perl-image-exiftool` (the preset's `exif` opener), `zoxide` (makes the preset's `Z` binding work rather than error), `chafa` (image fallback outside kitty). `fd`, `ripgrep`, `fzf`, `jq`, `poppler` and `imagemagick` are already present and are what `s`, `S` and `z` use. Image previews need nothing extra: kitty speaks its own graphics protocol and `tmux.conf` already sets `allow-passthrough on` |
| `lualine.nvim`, `nvim-web-devicons` | **self-installing** | nvim's statusline. Fetched by `vim.pack.add` in `init.lua` on first launch, into `~/.local/share/nvim/site/pack/core/opt` — nothing to clone by hand, and nothing in `~/.config/nvim` (§5.2). nvim's *colourschemes* are still written from the §3.1 roles rather than cloned, and lualine is themed from them too, so no plugin decides a colour here |

**Why the gruvbox GTK theme is not the AUR package.** `gruvbox-gtk-theme-git` depends on
`gtk-engine-murrine`, which on a current Arch pulls in a **from-source `gtk2` build** — and gtk2 is
not installed here, nor wanted for one theme. `vinceliuice/Colloid-gtk-theme` has a gruvbox tweak
that produces the same result, installs into `~/.themes` without root, and needs no engine.

### 4.3 Deliberately not used

`gtklock` (see below), `wofi`/`rofi` (fuzzel), `dunst` (mako),
`lxappearance` (GTK3+ only reads settings.ini), `qt5ct`/`qt6ct` (no Qt apps in this setup yet —
add them if that changes, as Qt apps will otherwise ignore the theme entirely).

**`gtklock`, dropped for `swaylock`.** This entry used to read the other way round — swaylock was
the one not used, "gtklock does the job and is already themed" — so read it as a reversal, not as a
gap that was always there. The reason is the honest one: **the user did not want gtklock.** It
worked and it was themed; that was not enough to keep it. This is the rare change in this repo
driven by preference rather than by a defect, and it is written down as such so nobody later hunts
for the bug that prompted it.

What the switch costs, plainly, because the replacement is genuinely smaller: **no clock, no power
buttons, and no user avatar on the lock screen.** gtklock is a GTK app with a window full of
widgets; plain swaylock draws one password ring over a wallpaper (§9.25) or a solid `$desktop`
field, and nothing else. The power buttons are the only real loss, and they are not lost —
`$mod+Shift+e` reaches the same suspend/reboot/shutdown actions through `power_menu.sh`, from an
unlocked session. The clock is on waybar. The avatar has no replacement and none is wanted.

`swaylock-effects` (blur, screenshot backgrounds, a clock) was considered and declined, and **that
is still true now that the lock screen carries a wallpaper** — read the reason carefully, because
the obvious paraphrase of it has since been overtaken. What was rejected is *an unofficial fork as
a dependency*, and separately *a 22 MB image living in the repo*, which is what the gtklock
wallpaper was. A background image as such was never the objection: `--image` is stock swaylock, it
costs no package, and §9.25's images are in `~/Pictures`, not here. Configuration lives in
`sway/.config/sway/scripts/lock.sh` rather than `~/.config/swaylock/config`, because a static config
file cannot follow a palette switch and a script sourcing `theme.gen.env` at lock time can (§9.13).

**mako's `group-by`**, tried and reverted. mako draws only the *first* member of a group, so
`group-by=app-name` turned six notifications into one card reading `(6) …` with the other five
invisible and no hint they differed. It bites here specifically because `notify-send` sends an
**empty app name** — every script on the machine grouped as one nameless app, which is grouping's
worst case rather than its intended one. The wall-of-cards problem it was meant to solve is already
handled by `max-visible=5` plus the `[hidden]` placeholder. `[grouped] invisible=0` was also tried:
it shows every member, but stamps the redundant `(N)` on each one *and* escapes the `max-visible`
cap. If a genuinely chatty app ever arrives, `group-by=app-name,summary` collapses only true
repeats without hiding distinct messages.

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
| `sway` `mako` `fuzzel` `nwg-drawer` `kanshi` `foot` `waybar` | **Yes** | Nothing writes into these directories. New files appear for free. |
| `kitty` | **Yes** | kitty's state is in `~/.local/state/kitty` and `~/.cache/kitty`, not the config dir, so it behaves like `foot`. **The one thing that would break this is `kitten themes`**, which writes `current-theme.conf` into `~/.config/kitty` *and* appends an include to `kitty.conf` — folded, that lands in the repo, and it is the wrong mechanism here anyway: colours come from `palettes.toml`. Do not run it, for the same reason `nwg-look` is a hazard for `gtk` (§9.1). |
| `tmux` | **Yes** | tmux itself never writes to `~/.config/tmux` — its state is sockets under `$TMUX_TMPDIR`. The package is at the XDG path rather than `~/.tmux.conf` (tmux has read it since 3.1) precisely so that folding is available: the rendered `colors.gen.conf` and `scripts/git-branch.sh` then appear with no `stow -R`, and neither has to sit loose in `$HOME`. **The one thing that would break this is a plugin manager**: tpm installs into `~/.config/tmux/plugins`, which folded means untracked plugin clones inside the repo. None is used today; adding one means unfolding first. |
| `nvim` | **Yes** | Neovim keeps its state in `~/.local/share/nvim`, `~/.local/state/nvim` and `~/.cache/nvim`, and `vim.pack` puts plugin *code* in `~/.local/share/nvim/site/pack/core/opt` — none of it in `~/.config/nvim`, so the reason `vim` stays unfolded does not apply. Folded, a newly rendered `colorscheme.gen.lua` and any new themed file appear without `stow -R`. **The one thing `vim.pack` does write here is `nvim-pack-lock.json`**, which folding puts straight into the repo — so it is tracked deliberately (§8) rather than ignored, which is what keeps the "no untracked content inside a folded directory" rule satisfied. It is rewritten in place, not by `rename()`, so unlike `htop` (§9.16) folding is a choice here rather than a requirement. |
| `gtk` | **No** | **nwg-look writes into `~/.config/gtk-{3,4}.0`.** See §9.1. Only specific files are tracked; `bookmarks` is left alone as machine-specific. |
| `bin` | **No** | `~/.local/bin` is a real directory holding untracked binaries — `claude`, `coderabbit` (104 MB), `herdr` (22 MB), `uv`. Folding would pull all of it into the repo. A newly added script therefore needs `stow -R bin`. |
| `yazi` | **No** | `ya pkg add` installs plugins and flavors into `~/.config/yazi` and writes a `package.toml` lockfile beside them — untracked content inside the package directory, which is the rule below. **No plugin is used today**, and the decision is still made now: unfolding later costs `stow -D && rmdir && stow`, and the trap this section documents is discovering that mid-way through something else. `~/.config/yazi` therefore has to exist *before* the first `stow yazi`, or stow folds it. A file added to the package later is silently absent until `stow -R yazi` — and for this package that includes the rendered `theme.toml`, which is why `tests/check_consumers.sh` asks yazi whether it actually loaded a theme rather than only whether it started. |
| `vim` | **No** | `~/.vim` holds untracked plugin clones (`lightline`, and now `nord-vim` and `gruvbox`), so folding would pull them into the repo. A newly added file in the package — such as a future themed file — is silently absent until `stow -R vim`. That is exactly the trap this section exists to document. |
| `claude` | **No** | `~/.claude` is Claude Code's own state directory — `sessions/`, `history.jsonl`, `projects/`, `plugins/`, `.credentials.json`, all untracked and some of it secret. Folding would pull the lot into the repo. It also already contains `skills`, a directory symlink to `~/repos/xl-skills/skills`, which folding would swallow. Unfolded, stow links only `statusline.py`; a second file added to the package later needs `stow -R claude`. Note the repo's own `.claude/` at the root is Claude Code *project* state for this repo and is not a package — never name it in a stow command. |
| `htop` | **Yes — and it must be** | When htop does save `htoprc` (clean quit, settings changed) it uses `mkstemp` + `rename()`. A `rename()` onto a *file* symlink replaces the symlink with a regular file, so an unfolded `htop` would silently detach from the repo the first time it saved. Folded, the write lands on the repo's own file. See §9.16. |
| `bash` | **Neither — no directory to fold** | Owns two loose files, `~/.bashrc` and `~/.config/dircolors`, and no directory of its own. `$HOME` and `~/.config` always exist, so stow has nothing to fold and always links file by file. Consequence: **a new file added to this package is silently absent until `stow -R bash`**, the same as an unfolded package, and it can never become folded by accident. |
| `starship` | **Neither — no directory to fold** | Owns one loose file, `~/.config/starship.toml`. Same as `bash`: no directory, nothing to fold, `stow -R starship` needed for any file added later. |

**Rendered palette files are the standing exception.** Every folded themed package now contains
ignored `*.gen.*` artefacts, which is untracked content inside a folded directory — the thing the
rule below forbids. It is tolerable here for one reason only: those files are caught by a glob that
cannot fall behind, unlike a hand-maintained list. It is worth naming as a principle spent rather
than earned, because the next person to put a generated file in a package will cite it.

The rule: **never fold a directory that a tool writes into, or that holds untracked content** —
*unless* the tool replaces the file by `rename()`, in which case folding is the only thing that
survives it (`htop`, §9.16). What breaks folding is untracked content appearing inside the
directory, not writes to a tracked file.

Check which a directory is:

```sh
[ -L ~/.config/waybar ] && echo folded || echo unfolded
```

Use the `[ -L ]` test, not `ls -la ~/.config | grep -E ' waybar$'`. `ls` renders a symlink as
`waybar -> ...`, so a `$`-anchored grep matches only the **unfolded** case — the command prints
nothing and silently "passes" exactly when folding is healthy, and prints a line exactly when it is
broken. The anchored form shipped in this plan's own verification step and had to be corrected.

To fold one that isn't: `stow -D <pkg> && rmdir <the now-empty target dirs> && stow <pkg>`.

**The theming work did not change a single row of this table, by design.** Each template and its
rendered output live *inside* the package that owns them, so switching writes into the repo, never
into `~/.config`. The alternative — a pair of per-palette stow packages — would have
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

The full stock-vs-here record — every theming deviation and every stock defect found and fixed,
with verification — is archived in
[`docs/archive/2026-08-17-stock-deviations.md`](docs/archive/2026-08-17-stock-deviations.md).
It is history: the *rules* that came out of it live in §3, §5 and §9. What remains here is
capability added on top of stock (§6.3) and the one known-incomplete fix (§6.4).

### 6.3 Added capability

| Addition | Binding / file | Notes |
|---|---|---|
| Workspace back-and-forth | `$mod+Tab`, plus `workspace_auto_back_and_forth yes` | Re-pressing the current workspace's number returns to the previous one |
| Dropdown terminal | `$mod+grave` | `kitty --class dropdown`, parked in the scratchpad. `swaymsg … scratchpad show` exits 2 when nothing matches, so `\|\| kitty …` creates it on first press. `--class` sets the app_id the `for_window` rule matches on — and stays this simple only while `$term` is one-process-per-window; under `--single-instance` it would need `--instance-group dropdown` too |
| Modal resize | `$mod+r` | vim keys and arrows; `Escape`/`Return` exits. Indicator drawn by waybar's `sway/mode` module |
| Gaps toggle | `$mod+g` | `gaps inner current toggle 12` — for screen sharing and screenshots |
| Screenshot to clipboard | `Ctrl+Shift+Print` | Skips the swappy editor. All four Print bindings now go through `scripts/screenshot_*.sh`, which theme the slurp selection box and bail out when the selection is cancelled — §9.13 |
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

## 7. Keybindings

Not listed here. A static table duplicating `sway/.config/sway/keyboard.conf` (457 lines) is a
table that drifts, and this desktop already answers the question two better ways:

- `sway/.config/sway/keyboard.conf` holds most of them, commented.
- `sway/.config/sway/config.d/default` holds the rest — the two files together are the source.

**`$mod+?`**, or clicking the waybar clock, runs `waybar/.config/waybar/scripts/keyhint.sh`. Be
aware of what that is: a *hardcoded* `cheat=()` array, inherited from stock EndeavourOS. It reads
no config, so it can and does drift from the two files above. It is a convenience, not a source.

Two things bite when adding to it, both silent:

- The array is a **flat list of cells in a 5-column grid** (left Function, left Binding, spacer,
  right Function, right Binding). Append fewer than five and every following row shifts a column —
  a section header lands in the Binding column and nothing errors. Count with
  `len(cells) % 5 == 0` before trusting it.
- **`--geometry` does not grow with the array.** yad clips the overflow with no scrollbar and no
  warning: the NOTIFICATIONS section was invisible at `1200x680` until the height went to `860`.
  Screenshot the window after adding rows; do not assume it rendered.

The notification bindings are `$mod+Shift+n` (do-not-disturb toggle), `$mod+Ctrl+n` (restore the
last notification from history) and `$mod+Ctrl+Shift+n` (dismiss all). They are plain `makoctl`
calls with no colour in them, which is why they can live in `config.d/default` despite that file
being parsed before `config.d/theme` (§9.6).

The one worth knowing before you can read any of it: **`$mod+Return`** opens a terminal.

**A binding is for something done often.** Switching palettes is not, so it has none — `theme
<name>` at a shell is the interface. The previous binding was `$mod+Shift+t exec theme toggle`,
which stopped working when `toggle` was dropped and failed *silently*, because a sway `exec` sends
stderr nowhere. That is the second cost of a binding for a rare operation: nobody notices it
rotted.

---

## 8. Post-install steps that cannot be stowed

`./setup.sh <palette>` already did everything stow-shaped: the §5.2 fold-guard `mkdir`s, the render
(before the stows — §3.3), the `/etc/skel` `~/.bashrc` move, and every package, gated on a
`stow -n` dry run so a conflict stops it before anything is linked. What follows is what it cannot
do.

```sh
# Tint the Papirus folder icons (writes into /usr/share/icons, so root).
# `theme` re-runs this on an INTERACTIVE switch when the colour differs -- it skips
# papirus-folders when stdin is not a tty, because it needs sudo. This is just
# the first one. nordic for Nord, yellow for Gruvbox — see §3.2.
sudo papirus-folders -C nordic -t Papirus-Dark

# Default web browser: http, https and text/html to Chrome. This is xdg state,
# not config — it lands in ~/.config/mimeapps.list, which xdg-settings and every
# "make me your default?" prompt rewrite in place. Stowing that file would make
# it a tracked file other programs edit behind you, the nwg-look failure mode of
# §9.1 — so it stays a one-liner here. Idempotent; verify with
# `env -u BROWSER xdg-settings check default-web-browser google-chrome.desktop`.
# `env -u BROWSER` is REQUIRED, not tidiness: bash/.bashrc exports $BROWSER, and
# xdg-settings refuses to write while it is set ("$BROWSER is set and can't be
# changed with xdg-settings") — exit 1, one line of stderr, nothing written.
# NOTE the .desktop name is `google-chrome`, while the BINARY is
# `google-chrome-stable` ($mod+o, $BROWSER) and the X11 class is `Google-chrome`
# (application_defaults). Three spellings, all required, none interchangeable.
env -u BROWSER xdg-settings set default-web-browser google-chrome.desktop

# The Gruvbox GTK theme. Not a package: see §4.2 for why not the AUR one.
# NEVER add -l/--libadwaita — it overwrites ~/.config/gtk-4.0/gtk.css, which is
# precisely the nwg-look failure mode of §9.1.
git clone https://github.com/vinceliuice/Colloid-gtk-theme /tmp/colloid
cd /tmp/colloid && ./install.sh -d ~/.themes -c dark -s standard -t yellow --tweaks gruvbox

# vim: status bar, and one colorscheme per palette
git clone https://github.com/itchyny/lightline.vim ~/.vim/pack/plugins/start/lightline
git clone https://github.com/arcticicestudio/nord-vim ~/.vim/pack/plugins/start/nord-vim
git clone https://github.com/morhetz/gruvbox   ~/.vim/pack/plugins/start/gruvbox

# nvim: nothing to run. Its colourscheme is rendered from the §3.1 roles
# (nvim/.config/nvim/colorscheme.gen.lua.tmpl), so there is no colorscheme
# clone to forget, and lualine installs itself: `vim.pack.add` in init.lua
# fetches it on the FIRST LAUNCH, which is therefore the one launch that needs
# network. Offline, nvim still opens — it falls back to the built-in
# statusline, already themed.
#
# Plugin versions are pinned in the TRACKED nvim/.config/nvim/nvim-pack-lock.json,
# so a fresh clone installs the same revisions this machine runs. Updating is
# deliberate — `:lua vim.pack.update()` — and DOES dirty the tree: the lockfile
# is the diff, and committing it is how a version bump gets recorded. That is
# the exact opposite of `theme`, where a switch must never show up in git; the
# difference is that a plugin revision is part of the configuration and the
# active palette is not.
```

**`theme` before `stow`, always.** If you stow first, run `stow -R <pkg>` afterwards for the
unfolded packages, or the rendered files will exist in the repo and be absent from `~`.

Optional: the greetd-level environment fix from §6.4, in `/etc/greetd/config.toml`.

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

### 9.2 `exec` vs `exec_always` — three distinct bugs

- **`exec_always` without cleanup leaks processes.** Every reload spawns another copy. This is what
  produced 40 swayidle processes. Any `exec_always` that starts a long-lived daemon needs
  `pkill -x <name>;` in front of it. `pkill -x` matches the exact name — without `-x`, `pkill sway`
  would kill sway itself.
- **`exec` cannot be repaired by a reload.** It only runs at startup, so a fix that uses `exec`
  appears not to work until you log out and back in. This bit the `XDG_CURRENT_DESKTOP` fix during
  development.
- **An unquoted `;` on an exec line is split, and only at startup.** sway dispatches an exec line by
  two different routes. At a *reload* the config is already active and the line goes straight to
  `sh -c` with its `;` intact. At *startup* the same line is deferred into a queue and replayed
  through the parser `swaymsg` uses — and that one splits a command string on `;`. So the two rules
  above, applied naively, produce a line that is broken exactly at login:

  ```
  exec_always pkill -x idle.sh; pkill -x swayidle; ~/.config/sway/scripts/idle.sh
  ```

  runs `pkill -x idle.sh` and nothing else, the remaining two segments being rejected as unknown
  sway commands. The correct form hands sway **one** command and lets the inner shell own the `;`:

  ```
  exec_always sh -c 'pkill -x idle.sh; pkill -x swayidle; exec ~/.config/sway/scripts/idle.sh'
  ```

  `exec` on the last segment keeps the wrapper shell from lingering as an extra process, and leaves
  the daemon's own name in `comm` so `pkill -x <name>` still matches it.

  **This is the failure mode a reload cannot show you.** The machine booted with no `swayidle` at
  all — no idle lock, ever — and `pgrep -xc swayidle` returned 1 the moment anyone ran
  `swaymsg reload` to check. `kanshi` had been broken the same way for as long as its line existed,
  and nobody noticed because a reload always repaired it. `tests/check_sway_exec.py` asserts the
  invariant across every exec line; `sway --validate` does not catch it, because at validate time
  the line is syntactically a perfectly good `exec`.

Also: `exec export FOO=bar` does nothing. sway runs the command in a subshell that exits
immediately, taking the variable with it. Use `systemctl --user set-environment`.

**One `exec_always` line here lacks the `pkill` prefix:**

```
exec_always nwg-drawer -r -c 7 -is 90 …      # single instance in practice
```

`nwg-drawer -r` is resident mode and stays at one process across reloads (`pgrep -xc nwg-drawer`
→ `1` after 15 hours and many reloads).

**There is no terminal daemon here any more.** This section used to carry a second exempt line,
`exec_always --no-startup-id foot --server`, safe for a stronger reason than nwg-drawer's — it
*cannot* double-start, the second instance failing to bind
`$XDG_RUNTIME_DIR/foot-wayland-1.sock` and exiting on the spot. That line is gone with the switch
to `$term kitty`, which starts one process per window and has no daemon to prewarm. Kept here
because the reasoning is the reusable part — **"this daemon cannot
double-start" is a valid exemption from the `pkill` rule, and "it seems to stay at one process" is
not.** Only the second needs re-checking after every change.

**Do not add a `pkill` for a terminal to any `exec_always` line.** It would kill every open terminal
on every `swaymsg reload`, taking whatever was running inside them with it. Nothing in this repo
restarts a terminal — see §9.11 for what `theme` does instead.

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

The way to produce it is to add a role to one palette and forget the other. `theme` refuses to
render when the two sections of `palettes.toml` do not define exactly the same keys:

```
theme: nord and gruvbox define different keys: missing=['indicator'] extra=[]
```

That is the guard working, and it now covers *every* themed file rather than the two it could
parse — the check is on the table, not on a sample of the outputs. A template naming a role no
palette defines fails the same way, naming the file:

```
theme: waybar/.config/waybar/colors.gen.css.tmpl: no such role 'accnet' in this palette
```

Related: **a raw hex in an application config is now a bug**, not a style choice. It will survive a
switch and sit there in the wrong palette. §2.3 lists where values are allowed to live.

### 9.11 foot cannot be told to re-read its colours

foot has **no config-reload signal.** `SIGUSR1` and `SIGUSR2` look like one and are not: they toggle
between the `[colors-dark]` and `[colors-light]` blocks *that were loaded at startup*. Sending them
after editing the config does nothing new.

**The answer is that foot does not get restarted.** An already-open foot keeps its old palette
until you close and reopen it; a new one comes up correct. That is a deliberate limit, not a
missing feature: restarting terminals to recolour them destroys the processes inside them, which
are the user's and not the theme switcher's — an editor with unsaved work, a long build, a Claude
Code session. Nothing in this repo restarts a terminal, ever. (The rejected alternatives — the
dark/light-slot trick, the `--restart-terminals` flag this document once described but which never
existed, the tmux-survives caveat — are archived in
`docs/archive/2026-08-17-stock-deviations.md`.)

**kitty — now the default terminal — does not have the problem.** `SIGUSR1` is a genuine
config-reload there: every running instance re-reads `kitty.conf` and its `include`, so a palette
switch recolours open windows in place, without closing them and without touching what is running
inside. `theme` sends it at the end of every switch, and this is the only signal it sends to a
terminal. Nothing is restarted.

**Send it with kitty's own reloader, never with `pkill`:**

```sh
kitty +runpy 'from kitty.utils import reload_conf_in_all_kitties as r; r()'
```

`pkill -USR1 -x kitty` is the obvious version and it is a trap. `kitty @ …` and `kitty +…` helper
processes share the basename `kitty` and install **no** SIGUSR1 handler, so `pkill -x` matches them
and the default action for SIGUSR1 — terminate — kills them. kitty's own function filters to GUI
processes first (`kitty/utils.py`, `is_kitty_gui_cmdline`), so borrowing it means that filter can
never drift from what kitty considers itself to be. `theme` calls it for exactly this reason.

**`--single-instance` was measured and rejected** — one process serving every window means every
window shares a fate, for ~175 ms and ~50 MB per window, and it does not even fix the cold start.
The measurements, and the two usual pro-daemon arguments that were checked and found false for
kitty, are in the archive file above. The consequence that stays operative: a throwaway window —
waybar's htop popup, fuzzel's launcher — must never share a process with a long-lived shell, which
one-process-per-window gives for free.

Separately: **foot's plain `[colors]` section is deprecated** and warns on every launch. The
foot template uses `[colors-dark]`. With no `[colors-light]` block defined anywhere, foot picks
`[colors-dark]` unconditionally, which is what makes the section name a formality rather than a
light/dark switch.

### 9.12 waybar's `include` is overridden by the *including* file

Backwards from every other config format in this setup. In waybar, a key defined in `config` **wins**
over the same key coming from an `"include"`, regardless of where the `"include"` line sits.

So moving the clock's colours into `colors.gen.json` while leaving a `"clock"` object behind in
`config` does not merge them — the `config` copy silently wins and the included file has no effect
at all. The `clock` module had to be **deleted from `config` entirely** and defined only in
`colors.gen.json`. The symptom is a module that ignores the theme while every other module switches
correctly.

### 9.13 sway `$variables` cannot cross `config.d` ordering

`config.d/*` is read alphabetically (§9.6), so `default` — which holds the keybindings — is parsed
**before** `theme`, which is where `include ../colors.gen.conf` defines the palette. A `$role` used in a
binding in `default` is therefore not yet defined, and sway rejects the whole config:

```
Invalid border color $accent
```

This is why the screenshot bindings call `scripts/screenshot_region.sh` instead of inlining
`slurp -c $accent`: the script sources `~/.config/sway/theme.gen.env` at *runtime*, sidestepping parse
order completely. Any future binding that needs a colour should do the same rather than move files
around to fix the sort order.

### 9.14 Moving a config block wholesale loses whatever stayed behind

When the waybar clock moved into the rendered `colors.gen.json`, its `actions` block — scroll to shift the
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

### 9.16 htop can rewrite `htoprc` on quit, and does it by rename

Two distinct hazards from one behaviour. The trigger is narrow, the blast radius is not: htop saves
only on a **clean quit** (`q` or **F10**) **and** only if something changed during the session — but
when it does save, it writes the **whole file** from memory.

What counts as "changed" is wider than the F2 setup screen: toggling tree view with `t` or changing
the sort column both mark the settings dirty. A command-line `-d 2` does **not** — but its value
sits in memory, so any *other* change drags it to disk with everything else. That is how a `delay`
of 15 silently becomes 2.

**A hand-edit is only clobbered if that instance changed something.** An untouched htop never
writes, so an external edit survives it. But you cannot see from outside whether an instance is
dirty, so before hand-editing `htoprc`, kill any running htop with `pkill -9 htop`. With several
instances open it is whichever *saves* last that wins.

Only a clean quit saves — `q` **or F10**, which is the labelled Quit key in the function bar and so
the more discoverable of the two. **No signal saves.** SIGTERM (plain `pkill`) and SIGHUP discard
pending changes exactly as SIGKILL does; `-9` is the advice because it is unconditional, not because
the others would write.

**The write is `mkstemp` + `rename()`, not an in-place update.** `rename()` onto a path that is a
symlink replaces the symlink. This is why the `htop` package is folded (§5.2) — if `~/.config/htop`
were a real directory containing a symlinked `htoprc`, the first save would turn that symlink into a
regular file and every later change would go to `~/.config`, leaving the repo copy stale with no
error anywhere. Verify the fold is intact with:

```sh
ls -ld ~/.config/htop                       # must be a symlink into the repo
readlink -f ~/.config/htop/htoprc           # must resolve inside ~/repos/dotfiles
```

Because the repo file *is* the live file, any save shows up as a dirty working tree. That is
intended — it is how layout changes get captured — but a save rewrites everything, so the diff can
carry incidental settings you never meant to keep alongside the one you did. Read it before
committing rather than assuming it is only the change you set out to make.

**Layout keys.** The header meters live in `column_meters_N` / `column_meter_modes_N`, one pair per
column, with `header_layout` setting the column count and split. Modes: `1` bar, `2` text, `3` graph,
`4` LED. A column emptied in the UI is written as `!`, and every meter can end up piled into
`column_meters_0` — which renders as the right-hand CPUs appearing *below* the left ones rather than
beside them. Resetting `header_layout` back to `two_50_50` does not fix that; the meters themselves
have to be moved back.

---

### 9.17 A plugin that themes itself silently diverges from the palette

lualine's default `theme = 'auto'` reads `g:colors_name` and loads its *own* bundled theme of that
name — it ships both `nord` and `gruvbox`, so it always finds one and paints the bar a few shades
off the waybar above it, erroring never. `nvim/.config/nvim/statusline.lua` hands it a table built
from the fourteen roles instead. Apply the same rule to any future self-theming plugin: if it can
choose colours, feed it the roles explicitly.

### 9.18 tmux has no colour indirection, and no error for a missing one

Every tmux colour option takes a literal, so `tmux/.config/tmux/colors.gen.conf` carries the hexes
twice over: as `@thm_*` user options for the format strings (`#[fg=#{@thm_accent}]` — tmux does
expand `#{}` inside `#[]`) and as the plain style options, which take a colour and would not expand
a format. An **undefined** `@thm_foo` expands to nothing, `#[fg=]` is accepted, and the bar quietly
renders in the default colours — the GTK `@name` failure of §9.10 again. `check_consumers.sh` greps
the expanded format for an empty `fg=`.

### 9.19 A `#` arriving from data breaks the tmux status bar downstream of itself

tmux expands the format first and parses `#[...]` directives in the *result*, so a `#` from a pane
title, window name or branch name is indistinguishable from the start of one — and a value ending
in `#` pairs with the `#` of the next real directive to form `##`, an escaped literal, printing
that directive as visible text. A Claude Code pane title truncated onto an issue number ate
`#[nolist align=right]` and left the right-hand group unaligned.

Wrap **every** dynamic value in `#{qh:…}` (`#S`/`#W` don't escape; use
`#{qh:session_name}`/`#{qh:window_name}`), and have any `#()` script escape its own output. Two
constraints on `qh` that are not in the man page: it does **not** apply to a nested `#{…}`, only to
a plain variable name — hence chained modifiers, and a conditional wrapping two modified branches
rather than one modifier wrapping a conditional; and in `#{=/50/…;qh:x}` the trim runs **first**,
which is the only safe order, since escaping first lets the trim fall between the halves of a `##`
and recreate the dangling `#`.

### 9.20 A hand-written `status-format[0]` needs `list=on`/`nolist`

Without them, every `align=` group is ignored. Wrapping the `#{W:…}` window list in `#[list=on …]`
… `#[nolist align=centre]` is what identifies the elastic part of the line; without it tmux accepts
all three groups, reports nothing, and draws left, centre and right run together flush left.
Taking the format over also drops the per-window activity/bell *style* options — the stock
format's nested conditionals for them are gone, so those states have to be shown as characters in
`window-status-format`. Neither loss is visible except by attaching a client and looking.

### 9.21 mako: `ignore-timeout=1` does not mean "never expire"

It means *ignore the timeout the app asked for and use `default-timeout` instead* — so on its own,
under a global `default-timeout`, it makes a notification expire **sooner** than an app requested.
Pair it with `default-timeout=0` in the same criteria. A comment claiming otherwise sat over
`[urgency=high]` for months (the defect log in `docs/archive/2026-08-17-stock-deviations.md` has
the full story). `border-size` is also **not** directional, though
`margin`/`outer-margin`/`padding`/`border-radius` all are.

Related: **`mako --config <file>` is a real validator**, and the only one mako has. It fully
parses the config *and its includes* before touching D-Bus, so the running daemon is unaffected
and the second instance just exits on the name clash. Distinguish the parse error from the
expected `Failed to acquire service name` — `check_consumers.sh` greps for the former, since the
exit code is dominated by the latter.

### 9.22 yazi ignores an unknown theme key in silence

No error, no warning, not even in `--debug`. It is strict about everything else: `yazi --debug
</dev/null` exits 1 with a caret under a bad hex, a bad value, malformed TOML or an unknown
`[section]`, which makes it a better validator than most consumers here. But a *key* misspelt
inside a known section is dropped without a word, and the schema does move (`[manager]` was
renamed `[mgr]`). So the keys in `theme.toml.tmpl` are copied from the preset embedded in the
installed binary, not from documentation — re-derive them the same way after an upgrade:
`strings /usr/bin/yazi | grep -n 'schemas/theme.json'`, then read forward.

More yazi traps, all the same shape — **a bare array key replaces, only `prepend_*`/`append_*`
merge**: `keymap` wipes the whole preset keymap, and `[filetype] rules` and the four `[icon]`
tables replace theirs, so every *fallback* rule has to be restated or files quietly stop being
coloured or lose their icon. The `[icon]` tables are replaced here on purpose: the preset carries
725 rules painted from the Material palette, a third colour scheme fixed in the binary that
matches neither palette and does not move when one switches. Its `files` keys are **lowercase** —
yazi folds the filename before matching, so a capitalised key never matches and says nothing.

Interactively a bad config is not fatal either — yazi prints
`Press <Enter> to continue with preset settings...` and starts anyway, which is why
`check_consumers.sh` closes stdin and then asks whether the theme actually *loaded*.

### 9.23 The claude usage widget: two data sources, one hard read-only rule

`waybar/.config/waybar/scripts/claude_usage.py` (design:
`docs/specs/2026-08-22-claude-usage-widget-design.md`) reads two independent sources: the
undocumented `api.anthropic.com/api/oauth/usage` endpoint for limits/reset countdowns, and
`~/.claude/projects/*.jsonl` (scanned incrementally by byte offset) for the per-model token bars.
**`~/.claude` is read-only, full stop** — it reads `.credentials.json` for the access token but
never refreshes it; Claude Code's own daemon owns rotation, and a second writer racing it is
exactly the failure mode [claudebar](https://github.com/mryll/claudebar) has (it writes OAuth
token refreshes back into `.credentials.json`) and exactly what this widget rejects as a design.
Cadences follow from the endpoint being undocumented and rate-limiting aggressively: `API_TTL=300`
(never poll faster), `FORCE_DEBOUNCE=30` (click-spam on `--refresh` must not be able to 429 the
widget stale), `FETCH_TIMEOUT=5` (a stale bar beats a frozen one). `custom/claude`'s
`exec-on-event: false` in waybar's config exists for the same reason — the default `true` re-execs
the script on every click, racing the `--refresh` already in flight — and inside the script,
`fcntl.flock` on `~/.cache/claude-usage/lock` makes the interval run, a clicked `--refresh`, and
the signal-8 re-exec a single writer regardless of which one wins the race. If `theme.gen.env` is
missing or a role fails to parse, `FALLBACK_THEME` uses **Pango named colours only** (`black`,
`gray`, `yellow`, …) — `check_hex.py` scans this file too, and a hex literal here would fail it
the same as anywhere else. All widget state — fetched limits, JSONL scan offsets, debounce
timestamps — lives in `~/.cache/claude-usage/`; deleting it forces a full rebuild on the next run
(fresh JSONL scan, fresh fetch, TTL ignored).

### 9.24 A CodeRabbit "Review failed" banner is the app failing, not a finding

PR #5 opens with `> [!CAUTION] Review failed — The pull request is closed.` and carries **zero
findings**. That box reports the GitHub App's own failure, not a verdict on the code: the PR was
merged **eight seconds** after it was opened (`07:50:33Z` → `07:50:41Z`), long before the app got
to it. The failure mode is entirely social — anyone landing on the PR months later sees a red
CAUTION banner sitting over merged code and reasonably concludes the review found something bad.

**It cannot be recovered after the fact.** `@coderabbitai full review` on the already-closed PR was
tried on 2026-08-22: the app engages for a few seconds, then settles back to `Action not completed
— Pull request is closed.` Verified, not assumed. So the rule is timing, not tooling — if app-side
review is wanted, **leave the PR open until the app has posted its review**, then merge. Auto-merge
on a fast-approving PR loses the review the same way.

The CLI has no such dependency, because it does not need a PR to exist at all:

```sh
coderabbit review --base origin/main --committed
```

The app's **pre-merge checks** are configured in `.coderabbit.yaml` at the repo root, and one of
them is turned off there: docstring coverage. It scores every function a diff touches against a
default 80% threshold, which the Python here cannot reach by construction — the widget's own
functions carry docstrings, but its test suite documents each case with a `#` comment above it, so
a PR touching a dozen tests scores in the teens (14.29% on #12, 15.38% on #14, 16.67% on
#15) with nothing actually wrong. That the check is *configured off* rather than merely quiet is
visible in the pre-merge table: #13 touched no Python and still printed a "skipping" row, whereas
#16 — the PR that added this file — prints no docstring row at all. The reason to silence it rather than live with it is this section's own rule: a
banner that is always present stops being read, and the whole point of §9.24 is that these banners
have to be read rather than merged past. `mode` is a **string** in CodeRabbit's schema, so `"off"`
must be quoted — a bare `off` is YAML's boolean `false` and fails validation while looking right.

That is what actually covered #5 — range `4d6e404..b8702a0`, run twice, with the findings and their
dispositions written up in `docs/specs/2026-08-22-claude-usage-widget-design.review.md`. Prefer it
on this repo: work here lands in small PRs that are often merged the moment they go green, which is
exactly the shape the app misses.

### 9.25 The lock screen's wallpapers: pre-synced, never fetched at lock time

`lock.sh` picks a random image from **`~/Pictures/walls/<active palette>/`** and passes it as
`--image … --scaling fill`. The images come from [dharmx/walls](https://github.com/dharmx/walls)
and are put there by **`walls-sync`** (`bin/.local/bin/walls-sync`), a command you run by hand.

**Why they are not in this repo.** The no-binaries rule, the same one that keeps the two desktop
wallpapers in `~/Pictures/wallpapers`. It is ~320 MB across both palettes — 75 MB for gruvbox, 245
MB for nord, at the default resolution floor — and none of it is configuration. Nothing lands
inside the tree, so no `.gitignore` entry was needed or added, which is the test of whether the
rule was actually followed rather than worked around.

**Why syncing is a separate manual command, and this is the whole design.** *The lock screen must
never touch the network.* It is asked for when the idle timer fires, before suspend, and at
`$mod+f1` — on a train, on dead wifi, halfway through a resume — and a lock that waits on a socket
is a lock that does not happen. So `lock.sh` only ever picks from what is already on disk. The same
argument one step down is why `theme` does not do it either: switching runs often and has to stay
instant and offline, while upstream changes about never. All of the network is confined to
`walls-sync`, where a timeout is a line on the terminal you are watching.

**The palette name *is* the directory name**, upstream and locally — `gruvbox` and `nord` are
folders in dharmx/walls and keys in `palettes.toml`, and that coincidence is load-bearing at both
ends: `walls-sync` asks `palettes.toml` what to sync, and `lock.sh` spells the active palette
straight into the path. **Rename a palette and you must rename the directory with it**, or the lock
screen silently drops back to a solid colour with nothing to say about it. `walls-sync` is the half
that fails loudly — a palette upstream has no folder for is an error on a command you are watching.

**The fail-safe chain.** Every one of these ends with the screen still locking, on the solid
`$desktop` colour: no palette recorded (fresh machine, `theme` never run); a palette name that is
not a plain word — it is a path component, so `../../etc` in the state file is *refused*, not
sanitised; no such directory; a directory with no images in it; a pick that is not a readable
regular file; a colon anywhere in the path, because swaylock reads `--image` as `[<output>:]<path>`
and would take the leading part as a monitor name. The selection is `find -print0 | shuf -z -n1`
read with `read -d ''`, so a filename with spaces — upstream's are whole sentences — survives as
one argv item. Only image extensions are eligible, which is also what stops a `.part` file left by
an interrupted `walls-sync` (a truncated image by definition) from ever being the pick.

**The pre-existing colour fail-safe stays bare, deliberately.** When a role fails to parse,
`lock.sh` still does `exec swaylock "$@"` with *no flags at all* — no `--image` either. That path
runs when the machine's own configuration is broken, so it must be the dumbest, most
obviously-valid invocation available: every flag it does not carry is a flag that cannot be the
reason it failed. The wallpaper is chosen *after* that loop so the ordering says so too.

**Verified, not assumed:** swaylock 1.8.6 logs `Failed to load background image` and **carries on
to lock** rather than exiting, so even a corrupt image is cosmetic. Checked by running the real
binary with `XDG_RUNTIME_DIR` pointed at an empty directory and `WAYLAND_DISPLAY` at a socket that
does not exist — it cannot lock anything from there, and the image is parsed before the compositor
is contacted, which makes the two failures distinguishable in the log. `lock.sh` checks the file
anyway: that guarantee belongs here, not in whatever swaylock does next release.

**Why there is a resolution floor.** Over half of upstream is smaller than this panel's 3840x2160,
and the worst of it is unusable — nord ships a 435x492 and a 794x1024, gruvbox a 1017x572 — which
`--scaling fill` blows up to fill the screen. A random picker served one of those about half the
time. `walls-sync` therefore enforces a minimum, default **1920x1080** (at most a 2x upscale here),
overridable with `--min WxH`. It is enforced at **sync** time, never at lock time: `lock.sh` must
not be reading image headers on every lock. Raising it later is just a re-run — `walls-sync --min
2560x1440` re-fetches nothing it already has and prunes what no longer qualifies, printing every
removal with the dimensions that condemned it. The cache is a mirror the command owns and every
file in it is one request away, which is what makes converging it that way safe.

Dimensions are read from the file's own header (PNG, JPEG and WebP, in `walls-sync`, stdlib only —
no Pillow, no ImageMagick), and **a header that will not parse keeps the file**: a parser must
never be the reason an image is deleted. The parser sniffs the magic rather than trusting the
extension, and that is not fastidiousness — `gruvbox/a_close_up_of_a_circuit_board.png` is a
lossless WebP, and it is 1017x572, i.e. the single worst image in that folder was one an
extension-trusting check would have kept. All 194 files were cross-checked against `identify` while
this was written: 194 agreements, 0 disagreements.

### 9.26 Idle policy depends on AC vs battery, and lives in `idle.sh`

`config.d/autostart_applications` no longer execs `swayidle` with a fixed timeout chain. It execs
**`scripts/idle.sh`**, a small daemon that owns that decision because it is the one thing about the
idle chain that `config.d/*` cannot express: it has to change *while the session is running*, on a
plug/unplug, with no `swaymsg reload`.

**The policy.** On AC: lock at 300s, never auto-suspend — a machine plugged in and idle is not one
anyone wants asleep on its own. On battery: lock **and** `systemctl suspend` both at 300s — idle
screen time on battery is exactly what this exists to stop. Screen-off via DPMS at 600s is
unconditional, unchanged from before. Ordering between the 300s lock and the 300s suspend on
battery does not matter: `before-sleep` still calls `lock.sh -f` independently of what triggered
the sleep, so a suspend that somehow beat the lock still comes back locked — the same double
insurance that already existed for lid-close and the power menu's Suspend entry.

**Why polled, not event-driven.** `idle.sh` reads `/sys/class/power_supply/AC/online` every 15s
and only touches `swayidle` when that value changes. `udevadm monitor` or `acpid` would be event-
driven and cheaper, but `acpid` is not installed (a new package for one boolean), and `udevadm
monitor`'s output is a debugging format this repo would have to trust to keep parsing correctly
across systemd releases for something nobody is timing to the second. A 15s lag between unplugging
and the policy actually switching is not a defect here.

**The fail-safe.** A read of `AC/online` that fails (missing, unreadable) is treated as AC — lock
only, no auto-suspend — not battery. Same reasoning as `lock.sh`'s own fail-safes (§9.25): losing
track of power state must never be the reason a machine suspends itself.

**Process hygiene.** `idle.sh` is itself a long-lived daemon started via `exec_always`, so it needs
the same `sh -c 'pkill -x idle.sh; …'` treatment any `exec_always` daemon does (§9.2) — and it also
`pkill -x swayidle`s its own child every time it switches state, plus once more from
`autostart_applications` on every reload, so a reload or a power-source flip can never leave a
`swayidle` running that nothing still points at:

```sh
pgrep -xc idle.sh      # exactly 1
pgrep -xc swayidle     # exactly 1
```

Check those **after a fresh login**, not only after a `swaymsg reload`. The two take different code
paths through sway, and the reload path is the forgiving one: this exact pair read 1/1 on demand
while the machine had in fact booted with neither process running (§9.2).

**Changing the timeouts.** Edit `scripts/idle.sh`, not `config.d/autostart_applications` — the
latter only starts the wrapper now and has no timeout values of its own.

### 9.27 A waybar state class is a *GTK* class, and the GTK theme styles it too

waybar puts a module's state into a bare CSS class — `warning`, `critical`, `muted`,
`disconnected`. Those go straight onto the GTK widget, into the same flat namespace GTK's own
stock classes live in. **`warning` is one of GTK's own.** It is part of GtkInfoBar's set —
`.info`, `.warning`, `.question`, `.error` — and the Nordic theme styles that set *unscoped*:

```css
/* /usr/share/themes/Nordic/gtk-3.0/gtk-dark.css */
.info, .warning, .question, .error { background-color: … }
.warning { background-color: #c3674a; }
```

so any waybar module in its warning state painted a solid infobar fill. cpu, memory and battery
take `warning` from their `states` in `config`; `custom-claude` takes it from
`scripts/claude_usage.py` and sits there for most of a working day, which is why that one is where
it was noticed — an orange block behind digits that `style.css` had only ever given a *colour* to.

**Nothing in this repo was wrong when it was written, and that is the interesting part.** The
widget was built under gruvbox, whose GTK theme is Colloid, and Colloid only ever *scopes* the
class — `infobar.warning`, `entry.warning`. A bare `.warning` matches nothing there. The
stylesheet's silence about backgrounds was therefore correct under one palette and a bug under the
other, and the switch that exposed it came months later. Same shape as §9.10: not a value that is
wrong, a value that was never declared, with something else quietly supplying it.

**The fix is to declare the paint rather than inherit it.** `style.css` lists every module once
more, purely to say `background: transparent; border: none; box-shadow: none` — the three
properties Nordic's infobar rules supply. `#mode` still gets its `@accent2` by coming later at
equal specificity, and the `blink-warning`/`blink-critical` keyframes still drive the background,
because an animated value outranks a normal declaration.

Deliberately **not** `#waybar *`: `#workspaces button` is a real GtkButton and takes a background
from the GTK theme under *both* palettes, as it always has. Flattening it is a look change, not a
fix, and there is no way to say "the theme's button background, minus the infobar rules" in CSS —
the override would have to invent a colour. The residual is that a workspace *named* `warning`
would still get an orange pill; workspaces here are numbered.

**Verification is a render, not a grep.** Reading `style.css` back for the missing
`background-color` only re-checks the fix. `tests/check_waybar_paint.py` builds each module
offscreen — a widget of that name inside a `#waybar` parent — bare and then once per class, under
**every** GTK theme `palettes.toml` names, and fails on any class that changes the painted
background. Testing the theme that is *not* switched on is the entire point: this bug was green
under gruvbox for as long as gruvbox was on. It tests the whole stock set rather than the classes
waybar emits today, because the next collision will be a name nobody thought to look up, and it
turns `gtk-enable-animations` off so `#memory.critical`'s blink does not make the sample depend on
when the frame was grabbed. It needs a display and the themes installed, so it lives in
`check_consumers.sh`, and it exits 77 → `skip` rather than green when it cannot run.

Confirmed on the live desktop by starting a second waybar with `-s` pointed at the fixed
stylesheet: sway gives it its own exclusive zone, so it lands *beside* the real bar rather than on
top and the two photograph side by side. 13103 pixels of `#c3674a` in the old one, 0 in the new,
with the same 297 pixels of `@warning` on the digits — the state and its colour intact, only the
theme's block gone.

### 9.28 A role can be legible in one palette and unreadable in the other

The waybar tooltip's secondary text — the header subtitle, the reset countdowns, the weekday
labels, the pace legend, `(7d)`, the footer — was all painted `muted`. Under nord it was very
nearly invisible, and measuring says why:

| | `muted` on that palette's GTK tooltip background | |
|---|---|---|
| nord | `#4c566a` on `#282d37` | **1.87:1** — under even the 3:1 large-text floor |
| gruvbox | `#7c6f64` on `#191818` | 3.64:1 — under 4.5:1, but legible |

**It was never right; gruvbox was just forgiving enough to hide it.** The widget was built under
gruvbox, and the same role there merely reads as quiet. Exactly the shape of §9.27 one section up,
from the other direction: that one was the GTK theme supplying a value this repo never declared,
this one is a value this repo did declare being wrong for half the palettes.

Note the background is **not** `bg`. GTK paints tooltips from its own theme —
`rgba(40, 45, 55, 0.93)` in Nordic, `rgba(25, 23, 23, 0.9)` in Colloid — both darker than the bar,
and translucent, so a light window behind them is the worst case for light text. Measure against
the surface the text actually lands on, not the palette's nominal background.

**The fix is the `dim` role** (§3.1), not a nudge to `muted`: the two jobs are different, and
`muted` still has to be able to disappear where it is chrome. Values are `#a0a8b6` for nord — nord
has nothing between nord3 and nord4, so this is 60% of the way up that line — and `#a89984` for
gruvbox, which is the scheme's own `fg4`/comment grey, so nothing is invented.

**The floor has to hold on the worse composite, and translucency decides which that is.** A
tooltip at 93% alpha is 7% whatever is behind it, so a white window lightens the background and
*reduces* contrast for light text. Measure both ends:

| | over the desktop's dark windows | over a white window |
|---|---|---|
| nord `#a0a8b6` on Nordic's tooltip | 5.77:1 | **4.63:1** |
| gruvbox `#a89984` on Colloid's tooltip | 6.37:1 | **4.86:1** |

The first nord value tried was the plain nord3↔nord4 midpoint, which measured a comfortable 5.01:1
over dark and **3.92:1** over white — under the floor in exactly the case that is easy not to
look at. CodeRabbit caught it on PR #19 by compositing over white; the fix was to walk up the same
line to the *first* step that passes, not to the most contrast available. Every step past that
buys margin the floor never asked for and spends hierarchy: `#a0a8b6` still sits 1.8x quieter
than `fg`, which is what keeps the hierarchy readable as hierarchy.

**Verified by rendering, not by arithmetic alone.** `pango-view --markup --margin=8
--background=<the tooltip colour>` on the widget's real tooltip output, one image per palette,
compared against the same tooltip built with the old code. The contrast numbers say a change
happened; the images say it reads.

While in there: the header showed `· Default Claude Ai`. Two faults, one line. It preferred
`rateLimitTier` over `subscriptionType` where the design doc says
`<subscriptionType/rateLimitTier>` — and `rateLimitTier` is the constant `default_claude_ai` for
everyone, i.e. no information, where `subscriptionType` is the plan. And `str.title()` renders
`ai` as `Ai`, which reads as a typo. Now `· Pro`, via a `title_case()` that keeps an acronym set;
it also stops mangling `max_20x` into `Max 20X`, since Anthropic writes that multiplier lowercase.

---

## 10. Troubleshooting

| Symptom | Likely cause | Check / fix |
|---|---|---|
| Config change had no effect | Package unfolded, new file not linked | `[ -L ~/.config/<pkg> ] && echo folded \|\| echo unfolded` (§5.2 — `ls -la \| grep` silently passes when it shouldn't); `stow -R <pkg>` |
| Config change had no effect | Symlink points outside the repo | `readlink -f ~/.config/<pkg>` |
| Change needs a full logout to apply | Used `exec` instead of `exec_always` | §9.2 |
| Screen never locks | swayidle not running, or many are | `pgrep -xc idle.sh` and `pgrep -xc swayidle` — both must be exactly `1` |
| Screen locks immediately / repeatedly | Multiple swayidle instances racing | Same check; the `pkill` prefix is missing |
| Machine suspends when plugged in, or never suspends on battery | `idle.sh` hasn't noticed a power-source change yet (15s poll), or `AC/online` is unreadable | Wait 15s; `cat /sys/class/power_supply/AC/online`; §9.26 |
| Lock screen is a solid colour, no wallpaper | Cache never populated, or a palette was renamed without renaming its directory | `ls ~/Pictures/walls/"$(cat "${XDG_STATE_HOME:-$HOME/.local/state}"/theme/palette)"`, then `walls-sync`; §9.25 |
| Lock screen wallpaper looks blurry or pixelated | An image below the resolution floor | `walls-sync` prunes on every run; raise it with `walls-sync --min 2560x1440`; §9.25 |
| `walls-sync` exits non-zero | One or more files failed; everything else synced | Read the `walls-sync:` lines on stderr, then re-run — it retries failed or incomplete entries and skips only files whose size already matches upstream; §9.25 |
| A waybar module has a coloured block behind it | Its state class collides with a GTK stock one the theme styles bare | `sh tests/check_consumers.sh` names the module and the class; §9.27 |
| Tooltip text is there but barely visible | `muted` used where `dim` belongs — `muted` is chrome and may disappear | §3.1, §9.28; measure against the GTK tooltip background, not `bg` |
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
| `htoprc` edit reverted | A running htop flushed its in-memory settings on quit | `pkill -9 htop`, then edit; §9.16 |
| htop changes stopped reaching the repo | `rename()` replaced the symlink | `ls -ld ~/.config/htop` must be a symlink; §9.16 |
| htop right-hand CPUs render below the left | All meters piled into `column_meters_0` | §9.16 |
| A window has no border at all | `smart_borders on` with one window | Set `smart_borders off`; §9.8 |
| One GTK app is the wrong theme | It predates the theme change | Restart it; §9.9 |
| `$mod+Return` does nothing | kitty not installed, or its first start is failing | `kitty --version`, then run `kitty` from another terminal and read the error |
| An open **foot** is still the old palette after a switch | foot cannot reload colours, and nothing restarts it | Close and reopen it; §9.11 |
| An open **kitty** is still the old palette after a switch | The SIGUSR1 never arrived | `theme` prints `kitty … reloaded (SIGUSR1)` when it sends one; §9.11 |
| One surface still the old palette, everything else switched | A running GTK app (§9.9), an open foot (§9.11), or an unfolded package that was stowed before `theme` first ran, so the rendered file was never linked | Restart the app; else `readlink` the file under `~` and `stow -R <pkg>` if it is missing; §3.3 |
| A widget renders **black** | A GTK CSS `@name` used in a hand-written file but produced by no template, or a stale/deleted rendered file | Re-run `theme` (re-rendering repairs artefacts); if the name is not a role, add it to **both** palettes; §9.10 |
| `theme: …tmpl: no such role '…'` | A template names a role `palettes.toml` does not define | Add the role to both palettes, or fix the typo in the template; §9.10 |
| `theme: … define different keys` | The two palettes have drifted | §9.10. This is the guard, not a fault |
| Folder icons don't match the theme | papirus-folders was skipped — it needs `sudo`, so `theme` only runs it from a terminal | Re-run `theme` in a terminal, or `sudo papirus-folders -C <colour> --theme Papirus-Dark` |
| Cursor is the default X arrow | Theme name case | `ls -d /usr/share/icons/<name>` — XCursor resolves by case-sensitive path |
| A `$role` breaks `sway --validate` | `Invalid border color $accent` — the binding is in `default`, parsed before `theme` | §9.13; source `theme.gen.env` from a script instead |

### Verification sweep

```sh
sway --validate -c ~/.config/sway/config     # before any reload
pgrep -xc idle.sh                             # exactly 1
pgrep -xc swayidle                            # exactly 1
fc-match "JetBrainsMono Nerd Font"            # not NotoSansMono
swaymsg -t get_outputs                        # scale 2 on eDP-1
gsettings get org.gnome.desktop.interface color-scheme    # 'prefer-dark'
systemctl --user show-environment | grep XDG_CURRENT      # =sway
readlink -f ~/.config/sway ~/.config/waybar ~/.gtkrc-2.0  # all inside the repo

theme                                                     # re-renders; prints "N files rendered … [name]"
cat "${XDG_STATE_HOME:-$HOME/.local/state}/theme/palette" # nord | gruvbox
```

Folding — the property §5.2 depends on, and the one that a stray file in `~/.config` quietly breaks:

```sh
for p in sway waybar foot kitty mako fuzzel nwg-drawer htop; do
    printf '%-12s ' "$p"
    if [ -L ~/.config/$p ]; then echo "folded (symlink)"; else echo "UNFOLDED (real dir)"; fi
done
```

Eight lines, every one `folded (symlink)`. Use this form, not `ls -la ~/.config | grep -E ' foo$'` —
see §5.2 for why that one passes silently when things are fine and only speaks up when they break.

Then trigger each themed surface by hand: `$mod+d`, `notify-send test`, `$mod+Shift+d`, the waybar
clock tooltip (and *scroll* on it — §9.14), `$mod+f1`, thunar, a GTK4 app, `$mod+Return`, `Print`,
`vim`, `ls`.
