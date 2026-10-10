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
azote, swappy, cliphist). Three of those have since changed here: kitty is the terminal instead of
foot, which was kept as a themed fallback and then retired on 2026-09-28 (§9.11); swaylock is the
lock screen instead of gtklock (§4.3); and fuzzel is the only launcher, nwg-drawer having been
dropped the same day (§4.1).
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
            nm-applet, cliphist watchers, polkit agent
```

**Alphabetical order is load-bearing.** `application_defaults` is read before `default`, and
`theme` last. Anything that must win a conflict belongs in a later-sorted file.

`exec` runs **only at sway startup**. `exec_always` runs at startup *and* on every
`swaymsg reload`. Choosing wrong is the single most common bug in this config — see §9.2.

### 2.2 How GTK theming actually reaches applications

**The GTK look is plain Adwaita in its dark variant, for both palettes** — Omarchy's choice, adopted
on 2026-09-28. GTK apps are neutral grey rather than tinted to the palette; in exchange, nothing in
this section changes on a switch, so the files below are tracked as they are rather than rendered.
Until then each palette named its own GTK theme (Nordic, Colloid-Gruvbox), `gtk.css` overrides
re-coloured libadwaita, and papirus-folders tinted the folder icons per palette — six templates, two
out-of-repo theme installs and the one step of a switch that needed `sudo`, all for window chrome.
Adwaita is compiled into GTK, so there is nothing to install.

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

~/.config/gtk-4.0/settings.ini  ────>  GTK4 apps
gsettings color-scheme          ────>  libadwaita apps  ← the one that matters
```

`~/.gtkrc-2.0` and `~/.config/xsettingsd/` are no longer carried. gtk2 is not installed and
`xsettingsd` never was, so both files were rendered on every switch for readers that did not exist;
XWayland clients fall back to what `gtk-3.0/settings.ini` and Xft give them.

**The critical thing to understand:** *libadwaita apps ignore `gtk-theme-name` completely.* They
decide light vs dark from the gsettings `color-scheme` key alone, which is why `import-gsettings`
was extended to set it. There is also no `Adwaita-dark` theme to name — that directory comes from
`gnome-themes-extra`, which is not installed, and GTK3 given the name renders *light*. Dark GTK3
comes from `gtk-theme-name=Adwaita` plus `gtk-application-prefer-dark-theme=1`, which is what
`settings.ini` says.

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
overwrites it. One file is the exception and cannot carry the marker, because yazi reads its
`theme.toml` at a hardcoded path and takes no include; it is listed individually in `.gitignore`.
That list is structural — it can only change if an application with a hardcoded config filename
joins the desktop, which is exactly what happened when yazi arrived on 2026-08-16. It was seven
entries until the six GTK files stopped being rendered (§2.2).

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
| **`accent`** | sway focused border, waybar focused workspace, fuzzel border |
| `accent2` | focused-inactive border, calendar weekdays, waybar mode |
| `indicator` | sway split indicator — where the next window will open |
| **`critical`** | urgent window, critical CPU/battery, destructive actions |
| `warning` | warning states, "today" in the calendar, idle inhibitor on |
| `success` | battery charging, success states |
| `desktop` | one shade below `bg`: the fallback behind the wallpaper slot, the letterbox around an image, and the lock colour when there is no usable image (§9.25) |

**`muted` and `dim` are not shades of one idea, and the split is the whole point.** `muted` says
"this is chrome" — a border, a rule, a weekday header — and is allowed to be almost invisible.
`dim` says "this is text you are meant to read, quietly", and therefore carries a floor: **4.5:1
against the background it lands on**, in *both* palettes — and where that background is
translucent, against the worse of its composites, not the flattering one (§9.28). Before it
existed, everything secondary
used `muted`, which measured 1.87:1 on the GTK tooltip under nord — the widget was written under
gruvbox, where the same role scrapes 3.64:1 and merely looks quiet (§9.28). If a new role is ever
added for text, give it a measured floor in this table or it will drift the same way.

`desktop` being darker than `bg` is what turns the gaps between windows into visible channels when
gaps are on (`$mod+g`; everyday they are zero, which is why `smart_borders` is off — §9.8) and
`desktop` is what shows in them: no usable wallpaper, or one that does not fill the output. Over a
full-screen wallpaper the gaps show the wallpaper, so tuning `desktop` changes nothing there. Nord
has nothing below `nord0`, so its value is a hand-darkened one; Gruvbox ships the idea as `bg0_h`.
`palettes.toml` records both.

A third group is the **16-colour terminal ramp**, under `[<palette>.ansi]`. Eight of its slots are
role colours; the other eight are not, and are kitty's. They used to be duplicated across two
terminals with a comment asking that they be kept in step by hand, until foot was retired.

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

Until 2026-09-28 "Nordic" was nonetheless correct in two places: the Nord **GTK theme** is named
`Nordic` (AUR `nordic-theme`), and **papirus-folders** calls its Nord folder colour `nordic`. Both
retired with the move to plain Adwaita (§2.2), so no name in the live setup is spelled that way
any more — but `/usr/share/themes/Nordic` stays on disk until `nordic-theme` is uninstalled, and
§9.27 is the story of what that theme did to waybar.

### 3.3 Switching

```sh
theme              # re-render the current palette
theme nord         # switch
theme --list       # what is available
```

`theme` renders every template, records the palette in `$XDG_STATE_HOME/theme/palette`,
then reloads: `sway --validate` before `swaymsg reload` (which also restarts waybar, re-runs
`import-gsettings`), then `makoctl reload` separately, because mako is
`exec`'d rather than `exec_always`'d and a sway reload does not restart it.

**Switching is not a repo change.** The state file lives outside the repo and every rendered file is gitignored, so a switch
leaves `git status` untouched. `tests/theme_test.sh` asserts it.

**`theme` must run before `stow` on a fresh clone.** The rendered files do not exist in a clone,
and the one unfolded package that carries a template (`yazi` — `bin`, `claude`, `gtk` and
`herdr` are also unfolded but carry none) links file-by-file — a file created
after `stow` is silently absent until `stow -R`. The folded packages pick it up for free. See
§5.2.

Applying is idempotent: re-running repairs a deleted or edited artefact.

**kitty reloads in place.** `theme` sends it SIGUSR1 through kitty's own reloader at the end of
every switch, and open windows recolour without being restarted (§9.11).

---

## 4. Package manifest

The install lists a new machine actually consumes are `packages.txt` (official repos) and
`packages-aur.txt` (AUR) at the repo root — `sudo pacman -S --needed $(cat packages.txt)`, then
`yay -S --needed $(cat packages-aur.txt)`. Every entry resolves from Arch's own
`core`/`extra`/`multilib` or the AUR — the one that needed EndeavourOS's repo, its `welcome`
greeter, was dropped on 2026-09-28 along with `firewall-applet`, a ~40 MB tray icon for a firewalld
that runs without it (`systemctl is-active firewalld`). `setup.sh` warns about anything from either list
that is not installed. The files also carry the tools the configs here invoke that the
tables below assume (vim, neovim, starship, htop, and yazi's
`fd`/`ripgrep`/`fzf`/`jq`/`poppler`/`imagemagick`). The tables say *why* each package is here
and what breaks without it. vim is installed but no longer configured here: the `vim` package
retired on 2026-09-28, `$EDITOR` is `nvim`, and plain vim is kept for root and rescue shells.

### 4.1 Required — the setup is broken without these

| Package | Source | Why | Symptom if missing |
|---|---|---|---|
| `sway` `swaybg` `swayidle` | repo | Compositor, background, idle daemon | — |
| `waybar` | repo | The bar | No bar |
| `kitty` | repo | **The terminal.** `$term` is `kitty`; also the dropdown, fuzzel's `terminal=`, and waybar's htop/nmtui click targets. One process per window, no daemon — §9.11 has the measurements | `$mod+Return` does nothing |
| `fuzzel` | repo | **The** launcher — `$mod+d` and the waybar launcher button — and the cliphist picker. The only one since 2026-09-28: nwg-drawer's app grid (`$mod+Shift+d`, resident, ~40 MB and its own themed stylesheet) duplicated it, and Omarchy ships one launcher too | Launcher and clipboard history dead |
| `mako` | repo | Notifications | Silent desktop |
| `swaylock` | repo | Lock screen, driven by `sway/scripts/lock.sh` — `$mod+f1`, the 300s idle timeout (via `idle.sh`, §9.26), before-sleep, and the power menu's Lock entry. No config file of its own: the script derives every colour from the live palette and passes them as flags (§9.13), and locks over the palette's wallpaper slot when its guard passes, else the solid `$desktop` colour (§9.25) | **Machine never locks** — `lock.sh` execs a binary that is not there, and swayidle's timeout fires into nothing |
| `grim` `slurp` `satty` `wl-clipboard` `tesseract` (+`tesseract-data-eng`) `zbar` `wf-recorder` | repo | Screenshots (grim shoots, satty crops/annotates, §9.32), clipboard, OCR (`tesseract`), QR (`zbar`), recording (`wf-recorder`; `slurp` is its region picker) | Print bindings dead; each missing tool disables only its own mode, with a notification naming the package |
| `cliphist` | repo | Clipboard history | `$mod+Ctrl+v` dead |
| `autotiling` | repo | Splits along the longer axis automatically | Manual `$mod+v`/`$mod+b` for every split |
| `pamixer` `brightnessctl` `playerctl` | repo | Media/brightness keys | Function keys dead |
| `polkit-gnome` | repo | Auth prompts for GUI privilege escalation | GUI admin actions fail silently |
| `stow` | repo | Deploys this repo | |

### 4.2 Added by this setup

| Package | Source | Why |
|---|---|---|
| `papirus-icon-theme` | repo | Icon theme, referenced by mako, fuzzel and GTK. Untinted since 2026-09-28 — `papirus-folders` drove a per-palette folder colour and was the one step of a switch that needed `sudo` (§2.2) |
| `ttf-jetbrains-mono-nerd` | repo | **The patched Nerd Font.** See §9.4 — the base install has only `ttf-nerd-fonts-symbols`, a symbols-only fallback |
| `google-chrome` | **AUR** | **The browser.** `$mod+o` and `$BROWSER`, and the default handler for `http`/`https`/`text/html` — §8 sets that, it is not stowed. The package ships `/usr/bin/google-chrome-stable` **only**: no bare `google-chrome`, and `Google-chrome` is the X11 WM_CLASS (`application_defaults` matches on it to assign workspace 2), never a command. Get the name wrong and `$mod+o` fails silently |
| `kanshi` | repo | Display hotplug profiles |
| `gdb` | repo | crash-diagnose's symbolised backtrace (§9.33). Installed today only as a dependency of `debugedit`, so a cleanup could orphan it, and a report then just says "no symbolised backtrace" |
| `tmux` | repo | Terminal multiplexer. Optional to the desktop, but its status bar is themed from `palettes.toml` like everything else, so a machine without it simply renders a `colors.gen.conf` nobody reads. `git` is a soft dependency of the bar's right-hand segment — absent, the branch is blank rather than broken |
| `yazi` | repo | Terminal file manager, themed from `palettes.toml` like everything else. Optional to the desktop; a machine without it renders a `theme.toml` nobody reads. Launched as `y` from any interactive bash — the wrapper in `bash/.bashrc` leaves the shell in whatever directory yazi ended up in, which plain `yazi` cannot do. **Optional extras, none required:** `7zip` (archive preview and the `extract` opener — without it archives show nothing), `ffmpegthumbnailer` (video thumbnails), `perl-image-exiftool` (the preset's `exif` opener), `zoxide` (makes the preset's `Z` binding work rather than error), `chafa` (image fallback outside kitty). `fd`, `ripgrep`, `fzf`, `jq`, `poppler` and `imagemagick` are already present and are what `s`, `S` and `z` use. Image previews need nothing extra: kitty speaks its own graphics protocol and `tmux.conf` already sets `allow-passthrough on` |
| `lualine.nvim`, `nvim-web-devicons` | **self-installing** | nvim's statusline. Fetched by `vim.pack.add` in `init.lua` on first launch, into `~/.local/share/nvim/site/pack/core/opt` — nothing to clone by hand, and nothing in `~/.config/nvim` (§5.2). nvim's *colourschemes* are still written from the §3.1 roles rather than cloned, and lualine is themed from them too, so no plugin decides a colour here |

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
widgets; plain swaylock draws one password ring over the palette's wallpaper, or a solid `$desktop`
field when there is none (§9.25), and nothing else. The power buttons are the only real loss, and they are not lost —
`$mod+Shift+e` reaches the same suspend/reboot/shutdown actions through the command palette's
System group (`menu.py --group System`, §7), from an unlocked session. The clock is on waybar. The avatar has no replacement and none is wanted.

`swaylock-effects` (blur, screenshot backgrounds, a clock) was considered and declined. What was
rejected is *an unofficial fork as a dependency*, and separately *a 22 MB image living in the
repo*, which is what the gtklock wallpaper was. A background image as such was never the
objection — `--image` is stock swaylock, and the lock screen carried palette-matched wallpapers
from `~/Pictures` for a while, went back to the solid colour, and since 2026-10-08 shows the
palette's one hand-picked image again (§9.25). Configuration lives in
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
| `sway` `mako` `fuzzel` `kanshi` `waybar` | **Yes** | Nothing writes into these directories. New files appear for free. |
| `kitty` | **Yes** | kitty's state is in `~/.local/state/kitty` and `~/.cache/kitty`, not the config dir, so nothing writes into `~/.config/kitty`. **The one thing that would break this is `kitten themes`**, which writes `current-theme.conf` into `~/.config/kitty` *and* appends an include to `kitty.conf` — folded, that lands in the repo, and it is the wrong mechanism here anyway: colours come from `palettes.toml`. Do not run it, for the same reason `nwg-look` is a hazard for `gtk` (§9.1). |
| `tmux` | **Yes** | tmux itself never writes to `~/.config/tmux` — its state is sockets under `$TMUX_TMPDIR`. The package is at the XDG path rather than `~/.tmux.conf` (tmux has read it since 3.1) precisely so that folding is available: the rendered `colors.gen.conf` and `scripts/git-branch.sh` then appear with no `stow -R`, and neither has to sit loose in `$HOME`. **The one thing that would break this is a plugin manager**: tpm installs into `~/.config/tmux/plugins`, which folded means untracked plugin clones inside the repo. None is used today; adding one means unfolding first. |
| `nvim` | **Yes** | Neovim keeps its state in `~/.local/share/nvim`, `~/.local/state/nvim` and `~/.cache/nvim`, and `vim.pack` puts plugin *code* in `~/.local/share/nvim/site/pack/core/opt` — none of it in `~/.config/nvim`, so there is no untracked content to keep out of the repo. Folded, a newly rendered `colorscheme.gen.lua` and any new themed file appear without `stow -R`. **The one thing `vim.pack` does write here is `nvim-pack-lock.json`**, which folding puts straight into the repo — so it is tracked deliberately (§8) rather than ignored, which is what keeps the "no untracked content inside a folded directory" rule satisfied. It is rewritten in place, not by `rename()`, so unlike `htop` (§9.16) folding is a choice here rather than a requirement. |
| `gtk` | **No** | **nwg-look writes into `~/.config/gtk-{3,4}.0`.** See §9.1. Only specific files are tracked; `bookmarks` is left alone as machine-specific. |
| `bin` | **No** | `~/.local/bin` is a real directory holding untracked binaries — `claude`, `coderabbit` (104 MB), `herdr` (22 MB), `uv`. Folding would pull all of it into the repo. A newly added script therefore needs `stow -R bin`. |
| `systemd` | **No** | `systemctl --user enable` writes `*.wants/` symlinks into `~/.config/systemd/user` (`default.target.wants`, `timers.target.wants`): untracked content inside the package directory. A new unit file is therefore absent until `stow -R systemd`, and `systemctl --user daemon-reload` comes after that. |
| `yazi` | **No** | `ya pkg add` installs plugins and flavors into `~/.config/yazi` and writes a `package.toml` lockfile beside them — untracked content inside the package directory, which is the rule below. **No plugin is used today**, and the decision is still made now: unfolding later costs `stow -D && rmdir && stow`, and the trap this section documents is discovering that mid-way through something else. `~/.config/yazi` therefore has to exist *before* the first `stow yazi`, or stow folds it. A file added to the package later is silently absent until `stow -R yazi` — and for this package that includes the rendered `theme.toml`, which is why `tests/check_consumers.sh` asks yazi whether it actually loaded a theme rather than only whether it started. |
| `claude` | **No** | `~/.claude` is Claude Code's own state directory — `sessions/`, `history.jsonl`, `projects/`, `plugins/`, `.credentials.json`, all untracked and some of it secret. Folding would pull the lot into the repo. It also already contains `skills`, a directory symlink to `~/repos/xl-skills/skills`, which folding would swallow. Unfolded, stow links only `statusline.py`; a second file added to the package later needs `stow -R claude`. Note the repo's own `.claude/` at the root is Claude Code *project* state for this repo and is not a package — never name it in a stow command. |
| `herdr` | **No** | `~/.config/herdr` is herdr's runtime directory as much as its config: the live API socket (`herdr.sock`), the client socket, logs, `session.json` (every workspace, pane and Claude conversation to restore), `plugins.json` and the `plugins/` state tree are all written there. Folding would put live sockets and session state in the repo. Unfolded, stow links `config.toml` as a file and `local-plugins/` as a folded subdirectory, which is safe because herdr never writes into it — its own plugin state goes to `plugins/`, which is why the source directory is *not* called that. **herdr rewrites `config.toml` in place** from its settings screen (`std::fs::write`, not `rename()`), so unlike htop (§9.16) the symlink survives and the edit lands in the repo: after touching herdr's settings, `git status`, then commit or revert. `setup.sh` pre-creates the directory. See §9.30. |
| `htop` | **Yes — and it must be** | When htop does save `htoprc` (clean quit, settings changed) it uses `mkstemp` + `rename()`. A `rename()` onto a *file* symlink replaces the symlink with a regular file, so an unfolded `htop` would silently detach from the repo the first time it saved. Folded, the write lands on the repo's own file. See §9.16. |
| `bash` | **Neither — no directory to fold** | Owns two loose files, `~/.bashrc` and `~/.config/dircolors`, and no directory of its own. `$HOME` and `~/.config` always exist, so stow has nothing to fold and always links file by file. Consequence: **a new file added to this package is silently absent until `stow -R bash`**, the same as an unfolded package, and it can never become folded by accident. |
| `starship` | **Neither — no directory to fold** | Owns one loose file, `~/.config/starship.toml`. Same as `bash`: no directory, nothing to fold, `stow -R starship` needed for any file added later. |

**`systemd-system/` is not in this table because it is not stow-managed at all.** It mirrors the
root filesystem (`/etc/systemd/system`, `/etc/udev/rules.d`, `/usr/local/bin`), not `$HOME`, and `.stowrc` pins
`--target=~` for every package in this repo — stowing it would exit 0 while linking to
`~/etc/systemd/system`, satisfying no one (same failure mode as §6.4's `/etc/greetd/config.toml`,
a whole tree instead of one file). `setup.sh` excludes it from the automatic package loop by name.
Everything under it is root-owned once deployed, deliberately: `jellyfin-state-dump.service` runs
as root and both `ExecStart`s and `source`s files, so none of what it executes or reads as
configuration can live anywhere the login user can write — which is why the script itself lives
here rather than in the stow-managed, user-writable `bin` package: a root service trusting a
user-writable script or config is a straight line from "anything running as the login user" to
root.

It holds two things. **`inhibit-sleep-on-ac.service`** plus **`99-inhibit-sleep-on-ac.rules`** keep
the machine awake while it is plugged in — it is a server on AC (tp2's nightly jobs, Jellyfin, the
family site). The udev rule starts and stops the unit on plug/unplug; the unit holds a logind
*block* inhibitor over `sleep:idle:handle-lid-switch`. The lid switch is its own inhibitor class:
the unit once covered only `sleep:idle`, and the box slept 23 hours through a nightly with the unit
`active` throughout (trading-platform-v2 `docs/runbooks/automation-nightly-watchdogs.md`). Until
2026-09-25 these two files lived only in `/etc`, edited by hand, so a reinstall would have lost
them silently. The tracked unit adds `Restart=on-failure` (the hand-made one had `Restart=no`, so
a dead `systemd-inhibit` left the machine sleepable until the next plug event). A deploy that
changes the unit restarts it, which drops the block for a moment, so **don't deploy during a tp2
nightly window**. The other is the **jellyfin-state-dump** timer.

**`systemd-system/deploy.sh` is the one procedure for deploying this tree** — run it, don't
hand-copy the individual files. It installs the sleep inhibitor first, so nothing Jellyfin-related
can fail before it, and verifies the *outcome*: logind must actually hold the `ac-power` block over
the lid switch while on AC, not just report the unit active. For Jellyfin it installs the script
and config *before* the units (so an abort
partway through never leaves the previous, working state half-overwritten), extracts the ntfy
topic from `~/.config/tp-backup/config` by parsing text rather than sourcing it (root must not
execute a file the login user can write, applied to the deploy step itself, not just the runtime
service), and ends by actually running the service once and checking its result — not just
checking file ownership and finding out at 02:00 whether the deploy worked:

```sh
sudo systemd-system/deploy.sh
```

Re-running after a `git pull` is the update procedure — it refreshes the units and the script, and
warns (without overwriting) if `/etc/jellyfin-state-dump.conf` has drifted from the current
`~/.config/tp-backup/config` value or still holds the example placeholder. It never touches that
config's *content* on a fresh install beyond seeding it once: `/etc/jellyfin-state-dump.conf` holds
the **ntfy topic** — an alert credential — so it is never committed, the same reasoning as
`~/.config/tp-backup/config` (§4, `systemd/.config/systemd/user/README.md`).

**`windows/` is not in the table either, for the same reason in a different direction.** It
targets the Windows host of a WSL machine, not `$HOME` on any Linux: `windows/claude-usage/install.py`,
run from inside WSL, copies the tray script to `%LOCALAPPDATA%\ClaudeUsage` and writes its config
there (§9.31). `setup.sh` excludes it from the package loop by name.

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
put a second package's files into `~/.config/waybar`, `~/.config/kitty` and the rest, forcing stow to
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
| Gaps toggle | `$mod+g` | Everyday gaps are zero; this shows the 6/2 frame and the second press returns to none — sway's toggle is `value ? 0 : amount`, so one end is always zero |
| Screenshot | `Print` / `Ctrl+Print` / `Shift+Print` | Region / focused window / display. Shot first at the keypress, then cropped in satty (`scripts/capture.py`) — §9.32. `$mod+Print` starts or stops a recording |
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

Not listed here. A static table is a table that drifts. The bindings live in
`sway/.config/sway/config.d/default` (plus the lid switches in `config.d/input`), commented, and
that file is the source. (`sway/.config/sway/keyboard.conf` is not bindings: it is a reference list
of xkb layouts and variants from stock EndeavourOS, and nothing reads it.)

**Clicking waybar's keyboard icon** (`custom/keyboard-layout`) runs
`waybar/.config/waybar/scripts/keyhint.py`, which lists every binding in fuzzel — key on the left,
command on the right, a mode's bindings labelled with the mode. (Earlier text here said the clock;
it was always the keyboard icon.) It is **built from the config at click time**, the way Omarchy builds its cheat sheet from
`hyprctl binds`, so it cannot drift. sway has no IPC call that lists bindings (`swaymsg -t
get_config` returns only the top-level file, not what it includes), so the script reads the files
sway reads: it follows `include` (with `~`/`$HOME` expanded, globs in sorted order), substitutes
`set $var` values, and understands `bindsym`/`bindcode` blocks with flags and `mode "…" { }`.
`keyhint.py --print` writes the list to stdout.

`tests/keyhint_test.py` (run by `theme_test.sh`) covers each of those shapes, and asserts that the
number of rows equals the number of bind lines in the repo's sway package — so a binding written in
a shape the parser cannot follow fails the suite rather than silently vanishing from the list.
The list replaced `keyhint.sh`, a hardcoded yad grid inherited from stock EndeavourOS: a flat
5-column cell array that read no config, drifted from the real bindings, shifted every later row
when a cell was missed, and clipped overflow without a scrollbar. Retiring it also retired `yad`.

The notification bindings are `$mod+Shift+n` (do-not-disturb toggle), `$mod+Ctrl+n` (restore the
last notification from history) and `$mod+Ctrl+Shift+n` (dismiss all). They are plain `makoctl`
calls with no colour in them, which is why they can live in `config.d/default` despite that file
being parsed before `config.d/theme` (§9.6).

The one worth knowing before you can read any of it: **`$mod+Return`** opens a terminal.

**A binding is for something done often.** Switching palettes is not, so it has none — `theme
<name>` at a shell, or `Style › Theme…` in the command palette, is the interface. The previous binding was `$mod+Shift+t exec theme toggle`,
which stopped working when `toggle` was dropped and failed *silently*, because a sway `exec` sends
stderr nowhere. That is the second cost of a binding for a rare operation: nobody notices it
rotted.

**The command palette is `$mod+space`** (`sway/.config/sway/scripts/menu.py`, actions in
`sway/.config/sway/menu.toml`; design in `docs/specs/2026-10-08-command-palette-design.md`). One
fuzzel window lists every app *and* every desktop action (`System › Reboot`, `Capture › Region →
clipboard`, `Style › Theme…`), searched together and ranked by use: Omarchy's Super+Space,
rebuilt on fuzzel. Each action is written as a `.desktop` file into `$XDG_RUNTIME_DIR/fuzzel-menu`
and fuzzel's ordinary launcher runs over it, so launching an app is exactly what `$mod+d` does.
`$mod+Shift+e` and waybar's power button show the System group alone. `focus mode_toggle`, which
`$mod+space` used to be, is now `$mod+Alt+space`.

The palette is where rare operations live. The rule above still holds for *keys*, and its reason,
silent rot, is answered here rather than ignored: a failing action raises a critical notification
carrying its stderr, and `menu.py --check` (run by `tests/menu_test.py` and `check_consumers.sh`)
fails the moment a command an action names stops resolving. Actions run with a fixed `PATH`,
`~/.local/bin` plus the system directories, because the session's own `PATH` has no
`~/.local/bin` (only `.bashrc` adds it). `--check` resolves against that same `PATH`, so a check
run from a terminal judges what a keypress sees.

`$mod+d` stays plain fuzzel on purpose: if the palette is ever broken, the way to open a terminal
and fix it must not depend on it. A `menu.toml` that fails to load still opens plain fuzzel, with a
notification saying why. The palette retires with the Omarchy migration (D1); `menu.toml` is then
the list of personal actions to recreate as Omarchy menu extensions.

---

## 8. Post-install steps that cannot be stowed

`./setup.sh <palette>` already did everything stow-shaped: the §5.2 fold-guard `mkdir`s, the render
(before the stows — §3.3), the `/etc/skel` `~/.bashrc` move, and every package, gated on a
`stow -n` dry run so a conflict stops it before anything is linked. What follows is what it cannot
do.

```sh
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

**Opening nwg-look and clicking Apply rewrites every GTK file this repo tracks** — the two
`settings.ini` files and `.icons/default/index.theme`. If it writes in place, the write flows
harmlessly through the stow symlink into the repo and shows up as a git diff. If it unlinks and
recreates, **the stow symlinks are silently destroyed** and the repo quietly stops being the source
of truth. It also writes files this repo no longer carries — `~/.gtkrc-2.0`, `xsettingsd.conf`, and
with `export-gtk4-symlinks` a `~/.config/gtk-4.0/gtk.css` symlink into `/usr/share/themes/` that
libadwaita apps would then load. Delete what it created.

nwg-look is not needed at runtime, and since the move to a static Adwaita look (§2.2) it has
nothing left to do: `settings.ini` is the source of truth and `scripts/import-gsettings` pushes it
to gsettings on every reload. **After ever opening nwg-look:**

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

**No daemon-starting `exec_always` line here lacks the `pkill` prefix any more.** There used to be
two exemptions. `exec_always nwg-drawer -r …` relied on resident mode staying at one process across
reloads — observed (`pgrep -xc nwg-drawer` → `1` after 15 hours), never guaranteed — and went with
nwg-drawer on 2026-09-28. `exec_always --no-startup-id foot --server` was safe for a stronger
reason: it *cannot* double-start, the second instance failing to bind
`$XDG_RUNTIME_DIR/foot-wayland-1.sock` and exiting on the spot; it went with the switch to
`$term kitty`. Kept here because the reasoning is the reusable part — **"this daemon cannot
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
- **`JetBrains Mono` ≠ `JetBrainsMono Nerd Font`.** The unpatched family has no icon glyphs. waybar
  is full of Nerd Font icons; without the patched font they render
  via a fontconfig fallback to `Symbols Nerd Font`. That *works*, which is exactly why it went
  unnoticed — but it is a fallback, not a configuration.

### 9.5 Stow exits 0 having done the wrong thing

Covered in §5.1. Always verify with `readlink -f`, never with `$?`.

### 9.6 config.d ordering

Files are read alphabetically. `theme` sorts last and wins conflicts against `default`. Adding a
file called `zz-local` is a clean way to override anything without editing the tracked files.

### 9.7 The dead waybar keyboard-layout signal

`custom/keyboard-layout` in the waybar config declares `"signal": 1`, meaning it refreshes on
`SIGRTMIN+1`. **Nothing ever sends that signal** — the only `pkill -RTMIN+1 -x waybar` in the repo is
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
  Reloading will *not* put it back — and the same holds the other way: after **editing** the
  config's gaps, a reload leaves every existing workspace at the old values, so the first `$mod+g`
  there toggles from the wrong end. Reset explicitly, to the config's values:
  ```sh
  swaymsg gaps inner all set 0 && swaymsg gaps outer all set 0
  ```
  This makes live experimentation safe *and* confusing — you can end up convinced the config file
  is being ignored.
- **`smart_borders on` hides borders when a workspace holds one window** — which is precisely when
  a maximised window and the bar most need distinguishing. Set to `off`.

For a single window on a workspace, the visible margin is `outer + inner` (with `outer 4 inner 8`,
measured 12 px on all sides). Everyday gaps are now `0 / 0`, so there is no margin at all and the
border is the only edge between a lone window and the bar, both `bg`; `$mod+g` toggles `outer 2
inner 6` on, which gives 8, and 6 between tiles.

### 9.9 GTK apps need restarting after a theme change

GTK3 apps read `settings.ini` at startup. A long-running app keeps its old theme indefinitely — a
Thunar started before the retheme was still rendering light a day later, while a freshly launched
GTK3 app picked up the new theme correctly. Diagnose by launching a *different* GTK3 app that was not
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

GTK CSS is waybar's stylesheet now — the desktop's own `gtk.css` overrides went with the move
to plain Adwaita (§2.2) — so waybar is where this bites, and `tests/check_consumers.sh` asserts that
every `@name` in waybar's `style.css` is defined by `colors.gen.css`.

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

### 9.11 A terminal is recoloured by reload, never by restart

**kitty's `SIGUSR1` is a genuine config-reload**: every running instance re-reads `kitty.conf` and
its `include`, so a palette switch recolours open windows in place, without closing them and without
touching what is running inside. `theme` sends it at the end of every switch, and this is the only
signal it sends to a terminal. **Nothing in this repo restarts a terminal, ever** — the processes
inside one are the user's, not the theme switcher's: an editor with unsaved work, a long build, a
Claude Code session.

That rule is why **foot was retired** (2026-09-28). It was the SwayCE default, then kept as a
themed standalone fallback after kitty took over, and it has **no config-reload signal**: `SIGUSR1`
and `SIGUSR2` only toggle between the `[colors-dark]` and `[colors-light]` blocks loaded at startup.
An open foot kept its old palette until closed, and the only way to force it was the restart this
rule forbids. It also cannot render ligatures, and never will — upstream closed that as needing "a
large rewrite of the rendering logic". A fallback terminal that could only ever be half-themed cost
a package, a template and this section; `kitty` alone is carried now. (The rejected
alternatives — the dark/light-slot trick, a `--restart-terminals` flag this document once described
but which never existed, the tmux-survives caveat — are archived in
`docs/archive/2026-08-17-stock-deviations.md`.)

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

This is why the old screenshot bindings called a script instead of inlining `slurp -c $accent`,
and why `scripts/capture.py` (which replaced them, §9.32) reads `~/.config/sway/theme.gen.env` at
*runtime* for its recording box: that sidesteps parse order completely. Any future binding that needs a colour should do the same rather than move files
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

No error, no warning, not even in `ya env`. It is strict about everything else: `ya env` exits 1
on a bad colour value, malformed TOML or an unknown `[section]` (re-measured on 26.9.1), which makes
it a better validator than most consumers here. Before 26.9 the same report was `yazi --debug
</dev/null`; 26.9 removed that flag, and because yazi now touches the terminal before it parses its
arguments, the old check *hung* in a real terminal (stopped by the kernel under `timeout`) rather
than failing. `check_consumers.sh` now runs `ya env` inside a `script` pseudo-terminal, so it behaves
the same from a terminal, a herdr pane or an agent's shell. But a *key* misspelt
inside a known section is dropped without a word, and the schema does move (`[manager]` was
renamed `[mgr]`). So the keys in `theme.toml.tmpl` are copied from the preset embedded in the
installed binary, not from documentation — re-derive them the same way after an upgrade. The
binary holds two copies, dark then light, each opening with the same `#:schema` line; the dark one
is the text between the first two:

```sh
python3 -c "import sys; b=open('/usr/bin/yazi','rb').read(); m=b'#:schema https://yazi-rs.github.io/schemas/theme.json'; i=b.index(m); sys.stdout.write(b[i:b.index(m,i+1)].decode())"
```

Not `strings /usr/bin/yazi` and read forward: that finds the preset but breaks the multi-byte icon
glyphs across lines, so the `[icon]` tables come out mangled (found re-deriving for 26.9.1, when
`[help]` had silently renamed `on`/`run`/`desc` to `chord`/`action`).

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
widget stale), `FETCH_TIMEOUT=5` (a stale bar beats a frozen one). **A failed fetch backs off,
and a 429 obeys `Retry-After`.** On 2026-10-08 the endpoint answered 429 with `Retry-After: 751`.
The old rule allowed a new attempt 30s after any failure, and the Windows tray (§9.31) ticks
every 60s, so every tick retried. That was one 429 a minute, and the tray showed "stale — HTTP 429"
for over 50 minutes: retrying inside the window is what kept it rate-limited. Now each failure
sets `limits_retry_at` and counts `limits_failures`, and nothing fetches before `limits_retry_at`.
A 429 waits the larger of `Retry-After` (capped at `RETRY_AFTER_MAX=3600`) and `API_TTL`
doubling up to `BACKOFF_CAP=1800`. Any other failure (network, 5xx, bad JSON) waits 30s doubling
up to `API_TTL`. Success resets both fields. "Refresh now" still retries a network error after its
debounce, but it cannot cut a 429's wait short. The stale banner, in waybar and the tray, ends in
`, retry HH:MM` while a wait is pending (`snapshot()`'s additive `retry_at`; no schema bump).
`BackoffTest` pins this down. `custom/claude`'s
`exec-on-event: false` in waybar's config exists for the same reason — the default `true` re-execs
the script on every click, racing the `--refresh` already in flight — and inside the script,
`fcntl.flock` on `~/.cache/claude-usage/lock` makes the interval run, a clicked `--refresh`, and
the signal-8 re-exec a single writer regardless of which one wins the race. If `theme.gen.env` is
missing or a role fails to parse, `FALLBACK_THEME` uses **Pango named colours only** (`black`,
`gray`, `yellow`, …) — `check_hex.py` scans this file too, and a hex literal here would fail it
the same as anywhere else. All *derived* widget state — fetched limits, JSONL scan offsets, debounce
timestamps — lives in `~/.cache/claude-usage/`; deleting it forces a full rebuild on the next run
(fresh JSONL scan, fresh fetch, TTL ignored). The one thing that is the user's rather than
derived, the reset floor below, deliberately does not.

**An out-of-cycle limits reset has a user-set floor, kept outside the cache.** When Anthropic
resets the limits early (2026-09-26 was one), the percentages drop to 0 through the API but
`resets_at` stays where it was, so the pace marker still starts its window seven days before that
end — 4d 7h left read as 39% along at 0% used — when the budget now only has to last from the
reset. `claude_usage.py --limits-reset` (a hand-run mode; add `; pkill -RTMIN+8 -x waybar` to
repaint at once, `-x` per §9.29) writes the current time to
`$XDG_STATE_HOME/claude-usage/limits-reset-at` (default `~/.local/state/`), and each pace marker's
window then starts at `max(resets_at - window, floor)` — its end is still the payload's. Delete the
file to undo it. The decisions worth keeping:

- **The token charts ignore it, on purpose.** They are a record of what was spent, not a budget,
  and usage from before an early reset is still usage. The first version also restarted the charts
  from the floor; that was a misreading of what "reset" was for and was reverted the same day
  (#37 → the PR after it). The scan and the chart rendering are byte-identical to before the
  feature, and `ResetFloorKeepsHistoryTest` plus a `MainTest` end-to-end case pin that down.
  A cache built under #37 keeps its floor-cut `days` *and* its advanced scan offsets, so it never
  recovers the lost history on its own; there is deliberately no migration for it, since the only
  such cache was this machine's and it was rebuilt on the spot. If one ever turns up, the fix is
  the ordinary one — delete `~/.cache/claude-usage/state.json` and the next tick rescans.
- **Outside the cache**, because the paragraph above promises the cache is safe to delete, and a
  floor kept in it would put the markers back on the plain window the moment somebody did. `theme`
  keeps its palette in the same state directory for the same reason. main() reads it fresh on
  every run into `st["reset_floor"]`, which render() hands to `pace_mark`; the copy in state.json
  is never read back.
- **It retires itself.** It only moves a window's start *later*, and only while it falls inside
  that window: once the window rolls over, its plain start passes the floor and the marker is back
  on seven days (or five hours) with nobody deleting anything. A floor at or past `resets_at`
  would make a window of no length, so it is ignored. Session windows take the same rule on their
  own scale.
- **It is manual, not detected.** An early reset is visible only as a percentage falling while
  `resets_at` stands still; detecting that means watching the payload and remembering what it
  was — the persistent state `LIMIT_WINDOWS` declines to keep — for an event that happens rarely.
  One command at the moment you notice is cheaper than a heuristic that can misfire on every tick.

A garbled floor file fails open — the markers go back to their plain windows and stderr says why —
rather than blanking the widget. `tests/claude_usage_test.py` covers it (`ResetFloorTest`,
`PaceFloorTest`, `ResetFloorKeepsHistoryTest`, the reset cases in `MainTest`). Every `MainTest`
environment pins `XDG_STATE_HOME`, or a real floor file on the machine running the suite would leak
into it.

**`--json` is the second face, for the Windows tray (§9.31).** Same lock, same refresh, same scan,
same `state.json` — a `--json` run is a full tick — but `snapshot()` goes to stdout instead of
waybar's Pango. `snapshot()` carries every decision `render()` makes as data (rounded percent and
its `level_of()` level, labels, the pace window from `pace_window()` with the floor applied, the
seven local days, model names and order, humanized counts) and leaves only clock- and pixel-bound
work to the consumer. `level_of()` is now the one home of the 70/90 thresholds for the waybar class,
the tooltip fill and the tray alike. Model names come from the id alone: the prefix table that used
to sit in front of `model_display()` named `claude-sonnet-5-5` "Sonnet 5", so the chart drew two
rows with one name.

**One wall-clock read, and `main(now=…)` is the seam.** Every function in the widget already takes
`now` as an argument — `render(st, theme, now)`, `scan_jsonl(…, now_epoch)`, `refresh_limits(…,
now_epoch)`. `main` was the only one calling `datetime.now()`, and it now takes an optional `now`
so the end-to-end tests can freeze it to the same instant the other 80 tests use. That is not
tidiness. With a real clock, the end-to-end fixture (stamped 2026-08-22) aged past `WINDOW_DAYS =
8`, `scan_jsonl` pruned it on arrival, and `tests/claude_usage_test.py` — and `theme_test.sh`,
which runs it — went red from roughly 2026-08-30 **on the calendar rather than on a defect**, and
stayed red until 09-19, camouflaging anything real that might have joined it. A test with a dated
fixture either freezes the clock the code reads or it rots; freezing is the option that keeps this
test in step with the other 81 instead of making it the only one whose inputs change per run. The
`now` is still resolved *inside* the flock, not at function entry, so a run that queued on the
lock stamps itself when it got the lock. Proven both directions: booby-trap `datetime.now()` to
raise and the end-to-end test still passes (the clock really is out of the path), and break day
bucketing and it still goes red (the assertion still bites).

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

### 9.25 The lock screen: the palette's wallpaper, guarded, and never the network

**Since 2026-10-08 each palette has a wallpaper slot**, `~/Pictures/wallpapers/<palette>`: a
symlink the user points at an image *in the same folder*
(`ln -sfn ~/Pictures/wallpapers/<file> ~/Pictures/wallpapers/gruvbox`; a bare or this-folder
absolute target both pass the lock's guard). Keep the images on local disk for the desktop's sake
too: sway calls `access()` on the slot in the compositor while parsing the config, so a slot into a
dead network mount could stall sway itself at reload or login. The desktop
shows it (`output * bg $wallpaper fill $desktop` in `config.d/theme`, `$wallpaper` rendered into
`colors.gen.conf`), and so does the lock screen, which is Omarchy's idea too: the lock screen is the
desktop's own background, not a separate collection. A missing slot is not an error anywhere — the
desktop falls back to `$desktop` (measured: `sway --validate` passes, swaybg runs colour-only) and
so does the lock. The images live outside the repo (no binaries), so a fresh clone shows the colour
until the slots exist.

**The lock only uses the slot behind a guard**, because the lock is the one consumer that must
never stall. `lock.sh` passes `--image <slot> --scaling fill` only when every check holds, each
local and non-blocking; any miss is exactly the colour lock:

| Check | Why |
|---|---|
| `PALETTE` (from `theme.gen.env`) is `^[a-z0-9_-]+$`, and the slot path has no `:` | no `../`; swaylock reads `--image` as `[[<output>]:]<path>`, so a colon would be taken as an output name |
| the slot is a symlink whose target is a bare name, or this folder's own absolute path to one (no other `/`, not `.`/`..`) | the image is a sibling in this folder, so never a link into another tree such as an rclone/FUSE mount whose `stat` could hang — which holds while `~/Pictures/wallpapers` is itself local (rclone is in use on this machine; never mount there) |
| that sibling is not itself a link, and is a readable regular file | the bare-name rule cannot be stepped around with a second link |
| it is under 8 MB | swaylock decodes the image *before* the lock surface exists (`load_image()` runs during argument parsing, v1.8.6 `main.c`), so a big image delays the lock that runs before suspend. A 22 MB PNG is refused by design |

Behind that, a second fallback that does not depend on the first: an image swaylock cannot decode
is dropped by `load_image()` and the lock proceeds over `--color` (verified in the v1.8.6 source).
The 8 MB cap is a heuristic for decode time, not a measurement. If a lock ever feels slow, time a
decode of the slot and tighten the cap (`gdk-pixbuf-thumbnailer` is not installed here):

```sh
python3 -c 'import gi,time; gi.require_version("GdkPixbuf","2.0"); from gi.repository import GdkPixbuf
t=time.time(); GdkPixbuf.Pixbuf.new_from_file("/home/xinye/Pictures/wallpapers/gruvbox"); print(time.time()-t)'
```

Measured 2026-10-08: a 3992x2242 JPEG decodes in 0.11 s, a 6000x4000 one in 0.18 s, and the 22 MB
5120x2880 PNG the cap refuses in 0.30 s. Pixel count, not bytes, is what a pathological image would
abuse (a tiny 16k x 16k PNG passes the cap); acceptable for two hand-picked images.
`tests/lock_test.sh` holds every case against a stub swaylock and was checked by mutation: each
guard removed in turn turns it red, except `-L slot` and `.`/`..`, which a neighbouring check
(`readlink` empty, `-f`) already covers.

**From 2026-09-28 to 2026-10-08 it locked over the solid `$desktop` colour. Until 2026-09-28 it picked a
random palette-matched image from `~/Pictures/walls/<palette>/`**, a ~320 MB cache that
`bin/.local/bin/walls-sync` (547 lines) mirrored from [dharmx/walls](https://github.com/dharmx/walls),
with a resolution floor, a header parser and a fail-safe chain of its own. All of that retired for
one lock-screen picture. `~/Pictures/walls` is safe to delete: nothing reads it any more.

**The rule that survives is the one the wallpaper work was built around: *the lock screen must
never touch the network.*** It is asked for when the idle timer fires, before suspend, and at
`$mod+f1` — on a train, on dead wifi, halfway through a resume — and a lock that waits on a socket
is a lock that does not happen. The image that came back obeys it: it must be on disk before the
lock is asked for, and every way of not finding it ends in the solid colour with the screen locked.

**The colour fail-safe stays bare, deliberately.** When a role fails to parse — no `theme.gen.env`
on a fresh clone, or a half-written one — `lock.sh` does `exec swaylock "$@"` with *no flags at
all*. That path runs when the machine's own configuration is broken, so it must be the dumbest,
most obviously-valid invocation available: every flag it does not carry is a flag that cannot be
the reason it failed. Measured on swaylock 1.8.6, a malformed `--color` is swallowed and it locks
anyway; the guard does not rest on that leniency.

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
`.info`, `.warning`, `.question`, `.error` — and the Nordic theme, nord's GTK theme until
2026-09-28, styles that set *unscoped*:

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
the GTK theme the tracked `gtk-3.0/settings.ini` names, and fails on any class that changes the
painted background. While each palette had its own GTK theme it rendered under **both**, and
testing the theme that was *not* switched on was the entire point: this bug was green under gruvbox
for as long as gruvbox was on. Since 2026-09-28 both palettes share plain Adwaita (§2.2), which
scopes the infobar classes — measured: with the declared paint deleted from `style.css`, the check
still passes under Adwaita, and with an unscoped `.warning` fill added back it fails on 15 modules.
The rule stays; Adwaita's politeness today is not a promise about the next GTK release. It tests the whole stock set rather than the classes
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

**Re-measured for Adwaita** (2026-09-28, §2.2), whose GTK3 dark tooltip is `rgba(0, 0, 0, 0.8)` —
read from libgtk's own `gtk-contained-dark.css`, not assumed. Both palettes still clear the floor,
gruvbox with the least room anywhere in the table:

| | over the palette's `bg` | over a white window |
|---|---|---|
| nord `#a0a8b6` on Adwaita's tooltip | 8.27:1 | **5.28:1** |
| gruvbox `#a89984` on Adwaita's tooltip | 7.20:1 | **4.55:1** |

`muted` fares worse, as it is allowed to: 1.71:1 (nord) and 2.60:1 (gruvbox) over white.

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

### 9.29 waybar is supervised by a script, and an orphaned bar looks identical to a live one

waybar is not started by a `bar { swaybar_command waybar }` block. `config.d/theme` has no `bar {}`
block at all — that is what stops sway running its own bundled `swaybar` — and
`config.d/autostart_applications` starts **`scripts/waybar_run.sh`** with the same
`sh -c 'pkill -x …; pkill -x …; exec …'` shape every `exec_always` daemon here needs (§9.2).

**Why not the bar block.** waybar aborts intermittently — `coredumpctl` showed five SIGABRTs across
2026-09-01..13, none correlated with output hotplug, suspend/resume or lock, so it reads as an
internal waybar race and not as anything this repo feeds it. Sway does not respawn a bar command
that exits on its own, so every crash left the desktop with no bar until someone pressed
`$mod+Shift+c`. Patching that from inside the bar block turned out to be a dead end: with the bar
already dead, `swaymsg reload` reliably re-ran every *other* `exec_always` (idle.sh and kanshi both
got fresh PIDs) and never relaunched the bar's process — tried with a plain `waybar`, an inline
`sh -c` loop, and the script, all three zero after 5s of polling. `swaymsg exec waybar` started it
instantly every time. So the bar became a daemon like the others, and the block went away.

**The failure that mattered is not the crash — it is the supervisor dying quietly.** On 2026-09-15
the bar vanished at 08:07:54 and was still gone 13 hours later. The supervisor had been in place
for two days and had demonstrably worked (it restarted a bar that was deliberately `kill -ABRT`ed
on 09-13). What the coredump of the bar that finally died actually recorded was:

```
PID: 1311355 (waybar)   Signal: 6 (ABRT) si_code: SI_TKILL   PPid: 1
```

`PPid: 1`. That waybar was an **orphan** — its supervisor had died days earlier, the bar kept
running reparented to init, and so the one thing the supervisor existed to do was already gone
before the crash it was supposed to cover. Note also `Command Line: waybar`, with no `-b bar-0`:
the pre-2026-09-13 cores all read `waybar -b bar-0`, which is how a bar started by sway's bar block
is spelled, so the cmdline alone dates a core either side of this change.

**Nothing could see it, and that is the real defect.** An unsupervised bar is pixel-identical to a
supervised one. The desktop looked perfect for two days. `check_consumers.sh` asked waybar whether
it accepted its config and got a happy yes. The only evidence anywhere on the machine was a field
in coredump metadata, which is not somewhere anyone looks until after the outage.

**The signature is reproducible in one line: `kill -HUP` the supervisor.** The first version
trapped `TERM INT` only, so a HUP killed the shell outright and the `waybar &` it had started
survived with `PPid: 1` — the exact state above. A trap is a necessary fix and not a sufficient
one: SIGKILL runs no handler at all, so no amount of trapping can guarantee the child goes with
the parent.

**`setpriv --pdeathsig TERM waybar` is what actually closes it**, and it is load-bearing rather
than tidy. `PR_SET_PDEATHSIG` is the kernel's own bookkeeping: it fires when the parent dies
*however* it died, SIGKILL included. Verified by SIGKILLing a supervisor and watching the child go
with it. `setpriv` execs waybar in place, so `comm` stays `waybar` and the `pkill -x waybar` in
`autostart_applications` still matches it; util-linux is not an added dependency. The invariant it
buys is one-directional, and it is the direction that matters: **no waybar outlives its
supervisor.** Do not read the converse into it — during a backoff the supervisor is deliberately
alive with no bar on screen, which is exactly when the run log is the thing to look at.

`setpriv` comes from `util-linux`, which pacman reports as `Required By: base`, so it is not a new
dependency and does not belong in `packages.txt` (§4 lists explicit installs, not what `base`
drags in). The script still resolves it with `command -v`, once at startup rather than per
restart, and if it is ever missing it says so through `notify-send` as well as the log and starts
waybar anyway: a bar with degraded recovery is the pre-2026-09-15 status quo and beats no bar,
and the supervision check below catches the orphan if one then appears. What it must not do is
take that path in silence — that would hand back the exact bug this section is about.

Four smaller holes went with it:

- `pid` is initialised before the loop. Under `set -u` an unset `$pid` makes the cleanup trap abort
  on an unbound variable at exactly the moment cleanup is wanted — a signal arriving before the
  first assignment.
- The kill hangs off an `EXIT` trap, so *every* exit path — signal, error, falling out of the loop
  — runs the same cleanup, instead of only the two signals someone thought of.
- A bar that cannot start at all (broken config, missing module binary) exits instantly, and a flat
  `sleep 1` retried it ten times in ten seconds, forever, with nothing on screen and nothing said.
  It now backs off 1, 2, 4, 8, 16, 30s and raises one `notify-send` after five fast exits in a row
  — a notification being the only channel left when the bar itself is the thing that is missing.
- Restarts are appended to `${XDG_STATE_HOME:-~/.local/state}/waybar/run.log` (trimmed at 500
  lines). waybar's stderr goes to sway's tty, which nothing records, which is why diagnosing this
  needed coredump archaeology in the first place.

**Detection, because prevention is not provable.** `check_consumers.sh` now asserts the invariant
against the live session: exactly one `waybar_run.sh`, and every running `waybar` a child of it. It
is placed ahead of that file's existing waybar check, which starts a second bar of its own for a
second. The repair for any failure it reports is `swaymsg reload` — the `pkill -x waybar` on the
`exec_always` line reaps a foreign or orphaned bar before the new supervisor starts its own.

**`pkill -x` matches by name across the whole session — a "sandbox" test cannot use these names.**
`pkill -x waybar_run.sh` from a test running out of `/tmp` kills the real supervisor, and
`pkill -x waybar` kills the real bar. This is not hypothetical: it is how the live bar was taken
down *during this investigation*, by a throwaway script that copied `waybar_run.sh` under its own
name and cleaned up after itself with `pkill`. `tests/waybar_run_test.sh` therefore kills only PIDs
it captured itself, and says so at the top.

**The suite.** `sh tests/waybar_run_test.sh` — sandboxed, a fake `waybar` on `PATH` and a throwaway
`$HOME`, never touches the live desktop. Six checks: crash restarts; TERM, HUP and KILL each take
the bar down with the supervisor; an instantly-exiting bar is backed off rather than respawned at
1Hz; restarts reach the log. Point `WBR_BIN` at another copy to confirm the assertions can still
fail — a green suite that cannot go red is the `gate-fixtures` trap (§9.25's sibling rule, applied
in `tp_backup_test.sh`). This one was built by proving **4 of its 6 checks fail** against the
pre-fix script, two of them with the literal `PPid: 1` signature from the outage.

By hand, in the live session:

```sh
pgrep -xc waybar_run.sh                      # exactly 1, and still 1 after a second reload
pgrep -x waybar | while read -r p; do        # every bar's parent is the supervisor, never 1
    printf '%s ppid=%s\n' "$p" "$(awk '/^PPid:/{print $2}' /proc/$p/status)"
done
tail "${XDG_STATE_HOME:-$HOME/.local/state}/waybar/run.log"
```

### 9.30 herdr: the agent multiplexer, its alerts, and what tmux is still for

[herdr](https://herdr.dev) runs every Claude Code session on this machine: workspaces → tabs →
panes, with each pane's agent classified `idle` / `working` / `blocked` / `done`. The research
behind this setup, with sources and a fact-check, is
`docs/specs/2026-09-23-herdr-agent-setup-research.md`. What lives here:

| Piece | File | Job |
|---|---|---|
| config | `herdr/.config/herdr/config.toml` | theme, keys, sidebar rows, toast delivery |
| attention plugin | `herdr/.config/herdr/local-plugins/attention/` | critical notification while an agent is blocked, withdrawn when it moves on; pokes waybar |
| waybar module | `waybar/.config/waybar/scripts/herdr_blocked.py` (`custom/herdr`) | dim count working, else amber count *done* (finished unseen — an answer is waiting), else red count *blocked* when any are; hidden only when herdr is not running; click goes to the first blocked, else the first done |
| session backup | `bin/.local/bin/herdr-session-backup` + `systemd/…/herdr-session-backup.{service,timer}` | hourly copy of `session.json` when it changed |
| tmux guard | `tmux/.config/tmux/tmux.conf` (`set-environment -gu HERDR_*`) | stop a tmux server inheriting one herdr pane's identity |

**The web documents a newer herdr than the one installed.** herdr.dev's docs default to the latest
release; the authority for what *this* binary accepts is `herdr --default-config`. An unknown key is
ignored with a one-line diagnostic, not an error — so a key copied from the website can do nothing
in silence. The one exception runs the other way: a typo inside a *styled* sidebar token
(`{ token = …, fg = … }`) is `deny_unknown_fields` and fails the whole parse. `check_consumers.sh`
asks herdr itself: it starts a throwaway server and reads the JSON from `server reload-config`,
which lists every ignored key.

**herdr writes its own config.** Its settings screen (theme, sound, toast delivery, border labels,
panel sort) rewrites `config.toml` in place, so through the stow symlink those edits appear in
`git status`. Commit what you meant, revert what you didn't — the same drill as nwg-look (§9.1),
minus the clobbering.

**Colour: `name = "terminal"`, plus three overrides.** The terminal theme draws with the host
terminal's ANSI colours, which kitty renders from `palettes.toml`, so a `theme` switch recolours
herdr with no template and no hex in this file. The two alternatives both break a convention:
`[theme.custom]` rendered from roles would put `config.toml` on the hardcoded-path render list
(§2.3) *and* lose herdr's own in-place edits at the next render; switching `name = "nord"/"gruvbox"`
would make every palette switch a repo change. Measured before choosing (§9.28): the terminal
theme's `surface1` is ANSI 8, and herdr draws text on it (copy-mode search matches, release-note
code blocks) — fg on gruvbox's ANSI 8 is 2.68:1. `surface1 = "black"` (ANSI 0, a *named* colour, so
no hex) is the only one of the sixteen that clears 4.5:1 in both palettes (7.45 / 8.45). Its price
is separators and tree lines at ~1.25:1, which is chrome.

The same measurement was missed for every *highlight*: herdr draws the active tab, menu and dialog
selections and the navigator as `surface_dim` text on an `accent` fill, which the terminal theme
makes ANSI 8 on ANSI 4 — 2.74:1 under nord, 1.15:1 under gruvbox, the active tab name all but
gone. `surface_dim` is also the fill behind the active sidebar row (fg on it: 2.68:1 under
gruvbox), and `accent` is text on bg in the pane-border labels (3.48:1 under gruvbox). So
`surface_dim = "black"` (ANSI 0, as `surface1`), and `accent = "lightcyan"` (ANSI 14: nord's frost
teal, gruvbox's aqua), because no ANSI blue carries ANSI 0 text at 4.5:1 under nord's light
blue (3.74). Result: highlight 4.83 / 5.51:1, sidebar row 7.45 / 8.45:1, accent text 5.99 /
7.01:1. `ThemeTest` in `tests/herdr_test.py` resolves the config over the 0.8.0 terminal theme
against `palettes.toml` and measures all four pairs in both palettes; against the old config it
fails four of them. When herdr is upgraded, re-read `Palette::terminal` and `panel_contrast_fg`
in the new source — the test copies them.

**Agent state comes from the screen, on purpose.** The official Claude integration
(`herdr integration install claude`) reports only *which conversation* a pane holds, for restore.
herdr's authors moved Claude off hook-reported state because hooks "can miss permission approval
results, escape interrupts". Do not add a `pane report-agent` Claude hook to "fix" a misreading —
it would override the screen and can stick (e.g. `working` after an Esc). Screen detection has open
bugs in both directions (herdr #3090, #3414, #3467, #4376, #3993), so nothing here gates on state
alone: the alert withdraws itself, and the waybar count is recomputed from `herdr agent list`
rather than tracked.
The module is always visible while herdr runs — a dim working count (`@dim`: text meant to be
read quietly) — because one that appears only on `blocked` looks exactly like one that is broken.

**Three states, one priority order.** `custom/herdr` picks one number and class per agent status,
blocked outranking done outranking working: any `blocked` agent (a decision is needed, including a
multiple-choice question dialog — Claude Code's are already reported as `blocked`) shows that count
in `@critical`; else any `done` agent shows that count `waiting` in `@warning`; else the plain
`working` count shows `quiet` in `@dim`. `done` means an agent finished its turn *while you weren't
looking at that tab* — it is a lower bound on "there's an answer waiting for you", not an exact one,
because it never appears at all if you were watching when the turn finished (straight to `idle`
instead), and it clears to `idle` — dropping out of the count — the moment you *view* the tab again,
whether or not you actually typed an answer; herdr marks a tab seen as a whole, not per message. The
tooltip lists every non-empty status, including `idle` under "seen, not answered yet", since herdr
gives no way to tell an idle agent that was answered from one that was only glanced at and left.
Click focuses the first blocked agent, else the first done one. Signal 9 from the attention plugin
keeps blocked/working/done transitions instant, but viewing a pane emits no
`pane.agent_status_changed` event — the done → idle move happens client-side with nothing to poke
the bar — so the config's 5 s interval, not the signal, is what clears a stale "waiting".

**The attention plugin.** herdr runs `attention.py` on every `pane.agent_status_changed`, for every
pane, with the event in `HERDR_PLUGIN_EVENT_JSON` (fields under `data`) and cwd = the plugin's
directory. On `blocked` it sends `notify-send --app-name=herdr --urgency=critical`, keyed per pane
so a re-block replaces rather than stacks; on any other status it `makoctl dismiss`es that pane's
notification. It skips the notification only when the pane is herdr's focused pane **and** the
sway-focused window is the terminal hosting a herdr client (a `herdr` process descended from that
window's pid) — focused inside herdr but looking at another window still notifies. Every event
also sends `pkill -RTMIN+9 -x waybar`. It is *linked*, not installed:
`herdr plugin link ~/.config/herdr/local-plugins/attention` (setup.sh does it; idempotent, needs no
running server). `min_herdr_version` is mandatory — link refuses a manifest without it. Because it
replaces herdr's own desktop notifications, `ui.toast.delivery = "herdr"` keeps herdr's toasts
in-app instead of doubling them (and herdr ≤ 0.8.2's `"system"` delivery sent them unlabelled, as
"Notify Send").

**`-x waybar` is load-bearing — and the claude widget shipped without it.** `pkill -RTMIN+8 waybar`
is a *pattern*: it also matches the supervisor, whose comm is `waybar_run.sh` (it is exec'd, not
run via `bash`). bash has no trap for real-time signals and dies of one — measured: exit 170 — and
the bar goes with it through pdeathsig (§9.29), with nothing to restart it until the next
`swaymsg reload`. The claude widget's on-click did exactly this until 2026-09-24. `theme_test.sh`
now asserts every `pkill -RTMIN` in the repo, comments included, names `-x waybar`.

**What tmux is still for.** Interactively, nothing: herdr covers detach/attach, named sessions,
SSH, scripting, and restores layout and Claude conversations after a reboot. Its gaps on 0.8.0 are
a status bar (0.8.2+), tpm plugins, regex scrollback search and paste buffers. But the agents here
run long **background jobs** in detached tmux sessions (`tmux new-session -d -s eodhd-…`), and
that is the right tool: the tmux server double-forks away from the herdr pane, so the job survives
a herdr restart — including the upgrade — where a job in a herdr pane would die. Nobody attaches to
those sessions, so the shared `ctrl+b` prefix never collides; attaching one *inside* a herdr pane
needs `ctrl+b ctrl+b`. Two rules follow:

- **Never run an agent inside tmux inside herdr.** herdr sees `tmux` as the pane process and stops
  detecting the agent.
- **A tmux server started from a herdr pane inherits that pane's identity.** tmux copies its
  starting environment into the *global* environment, so every later session carried
  `HERDR_ENV=1` and `HERDR_PANE_ID=wK:p2` (found live on 2026-09-24): `herdr` then refuses to launch
  there as "nested", and anything herdr-aware inside believes it *is* pane `wK:p2`. herdr #2134
  was closed unfixed. `tmux.conf` unsets the five `HERDR_*` variables at load;
  `check_consumers.sh` starts a server with them set and asserts they are gone. An already-running
  server keeps them until `tmux set-environment -gu <name>` or a restart.

**Session backups.** One failure (herdr #4320, on 0.9.0, fixed only on the preview channel so far)
rewrote `session.json` as a valid session with nothing in it. herdr 0.9.1 keeps copies of sessions
it cannot *load*; nothing keeps one that loads fine and is empty. `herdr-session-backup` (hourly,
`herdr-session-backup.timer`) copies `session.json` to `~/.local/state/herdr-backup/` when it
changed, keeps 48, and **refuses to copy a session with no workspaces** (exit 1, visible in
`systemctl --user status`) so a wipe cannot rotate the good copies out. Restore: from a terminal
*outside* herdr, `herdr server stop` (this ends every pane process), copy the chosen file over
`~/.config/herdr/session.json`, run `herdr`.

**Upgrading herdr.** 0.9.1 only *adds* config keys over 0.8.0, so this config carries over
unchanged. Do it from a terminal outside herdr: `systemctl --user start herdr-session-backup`,
`herdr server stop`, `herdr update`, `herdr`. Not `herdr update --handoff`: live handoff is still
experimental and has lost agents' scrollback (herdr #3864). Resume brings each Claude pane back to
its conversation — except a pane where `/clear` or `/resume` ran, which can come back to the *old*
one (herdr #1653, reproduced with the v7 hook installed here).

**Testing without touching the live herdr.** Every `herdr` command inherits `HERDR_SOCKET_PATH`
from the pane it runs in, so from inside herdr a test reaches the live session unless it overrides
it. A test server needs its own `XDG_CONFIG_HOME`, `XDG_STATE_HOME` and `HERDR_SOCKET_PATH`, with
`HERDR_ENV`/`HERDR_PANE_ID`/`HERDR_TAB_ID`/`HERDR_WORKSPACE_ID` unset; the socket path must be short
(a Unix socket is capped near 108 bytes — put it directly under `/tmp`). Start it as
`env … herdr server &` so `$!` is the server itself, and stop it by that PID. Never `herdr server
stop` or `pkill herdr` from a test, and never `setsid` it: setsid forks, `$!` is then the wrong
process, and the server you thought you stopped keeps running with *your* PATH — which is how a
stubbed test once sent a real notification.

### 9.31 The Windows tray: WSL decides, PowerShell paints

On a Windows machine where every Claude Code session runs in WSL there is no waybar, so
`windows/claude-usage/` gives the claude widget (§9.23) a Windows face: a notification-area icon
showing the worst displayed percent in its level colour, a hover summary (`Session 44% · 3h 13m`,
one line per limit), a click-open panel with the waybar tooltip's three sections drawn as real
bars, and toasts at 70/90/100% and on a reset. Right-click: Refresh now, Limits were reset early…,
Open usage page, Send test notification, Open log, Exit. **The operational cheat sheet — every
command, option, file and registry key — is `windows/claude-usage/README.md`**; this section is the
why.

**The split.** `ClaudeUsageTray.ps1` runs `wsl.exe -d <distro> --exec python3 claude_usage.py
--json` and draws what comes back; every decision stays in Python under `claude_usage_test.py`.
What the tray computes itself is only what depends on *its* clock: the countdowns and the pace
marker's position, from the epoch `resets_at`/`window_start` in the snapshot, so an open panel, or a
snapshot from before WSL went idle, never shows a countdown that has stopped. The panel's "today"
comes from the same `$Now` — never the wall clock — for §9.23's reason: it is what lets the tests
pin a fixture's date. `schema` in the snapshot is checked; an unknown one is an error on the icon
("re-run install.py"), not half a panel.

**Cadence and WSL's lifetime.** A 60 s timer (config `interval`) runs the collector; the API is
still fetched at most every 300 s inside it, so the tick only buys fresher token charts. The timer
**never boots WSL**: it asks `wsl.exe --list --running --quiet` first (under `WSL_UTF8=1`, or the
output is UTF-16), and while the distro is stopped it shows the last snapshot — persisted to
`last.json`, so a fresh logon has numbers before WSL starts — with the icon greyed and an "idle"
line. A tray that started the VM every minute would also stop it from ever idling out. "Refresh
now" may boot it; that is a click, not a timer. `~/.claude` stays read-only (§9.23): the tray
inherits that from the collector, and the token-expired case shows as stale until a Claude Code
session in WSL refreshes the token.

**Install, update, remove** — from inside WSL, in the distro to report on:

```sh
python3 windows/claude-usage/install.py                  # also the update, after a pull
python3 windows/claude-usage/install.py --palette gruvbox
python3 windows/claude-usage/install.py --uninstall
python3 windows/claude-usage/install.py --status | --start | --stop
```

It copies the `.ps1` to `%LOCALAPPDATA%\ClaudeUsage` (a copy, not a `\\wsl.localhost` path: that
would boot WSL at logon just to read the script, and RemoteSigned can refuse UNC scripts), writes
`config.json` beside it (distro, `/usr/bin/python3` — never a venv's — and the absolute path of
`claude_usage.py` *in this checkout*, so Python-side changes need no reinstall), puts `Claude
Usage.lnk` in the Startup folder, and restarts the tray. The restart signals the named event
`Local\ClaudeUsageTray.Exit` so the old tray removes its own icon (a killed one leaves a ghost
until hovered), then kills whatever is left after 5 s. A `Local\ClaudeUsageTray` mutex keeps it to
one per session. `--uninstall` deletes only the files it knows it created, then the directory if
that left it empty.

**Notifications are edge-triggered and remembered.** A limit's band is 0 below 70%, then 70
(`warning`), 90 (`critical`) and 100 (reached) — the first two straight from the snapshot's
`level`, so `level_of()` is still the only home of the thresholds. `Get-Notifications` toasts when
a band rises, including on first sight (so installing at 80% says so once), and toasts "has reset"
when a limit that had reached a band shows a `resets_at` more than ten minutes later than before
— the endpoint jitters it by fractions of a second between fetches, so equality would fire a
reset on every tick. It records the *current* band, falling as well as rising, so an early reset
(percent drops, `resets_at` unchanged) re-arms the bands. A snapshot carrying an API error changes
nothing: last-known numbers are not news. State lives in `notify.json`, so a restart neither repeats
a toast nor forgets one; several crossings in one tick merge into one toast, worst first, because a
second `ShowBalloonTip` replaces the first.

**Two things about toasts from a tray icon took measurement.** Explorer re-sends a balloon as a
toast under a synthetic app id, `Microsoft.Explorer.Notification.{hash}`, and with nothing
registered the toast header prints that id verbatim. A `DisplayName` and `IconUri` under
`HKCU\Software\Classes\AppUserModelId\<id>` name it — Windows caches the name, so it can take a
toast or two to appear. `SetCurrentProcessExplicitAppUserModelID` does **not** help (tried).
The hash covers the executable and the icon's number, so the first `NotifyIcon` of 64-bit
`powershell.exe` always gets `{B0AA627D-AE34-F5C9-9971-19C8E1D372A3}`; the tray names that one at
start, and after every toast names whatever Explorer id was stamped since (`Select-ToastSenders`),
in case another machine hashes differently. `--uninstall` removes only keys whose `DisplayName` is
the tray's. Any other PowerShell script's first tray icon shares that id, and so the name — an
accepted cost.

**Keeping the icon out of the overflow.** Windows 11 parks new tray icons in the overflow and
records each icon's placement under `HKCU\Control Panel\NotifyIconSettings\<id>`; `IsPromoted = 1`
puts it on the taskbar at once. Explorer writes that entry lazily — measured: not when the icon is
added or removed, not on opening taskbar Settings; by the next sign-in — so the tray checks on
every tick until it has decided. It finds its entry by executable plus `InitialTooltip`, which is why
the icon is first registered as plain "Claude usage" and only then given the live hover text. An
absent `IsPromoted` means nobody has chosen, and the tray sets 1; a present one (0 or 1) is a
choice that stands, so hiding it in Settings sticks. Until that first sign-in, dragging the icon out
of the overflow once is the fix.

**Colours come from `palettes.toml` at install time.** `config.json` carries the chosen palette's
top-level roles (the one `theme` last applied, else nord — inside WSL `theme` has usually never
run), so the panel matches the desktop and the repo still carries no hex; `check_hex.py` covers
the `.ps1` like any other file. It does strip full 8-4-4-4-12 GUIDs before matching — the toast
sender id below contains one, and its groups read as bare `RRGGBBAA` — and `theme_test.sh` asserts
that a colour beside a GUID is still caught. A role missing from the config falls back to a .NET *named* colour
— `FallbackTheme`, the same move as `FALLBACK_THEME`'s Pango names. The panel is always the
palette's dark, whatever Windows' light/dark setting; the icon is a solid tile, legible on either
taskbar.

**Launching with no window was the hard part, and two obvious answers are traps.** With the
default terminal on Windows Terminal — and "let Windows decide" *is* Windows Terminal on Windows 11
— a `powershell.exe` started from a shortcut opens a Terminal window that `-WindowStyle Hidden`
cannot hide. So the shortcut targets `conhost.exe powershell.exe -WindowStyle Hidden …`, minimized:
conhost keeps it in the classic console, which the flag can hide, and the worst case is a taskbar
blip at logon. Tried and rejected on a managed machine (2026-10-07):

- `conhost.exe --headless` — exits `0x80070005` (access denied); the child never runs.
- A launcher compiled at install time (`Add-Type -OutputType WindowsApplication`) that starts
  PowerShell with `CreateNoWindow` — **Defender blocked it on first run as "potentially unwanted
  software"**, and on a managed machine that is a security alert, not just a failure. An unsigned
  exe whose job is to start a hidden PowerShell is malware-shaped, whoever wrote it.
- A VBScript `WScript.Shell.Run …, 0` shim — the same shape to an EDR, and VBScript is a
  deprecated optional feature on Windows 11.

Do not reintroduce a hidden-launch trick to save the logon blip.

**Windows-side constraints worth knowing before editing the `.ps1`.** There is no Python on the
host (the `python.exe` on `PATH` is the Store stub), so it is Windows PowerShell **5.1** —
.NET Framework, WinForms, no `pwsh`. `NotifyIcon.Text` throws past **63** characters there
(measured); `Get-HoverText` sheds countdowns, then the status line, then truncates. Windows 11 puts
a new tray icon in the overflow (^) until it is dragged out or enabled under Settings >
Personalization > Taskbar > Other system tray icons. The panel opens beside the cursor inside the
screen's working area, so a taskbar on any edge works — this machine's is on the left. Two 5.1
traps cost a failed run each: **variable names are case-insensitive**, so a local `$ink` *is* the
`[Drawing.Color]$Ink` parameter and assigning a brush to it throws; and **an empty array returned
from a function arrives as `$null`**, and `@($null)` is a one-element array, which is why
`ConvertFrom-Snapshot` filters nulls out of every list. Two more cost the tests a red run:
**the comma binds tighter than `+`**, so `@('Session', 0, $t + 60)` is a four-element array (the
`+` appends), and a test passed by accident on it until it was parenthesised; and **PowerShell
defines a function when execution reaches it**, so a startup statement above a definition fails
at runtime only — the tray's toast naming did exactly that, logged and silent.

**Tests.** `tests/claude_tray_test.py` covers `install.py` (palette choice, roles, config,
PowerShell quoting, the shortcut command, `--status`, the uninstall's key filter, and the
exit-event name, toast name and schema matching the `.ps1`)
and drives `tests/claude_tray_test.ps1` with fixtures written by the **real** `snapshot()`, so a
shape change fails at the boundary rather than on the desktop. The PowerShell half needs
`powershell.exe`, so it runs in WSL and is a reported **skip** on the sway desktop. It paints every
panel variant to an offscreen bitmap and asserts every draw op lies inside the panel; it walks
every notification rule; and it parses the tray with PowerShell's own parser to assert no
top-level statement calls a function defined further down — the startup path is the one part no
other test runs. That check once passed vacuously: `Resolve-Path` on a `\\wsl.localhost` path
returns a provider-qualified string `ParseFile` cannot open, and the parse errors were discarded,
so it scanned an empty script. It now uses `.ProviderPath`, fails on any parse error, and requires
a non-trivial statement count. Mutation-checked (each turns it red): the 63-character limit, the
exact distro match, the pace clamp, `now` for a passed reset, the wall-clock "today", the
snapshot's level from the float, a dropped `window_start`, the reset message on stdout under
`--json`, an ignored floor, no jitter slack, notifying on stale data, overriding a user's icon
choice, a ratcheting band, the merge order, and a call above its definition. To look at the
panel without a desktop session:

```powershell
powershell -File ClaudeUsageTray.ps1 -Snapshot snap.json -RenderPanel panel.png -RenderIcon icon.png [-Idle]
```

**When it misbehaves:** `install.py --status`; right-click > Open log
(`%LOCALAPPDATA%\ClaudeUsage\tray.log`, collector stderr included); run the collector by hand in
WSL — `python3 waybar/.config/waybar/scripts/claude_usage.py --json`; re-run `install.py` to
restart it. The README has the full list.

### 9.32 Capture: shoot first, select on the freeze

`scripts/capture.py` owns every screenshot, OCR, QR and recording
(`docs/specs/2026-10-08-focus-safe-capture-design.md`). It replaced three `screenshot_*.sh` scripts
that ran **slurp first and grim after the selection**. slurp's overlay takes the keyboard (kitty gets
FocusOut, so termtris pauses and hides its board) and covers waybar (layer `top`, so the pointer
leaves the widget and the claude tooltip closes); by the time grim ran, both were gone.

**The rule: grim runs before any picker.** A Print key is a sway binding and moves no focus, so the
shot taken at the keypress still has the tooltip and the bricks. Choosing the region happens
afterwards, in satty, fullscreen on that frozen image: Enter copies and saves to
`~/Pictures/Screenshots/`, Esc discards and exits 0. **With a crop drawn it takes two Enters** —
satty's crop tool consumes the first to apply the crop, the second runs the actions (satty 0.22
has no option to merge them); Esc after only the first discards. `tests/capture_test.py` asserts
the order in every mode; its first test is this bug.

- **Palette rows pass `--after-palette`.** They wait for fuzzel's instance lock (the palette is on
  screen until it lets go, §7) plus 150 ms of repaint, so the palette is not in the shot. A Print key
  is still the way to catch something transient; `Display in 5 s` gives time to re-create it.
- **Recording** (`$mod+Print`, or the palette) runs wf-recorder detached with VAAPI H.264, its pid in
  `$XDG_RUNTIME_DIR/capture/recording.pid`. `custom/recording` shows a red dot on signal 10
  (`pkill -RTMIN+10 -x waybar`; `-x` per §9.29). A pid whose process is gone is removed on the next
  status read, so the dot cannot outlive the recorder. Region recording still uses slurp, so it is
  not focus-safe; *Record display* is.
- **Window mode** shoots the focused window's sway rectangle, which includes its border and title
  bar (`swaymsg` reports the decorated rect), so the image is a few pixels larger than the content.
- **A failing tool is never silent.** satty exiting non-zero, or wf-recorder dying within 0.3 s of
  starting (bad GPU or option), raises a notification quoting the stderr / `recording.log` tail;
  Esc in satty exits 0 and stays quiet. The recorder uses the first `/dev/dri/renderD*`, and the
  palette's record rows test the pidfile with `sh` (no python start per palette open).
- **Never read a child's output through a pipe here.** satty's Enter runs wl-copy, which forks to
  serve the clipboard and keeps satty's stdout/stderr; a pipe read to EOF hung capture.py until
  the next copy. satty's output goes to `$XDG_RUNTIME_DIR/capture/satty.log` (also the place to
  read why a save failed behind an Esc), and `menu.py` takes each action's stderr through a temp
  file for the same reason (`cliphist_pick.sh` ends in wl-copy too).
- **No satty** → the shot is copied to the clipboard whole, with a notification; the key still
  captures, still at the keypress.

Smoke after touching it: hover the claude widget and press Print (the tooltip is in the image);
Ctrl+Print mid-termtris (the bricks are); OCR some terminal text; `$mod+Print` twice.

### 9.33 Crash → Claude: a toast, a report, and Claude under normal permissions

`bin/.local/bin/crash-diagnose` (`docs/specs/2026-10-08-crash-diagnose-design.md`) turns a crash of
one of your own processes into a toast, and a click into a report plus a Claude session. It is
Omarchy's `omarchy-agent-crash` minus the permission bypass: Claude starts under normal permissions.
Nothing in it is sway-specific, so it is meant to survive the Omarchy migration unchanged.

**The flow.** `crash-watch.service` (`crash-diagnose watch`) follows the journal for
`MESSAGE_ID=fc2e22bc6ee647b6b90729ab34a250b1` entries with your uid and raises "Crash: <comm>
(<signal>)" with the action "Diagnose with Claude" (`-t 0`: it stays until dismissed). A click runs
`crash-diagnose diagnose <pid>`, which writes
`~/.local/state/crash-reports/<date>_<exe>_<pid>/report.md` and opens a herdr tab `crash: <comm>` running
`claude "<PROMPT>"`. The palette's `Dev › Diagnose a crash…` does the same from a list of recent
crashes. **Claude never starts without a click or a pick.**

**What the report holds, and never holds.** Summary (executable, signal, pid, package, core file,
time), History (how many crashes of that executable), the crash-time stack, a gdb backtrace, the
journal entry and the journal lines around it. It **never** contains `COREDUMP_ENVIRON` (no field
name, no value) or the core file. Beyond the field allowlist, any environment value whose name looks
like a secret (`TOKEN|SECRET|PASS|KEY|AUTH|CRED|COOKIE`, value of 8+ characters) is redacted
wherever it turns up: a journal line, a command line. A third pass runs over the whole rendered
report, whatever section a string came from: any verbatim `KEY=VALUE` line of the process
environment becomes `KEY=[redacted]`, and secret *shapes* go on sight, env or not (`sk-ant-…`,
`gh[pousr]_…`, `AKIA…`, a JWT, a PEM private key through its END line, or to the end of the report
if the journal window cut it off). `~/.local/state/crash-reports/` is 0700 (chmod'ed if an older
run made it with the umask). **Backtraces show frames, not argument
values**: gdb runs with `set print frame-arguments presence`, because its default prints a `char *`
argument's contents, which no scrub can know; every frame keeps its function name and its arguments
show as `...`. Honest caveats (spec §8):

- The report goes to Claude, which means Anthropic's API. Backtraces, command lines and journal
  lines are included; the process environment is not. A secret passed on a command line that is not
  in the environment would be.
- debuginfod is network access at click time, not at crash time. Offline reports are less useful,
  but still produced.
- Root and system-service crashes are out of scope (uid filter). The chromium segfault in
  `coredumpctl list` is one.
- One toast per executable per 30 min can hide a storm. The count in the replaced toast ("2nd since
  …") is the signal.

**What the probes found, and what each changed** (2026-10-09, read-only):

- `coredumpctl info` is instant (0.01 s) but not symbolised: it prints the stack recorded at crash
  time (`n/a (waybar + 0x3058b)`). gdb (`coredumpctl debug` with `-batch -iex 'set debuginfod
  enabled on'`) gives symbols: 19.0 s cold, 1.6 s warm. Batch gdb does not use debuginfod unless
  told to. The report holds both, capped at 30 s and 90 s.
- gdb can be worse than the crash-time stack. On the probe core a dozen libraries had been upgraded
  since the crash (`warning: Build-id of /usr/lib/libc.so.6 does not match core file`) and the
  crashing thread came out as `?? ()`. The report says so and puts the crash-time stack first.
- The service is not a shell. The user manager has no `~/.local/bin` on PATH (where `claude` and
  `herdr` live), no `DEBUGINFOD_URLS`, and gets `WAYLAND_DISPLAY`/`SWAYSOCK` only when sway runs
  `import-environment`, after a `default.target` service has started. `session_env()` fills the gaps
  at click time.
- `KillMode=process`: a click can open a kitty window with Claude in it, a child of the service. A
  watcher restart must not close a window someone is reading. herdr panes live in herdr's own
  cgroup and are unaffected. The flip side: the watcher's own `journalctl -f` would survive too,
  one more per restart, so the watcher ends it on SIGTERM and the kernel ends it on any other
  death (`prctl(PR_SET_PDEATHSIG)` in its `preexec_fn`).
- journalctl nulls fields over 4 KiB without `--all` (`MESSAGE`, which holds the stack, is one) and
  renders binary fields as lists of byte values. `diagnose` reads with `--all`; the watcher asks
  only for small fields, so it never sees the environment.
- `COREDUMP_PACKAGE_JSON` carries no package name on Arch, so `pacman -Qo <exe>` is the real path.
- `coredumpctl --json=short list` has no `comm`, and the journal can hold one crash twice (same pid,
  same time): `list` dedupes on `(pid, time)` and History counts it once.
- herdr's `tab create` reply is parsed defensively (`.result.root_pane.pane_id` plus four fallback
  shapes); anything else falls back to a kitty window in the report directory.
- Retention goes by directory mtime, not name (names start with the crash time); newest 20 kept.
- `run()` never reads a child's pipes to EOF after a timeout: a descendant in another session can
  hold them (the same trap as §9.32's wl-copy). It kills the group, reaps and closes.

**Toast lifetimes** (final review, 2026-10-09). A `-t 0` toast's `notify-send --wait` never returns
by itself. When `-r` replaces a toast, the watcher terminates the notify-send that raised it (the
toast stays on screen; killing a client never closes a notification), so there is one live client
per executable group; a click already in the old pipe is still diagnosed once, the newest. Each
clicked `diagnose` is reaped by a small thread (no zombie per click), and on exit the watcher waits
5 s in all for live toasts, not 5 s each. **A watcher restart closes its predecessor's toasts**:
`KillMode=process` lets their notify-send outlive it, so a click would write into a dead pipe and
do nothing while the toast looks live. At start (after journalctl is running, so no new toast can
be caught) `watch` reads `makoctl list -j` (mako 1.11: a JSON array of `{id, app_name, actions, …}`)
and runs `makoctl dismiss -n <id>` for each toast with app-name `crash` **and** the `default` click
action; diagnose's own action-less toasts ("…the report is <path>") and every other app's are left
alone. Dismissing ends the old notify-send's `--wait` too.

**The journal section** keeps what led up to the crash: at most the newest 200 lines before the
crash timestamp and the oldest 200 after (`short-iso-precise`, split to the microsecond). A core
kept with `Storage=journal` (corefile `journal`) gets a gdb backtrace like a `present` one.

**Known and accepted** (final review): the `-p` id `readline()` in the watcher blocks until
notify-send prints the id, bounded by the D-Bus call timeout; `entry_for(pid)` takes the newest
entry for that pid, so after pid reuse an old list line diagnoses the newer crash of that pid; if
`herdr tab create` succeeds and `pane run` fails, the empty tab stays open and kitty opens as well.

**Operating it.** `systemctl --user status crash-watch`; the watcher's own log is `journalctl --user
-u crash-watch` (a clicked `diagnose` inherits its stderr). Reports live in
`~/.local/state/crash-reports/`. A palette pick that fails shows two toasts, crash-diagnose's own
plus `menu.py`'s generic one (§7; harmless). `bin` and `systemd` are both unfolded (§5.2): a new
script or unit is absent until `stow -R bin systemd`, then `systemctl --user daemon-reload`.
`tests/check_consumers.sh` fails `crash-watch.service is active` until the unit is enabled.

**The suite.** `python3 tests/crash_test.py` (~45 s; also run by `theme_test.sh`). Every tool is a
stub on a PATH holding only the stub directory; the fixtures are synthetic, with marker values in
`COREDUMP_ENVIRON`, because a recorded real entry carries the real environment.
`CRASH_DIAGNOSE_BIN` points it at a copy for mutation checks; the suite was built by turning 8 of 8
planned mutants (uid filter, coalesce window, environ field, scrub, click twice, kill child only,
no dedupe, prune by name) plus the detached-grandchild one red, and the final review's fixes each
have a mutant it kills (shebang, gdb `presence`, terminate, prune threads, shared join deadline,
stale dismiss and its two filters, journal halves, journal core, reap, the two stderr lines, 0700,
both new scrub passes). One test execs the file by path, as systemd and the palette do: PATH is then
the stub dir plus a dir holding only a `python3` link, never `/usr/bin`. `theme_test.sh` names it
when it fails.

**Manual smoke** (after `stow -R bin systemd`, `daemon-reload`, `enable --now`): `sleep 60 & kill
-SEGV $!` raises "Crash: sleep (SIGSEGV)"; click it for a herdr tab `crash: sleep` with Claude
reading `report.md`; repeat within 30 min and the toast is replaced with "2nd since …"; Super+Space
→ `Dev › Diagnose a crash…` gives the same as a click; `grep -c COREDUMP_ENVIRON
~/.local/state/crash-reports/*/report.md` is 0 for every report.

## 10. Troubleshooting

| Symptom | Likely cause | Check / fix |
|---|---|---|
| Config change had no effect | Package unfolded, new file not linked | `[ -L ~/.config/<pkg> ] && echo folded \|\| echo unfolded` (§5.2 — `ls -la \| grep` silently passes when it shouldn't); `stow -R <pkg>` |
| Config change had no effect | Symlink points outside the repo | `readlink -f ~/.config/<pkg>` |
| Change needs a full logout to apply | Used `exec` instead of `exec_always` | §9.2 |
| Bar vanished and never came back | waybar was orphaned — its supervisor died earlier, so nothing restarted it | `pgrep -xc waybar_run.sh` (must be 1) and every `waybar`'s `PPid` must be that pid, never 1; `swaymsg reload` repairs it; §9.29 |
| Bar flickers on and off forever | waybar cannot start at all; the supervisor is backing off and retrying | `tail "${XDG_STATE_HOME:-$HOME/.local/state}/waybar/run.log"`; §9.29 |
| Screen never locks | swayidle not running, or many are | `pgrep -xc idle.sh` and `pgrep -xc swayidle` — both must be exactly `1` |
| Screen locks immediately / repeatedly | Multiple swayidle instances racing | Same check; the `pkill` prefix is missing |
| Machine suspends when plugged in, or never suspends on battery | `idle.sh` hasn't noticed a power-source change yet (15s poll), or `AC/online` is unreadable | Wait 15s; `cat /sys/class/power_supply/AC/online`; §9.26 |
| A waybar module has a coloured block behind it | Its state class collides with a GTK stock one the theme styles bare | `sh tests/check_consumers.sh` names the module and the class; §9.27 |
| Tooltip text is there but barely visible | `muted` used where `dim` belongs — `muted` is chrome and may disappear | §3.1, §9.28; measure against the GTK tooltip background, not `bg` |
| GTK3 apps render light | `gtk-theme-name` set to `Adwaita-dark`, which is not installed, or prefer-dark lost | §2.2; `gsettings get org.gnome.desktop.interface gtk-theme` → `'Adwaita'`, and `gtk-application-prefer-dark-theme=1` in `settings.ini` |
| *Some* apps still light | libadwaita | §2.2; check `gsettings get org.gnome.desktop.interface color-scheme` → `prefer-dark` |
| GTK theme reverted | nwg-look was opened | §9.1 |
| Boxes instead of icons | Nerd Font missing | `fc-match "JetBrainsMono Nerd Font"` |
| Wrong/blurry scale | Output scale not declared | `swaymsg -t get_outputs` |
| External monitor ignored | kanshi profile doesn't match | `pkill -x kanshi; kanshi` in a terminal and read the error |
| Screen share / file picker misbehaves | Portal backend | `systemctl --user show-environment \| grep XDG_CURRENT`; §6.4 |
| Background reverted to an image | azote | §9.3 |
| Notification icons missing | mako `icon-path` | Must be a directory that exists |
| Border width change ignored | Applies to new windows only | `swaymsg '[title=".*"] border pixel 2'`; §9.8 |
| Gaps stuck at an old value | A runtime `gaps` command overrode the config | `swaymsg gaps inner all set 0; swaymsg gaps outer all set 0`; §9.8 |
| `htoprc` edit reverted | A running htop flushed its in-memory settings on quit | `pkill -9 htop`, then edit; §9.16 |
| htop changes stopped reaching the repo | `rename()` replaced the symlink | `ls -ld ~/.config/htop` must be a symlink; §9.16 |
| htop right-hand CPUs render below the left | All meters piled into `column_meters_0` | §9.16 |
| A window has no border at all | `smart_borders on` with one window | Set `smart_borders off`; §9.8 |
| One GTK app is the wrong theme | It predates the theme change | Restart it; §9.9 |
| `$mod+Return` does nothing | kitty not installed, or its first start is failing | `kitty --version`, then run `kitty` from another terminal and read the error |
| An open **kitty** is still the old palette after a switch | The SIGUSR1 never arrived | `theme` prints `kitty … reloaded (SIGUSR1)` when it sends one; §9.11 |
| One surface still the old palette, everything else switched | A running GTK app (§9.9), or an unfolded package that was stowed before `theme` first ran, so the rendered file was never linked | Restart the app; else `readlink` the file under `~` and `stow -R <pkg>` if it is missing; §3.3 |
| A widget renders **black** | A GTK CSS `@name` used in a hand-written file but produced by no template, or a stale/deleted rendered file | Re-run `theme` (re-rendering repairs artefacts); if the name is not a role, add it to **both** palettes; §9.10 |
| `theme: …tmpl: no such role '…'` | A template names a role `palettes.toml` does not define | Add the role to both palettes, or fix the typo in the template; §9.10 |
| `theme: … define different keys` | The two palettes have drifted | §9.10. This is the guard, not a fault |
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
readlink -f ~/.config/sway ~/.config/waybar ~/.config/gtk-3.0/settings.ini  # all inside the repo

theme                                                     # re-renders; prints "N files rendered … [name]"
cat "${XDG_STATE_HOME:-$HOME/.local/state}/theme/palette" # nord | gruvbox
```

Folding — the property §5.2 depends on, and the one that a stray file in `~/.config` quietly breaks:

```sh
for p in sway waybar kitty mako fuzzel htop; do
    printf '%-12s ' "$p"
    if [ -L ~/.config/$p ]; then echo "folded (symlink)"; else echo "UNFOLDED (real dir)"; fi
done
```

Six lines, every one `folded (symlink)`. Use this form, not `ls -la ~/.config | grep -E ' foo$'` —
see §5.2 for why that one passes silently when things are fine and only speaks up when they break.

Then trigger each themed surface by hand: `$mod+d`, `notify-send test`, the waybar
clock tooltip (and *scroll* on it — §9.14), `$mod+f1`, thunar, a GTK4 app, `$mod+Return`, `Print`,
`nvim`, `ls`.
