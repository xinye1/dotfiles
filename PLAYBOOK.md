# Sway, Nord and Gruvbox: the full playbook

The complete technical reference for this desktop: what it is, how the pieces fit together, and
every way it differs from a stock EndeavourOS Sway install.

It carries **two palettes**, Nord and Gruvbox Dark, and switches between them with one keystroke
(`theme <name>` at a shell). Nord is the default and the original; Gruvbox was
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

**Rendered files are build artefacts.** They match `*.gen.*`, git ignores them, and editing one is
pointless because the next switch overwrites it. Six files are the exception and cannot carry the
marker, because GTK and xsettingsd read them at a hardcoded path:
`gtk-{3,4}.0/gtk.css`, `gtk-{3,4}.0/settings.ini`, `xsettingsd/xsettingsd.conf` and `.gtkrc-2.0`.
Those six are listed individually in `.gitignore`. That list is structural — it can only change if
an application with a hardcoded config filename joins the desktop.

This replaced a scheme where each themed file was kept *twice*, once per palette, with a
theme-neutral symlink pointing at whichever was active. The colours were written 36 times, the 18
pointers had to be enumerated in `.gitignore` because no glob could catch names like `colors.css`
and `.gtkrc-2.0` without also catching tracked files, and a test existed only to catch that list
falling behind. Generation chooses the output name, so a glob can catch it.

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
| `bg` | window bg, waybar bg, terminal bg, gtklock bg |
| `surface` | mako body, popovers, cards, fuzzel-adjacent chrome |
| `sel` | fuzzel selection, terminal selection bg |
| `muted` | unfocused border and text, placeholders, calendar weeks |
| `fg` | body text everywhere |
| `fg_bright` | focused window title, active text |
| **`accent`** | sway focused border, waybar focused workspace, GTK accent, fuzzel border |
| `accent2` | focused-inactive border, calendar weekdays, gtklock buttons, waybar mode |
| `indicator` | sway split indicator — where the next window will open |
| **`critical`** | urgent window, critical CPU/battery, destructive actions |
| `warning` | warning states, "today" in the calendar, idle inhibitor on |
| `success` | battery charging, success states |
| `desktop` | the wallpaper-less background, one shade below `bg` |

`desktop` being darker than `bg` is what turns the gaps between windows into visible channels, and
is what makes `smart_borders on` safe. Nord has nothing below `nord0`, so its value is a
hand-darkened one; Gruvbox ships the idea as `bg0_h`. `palettes.toml` records both.

Two per-palette values are not colours and still have to be chosen per palette: `gtk_theme_name`
and `papirus_folder`. They live in the same table.

A third group is the **16-colour terminal ramp**, under `[<palette>.ansi]`. Eight of its slots are
role colours; the other eight are not, and are shared by alacritty and foot. They used to be
duplicated across both applications with a comment asking that they be kept in step by hand.

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
and the unfolded packages that carry templates (`gtk`, `alacritty`, `vim` — `bin` and `claude`
are also unfolded but carry none) link file-by-file — a file created
after `stow` is silently absent until `stow -R`. The folded packages pick it up for free. See
§5.2.

Applying is idempotent: re-running repairs a deleted or edited artefact.

**foot does not reload.** It has no config-reload signal at all; `SIGUSR1`/`SIGUSR2` only pick
between the `[colors-dark]` and `[colors-light]` blocks loaded at startup. A switch needs a foot
server restart or a logout.

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
| `tmux` | repo | Terminal multiplexer. Optional to the desktop, but its status bar is themed from `palettes.toml` like everything else, so a machine without it simply renders a `colors.gen.conf` nobody reads. `git` is a soft dependency of the bar's right-hand segment — absent, the branch is blank rather than broken |
| `nord-vim`, `gruvbox` | **source** | vim colorschemes, cloned into `~/.vim/pack/plugins/start/` — §8. Without them vim still starts; `vim/.vimrc` guards the `source` with `filereadable` |
| `lualine.nvim`, `nvim-web-devicons` | **self-installing** | nvim's statusline. Fetched by `vim.pack.add` in `init.lua` on first launch, into `~/.local/share/nvim/site/pack/core/opt` — nothing to clone by hand, and nothing in `~/.config/nvim` (§5.2). nvim's *colourschemes* are still written from the §3.1 roles rather than cloned, and lualine is themed from them too, so no plugin decides a colour here |

**Why the gruvbox GTK theme is not the AUR package.** `gruvbox-gtk-theme-git` depends on
`gtk-engine-murrine`, which on a current Arch pulls in a **from-source `gtk2` build** — and gtk2 is
not installed here, nor wanted for one theme. `vinceliuice/Colloid-gtk-theme` has a gruvbox tweak
that produces the same result, installs into `~/.themes` without root, and needs no engine.

### 4.3 Deliberately not used

`swaylock` (gtklock does the job and is already themed), `wofi`/`rofi` (fuzzel), `dunst` (mako),
`lxappearance` (GTK3+ only reads settings.ini), `qt5ct`/`qt6ct` (no Qt apps in this setup yet —
add them if that changes, as Qt apps will otherwise ignore the theme entirely).

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
| `sway` `mako` `fuzzel` `nwg-drawer` `gtklock` `kanshi` `foot` `waybar` | **Yes** | Nothing writes into these directories. New files appear for free. |
| `tmux` | **Yes** | tmux itself never writes to `~/.config/tmux` — its state is sockets under `$TMUX_TMPDIR`. The package is at the XDG path rather than `~/.tmux.conf` (tmux has read it since 3.1) precisely so that folding is available: the rendered `colors.gen.conf` and `scripts/git-branch.sh` then appear with no `stow -R`, and neither has to sit loose in `$HOME`. **The one thing that would break this is a plugin manager**: tpm installs into `~/.config/tmux/plugins`, which folded means untracked plugin clones inside the repo. None is used today; adding one means unfolding first. |
| `nvim` | **Yes** | Neovim keeps its state in `~/.local/share/nvim`, `~/.local/state/nvim` and `~/.cache/nvim`, and `vim.pack` puts plugin *code* in `~/.local/share/nvim/site/pack/core/opt` — none of it in `~/.config/nvim`, so the reason `vim` stays unfolded does not apply. Folded, a newly rendered `colorscheme.gen.lua` and any new themed file appear without `stow -R`. **The one thing `vim.pack` does write here is `nvim-pack-lock.json`**, which folding puts straight into the repo — so it is tracked deliberately (§8) rather than ignored, which is what keeps the "no untracked content inside a folded directory" rule satisfied. It is rewritten in place, not by `rename()`, so unlike `htop` (§9.16) folding is a choice here rather than a requirement. |
| `alacritty` | **No** | `themes/` is an untracked clone of alacritty/alacritty-theme living inside `~/.config/alacritty`. Folding would put the clone inside the repo. |
| `gtk` | **No** | **nwg-look writes into `~/.config/gtk-{3,4}.0`.** See §9.1. Only specific files are tracked; `bookmarks` is left alone as machine-specific. |
| `bin` | **No** | `~/.local/bin` is a real directory holding untracked binaries — `claude`, `coderabbit` (104 MB), `herdr` (22 MB), `uv`. Folding would pull all of it into the repo. A newly added script therefore needs `stow -R bin`. |
| `vim` | **No** | `~/.vim` holds untracked plugin clones (`lightline`, and now `nord-vim` and `gruvbox`), so folding would pull them into the repo. A newly added file in the package — such as a future theme fragment — is silently absent until `stow -R vim`. That is exactly the trap this section exists to document. |
| `claude` | **No** | `~/.claude` is Claude Code's own state directory — `sessions/`, `history.jsonl`, `projects/`, `plugins/`, `.credentials.json`, all untracked and some of it secret. Folding would pull the lot into the repo. It also already contains `skills`, a directory symlink to `~/repos/xl-skills/skills`, which folding would swallow. Unfolded, stow links only `statusline.py`; a second file added to the package later needs `stow -R claude`. Note the repo's own `.claude/` at the root is Claude Code *project* state for this repo and is not a package — never name it in a stow command. |
| `htop` | **Yes — and it must be** | When htop does save `htoprc` (clean quit, settings changed) it uses `mkstemp` + `rename()`. A `rename()` onto a *file* symlink replaces the symlink with a regular file, so an unfolded `htop` would silently detach from the repo the first time it saved. Folded, the write lands on the repo's own file. See §9.16. |

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

**The theming work did not change a single row of this table, by design.** Each theme fragment and
its symlink live *inside* the package that owns them, so switching writes into the repo, never into
`~/.config`. The alternative — a pair of per-palette stow packages — would have
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
| mako frame | 5px border, square | 2px border, `border-radius=10,0,0,10` | Rounded on the left, square on the right, so the card reads as a tab flush against the screen edge. Note `border-size` is **not** directional in mako 1.11 — only `margin`, `outer-margin`, `padding` and `border-radius` are, so a per-edge accent *spine* cannot be expressed; asymmetric corners are the closest thing |
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
| **Hex guard blind to bare colours** | `tests/check_hex.py` asserts "no tracked config carries a literal hex" and passed while `sway/…/config.d/default` ran `fuzzel … -t bf616aff -S bf616aff`. The regex required a leading `#`; fuzzel's `-t`/`-S` want a bare `RRGGBBAA`. Same colour, different spelling. The cost was not the one off-palette picker — it was a green check certifying a rule it could not see | `BARE_HEX` pattern added; the binding moved into `scripts/cliphist_delete.sh`, which sources `theme.gen.env` and derives `${CRITICAL#\#}ff` at press time, because `config.d/default` is parsed before `config.d/theme` (§9.6) | `python3 tests/check_hex.py .`; `theme gruvbox` then `$mod+Ctrl+x` — picker is gruvbox red, not Nord red |
| **Critical notifications expired after 5s** | `[urgency=high] ignore-timeout=1` was commented "never time out on their own". It does not mean that. Per `man 5 mako` it means *ignore the timeout the app asked for and use `default-timeout` instead* — which is `5000` globally. So critical notifications vanished after five seconds, **and** an app that explicitly asked to stay longer was overridden into vanishing sooner. The comment described the intent, not the behaviour, and nothing ever checked | `default-timeout=0` alongside `ignore-timeout=1` in the same criteria. The pair is what makes it stick: ignore what the app said, then apply no timeout | `notify-send -u critical x y`, wait >5s, `makoctl list` still shows it |
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

```sh
# Tint the Papirus folder icons (writes into /usr/share/icons, so root).
# `theme` re-runs this on an INTERACTIVE switch when the colour differs -- it skips
# papirus-folders when stdin is not a tty, because it needs sudo. This is just
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

# nvim: nothing to run. Its colourschemes are written from the §3.1 roles in
# nvim/.config/nvim/colorscheme-{nord,gruvbox}.lua, so there is no colorscheme
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

# The palette renderer, so `theme` is on $PATH
stow bin

# Render the colour files. They are gitignored, so a fresh clone does not have
# them, and every themed package needs them present BEFORE it is stowed — the
# unfolded ones (gtk, alacritty, vim) link file-by-file and would otherwise miss
# them, leaving each application with no colours to include.
theme nord --no-icons          # or gruvbox; must report "18 files rendered"

# ~/.bashrc already exists from /etc/skel and stow will not overwrite a real file
mv ~/.bashrc ~/.bashrc.bak && stow bash
```

**`theme` before `stow`, always.** If you stow first, run `stow -R <pkg>` afterwards for the
unfolded packages, or the rendered files will exist in the repo and be absent from `~`.

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
`pkill -x foot` — which `theme <name> --restart-terminals` runs — makes the old server release its
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
`theme <name> --restart-terminals` is opt-in.

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
| `htoprc` edit reverted | A running htop flushed its in-memory settings on quit | `pkill -9 htop`, then edit; §9.16 |
| htop changes stopped reaching the repo | `rename()` replaced the symlink | `ls -ld ~/.config/htop` must be a symlink; §9.16 |
| htop right-hand CPUs render below the left | All meters piled into `column_meters_0` | §9.16 |
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
