# Nord ↔ Gruvbox Theme Switching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the desktop switch between Nord and Gruvbox Dark with one command (`theme gruvbox`), without losing stow's tree folding.

**Architecture:** Each application's colours move out of its config into a fragment file included under a theme-neutral name. That name is a symlink tracked in the repo pointing at `<base>-nord.<ext>` or `<base>-gruvbox.<ext>`. A `theme` script discovers every such symlink by its target's name and flips it, then reloads the running daemons. Stow is not involved in switching — it deploys packages exactly as it does today.

**Tech Stack:** GNU Stow, sway, waybar, foot, fuzzel, mako, gtklock, nwg-drawer, GTK2/3/4, vim, POSIX sh.

## Global Constraints

- **Repo lives at `~/repos/dotfiles`, not `$HOME`.** `.stowrc` pins `--target=~`. Always run stow from the repo root.
- **No build, no test suite.** `stow -n -v <pkg>` (dry run) is the verification step before `stow <pkg>`. Config validators (`sway --validate`, `foot --check-config`, `fuzzel --check-config`) are the closest thing to tests and MUST be run where they exist.
- **Never inline a hex in an application config.** Every colour is one of the thirteen role names below. This is the entire point of the change.
- **The thirteen roles, with both palettes.** Copy these values verbatim; do not re-derive them.

  | Role | Nord | Gruvbox Dark |
  |---|---|---|
  | `bg` | `#2E3440` | `#282828` |
  | `surface` | `#3B4252` | `#3C3836` |
  | `sel` | `#434C5E` | `#504945` |
  | `muted` | `#4C566A` | `#7C6F64` |
  | `fg` | `#D8DEE9` | `#EBDBB2` |
  | `fg_bright` | `#ECEFF4` | `#FBF1C7` |
  | `accent` | `#88C0D0` | `#FABD2F` |
  | `accent2` | `#5E81AC` | `#D65D0E` |
  | `indicator` | `#8FBCBB` | `#8EC07C` |
  | `critical` | `#BF616A` | `#FB4934` |
  | `warning` | `#EBCB8B` | `#FE8019` |
  | `success` | `#A3BE8C` | `#B8BB26` |
  | `desktop` | `#272B33` | `#1D2021` |

- **File naming is load-bearing.** The `theme` script finds symlinks whose target matches `-nord.` / `-nord` at the end, or the same for `gruvbox`. Fragments MUST be named `<base>-nord.<ext>` and `<base>-gruvbox.<ext>`, and the symlink `<base>.<ext>`. A fragment named anything else is silently not switched.
- **Symlink targets are relative and bare** (`ln -sfn colors-nord.css colors.css`, never an absolute path), so the repo stays relocatable.
- **Commit the symlinks.** They are ordinary tracked files; `git` records them as typechanges when flipped.
- **Sway reload safety:** after any sway change run `sway --validate -c ~/.config/sway/config` **before** `swaymsg reload`, then `pgrep -xc swayidle` (must be exactly 1, and still 1 after a second reload).

### Verified mechanics (do not re-litigate)

These were checked against the installed software during design. Trust them.

- foot: `include=` works before or inside `[main]`, and accepts `~/`. **`[colors]` is deprecated — the fragment must use `[colors-dark]`.**
- fuzzel: `include=` works, accepts `~/`. Verified with `--check-config`.
- mako: `include=` works, and **the included file may contain `[urgency=…]` criteria sections**.
- sway: `include ../colors.conf` resolves relative to the *including file's* directory. `set $var` defined in the include is visible to the includer.
- waybar: `include` merges, and **the first-defined value wins (including file beats included file)**. So a module defined in `config` must be *removed* from `config` to let the fragment define it.
- GTK CSS: `@import url("colors.css")` plus `@define-color` in the imported file works, including through a symlink, and `alpha(@role, 0.4)` works.

---

## File Structure

| Path | Responsibility |
|---|---|
| `sway/.config/sway/theme-{nord,gruvbox}.env` | The thirteen roles as shell variables. Source of truth for scripts. |
| `sway/.config/sway/colors-{nord,gruvbox}.conf` | The roles as sway `set $var`, plus `client.*` and `output bg`. |
| `waybar/.config/waybar/colors-{nord,gruvbox}.css` | The roles as GTK `@define-color`. |
| `waybar/.config/waybar/colors-{nord,gruvbox}.json` | The `clock` module, whose calendar markup carries inline colours. |
| `foot/.config/foot/colors-{nord,gruvbox}.ini` | `[colors-dark]` block. |
| `alacritty/.config/alacritty/colors-{nord,gruvbox}.toml` | `[colors.*]` tables. |
| `fuzzel/.config/fuzzel/colors-{nord,gruvbox}.ini` | `[colors]` block. |
| `mako/.config/mako/colors-{nord,gruvbox}` | Colour keys plus `[urgency=…]` sections. |
| `gtklock/.config/gtklock/colors-{nord,gruvbox}.css` | `@define-color` for the lock screen. |
| `nwg-drawer/.config/nwg-drawer/colors-{nord,gruvbox}.css` | `@define-color` for the app grid. |
| `gtk/.config/gtk-{3,4}.0/{settings,gtk}-{nord,gruvbox}.{ini,css}` | GTK theme name + libadwaita named colours. |
| `gtk/.gtkrc-2.0-{nord,gruvbox}` | GTK2. |
| `gtk/.config/xsettingsd/xsettingsd-{nord,gruvbox}.conf` | XSettings for XWayland. |
| `gtk/.icons/default/index.theme` | Cursor for the desktop and XWayland. Theme-independent. |
| `vim/.vim/colorscheme-{nord,gruvbox}.vim` | vim + lightline colorscheme. |
| `bash/.config/dircolors` | `LS_COLORS`, ANSI-16 only. Theme-independent. |
| `bin/.local/bin/theme` | The switcher. |

---

### Task 1: Shell palette — the role vocabulary

Establishes both palettes in the one format every later task can read, and the naming convention the switcher depends on.

**Files:**
- Create: `sway/.config/sway/theme-nord.env`
- Create: `sway/.config/sway/theme-gruvbox.env`
- Create: `sway/.config/sway/theme.env` (symlink → `theme-nord.env`)

**Interfaces:**
- Produces: thirteen shell variables — `BG SURFACE SEL MUTED FG FG_BRIGHT ACCENT ACCENT2 INDICATOR CRITICAL WARNING SUCCESS DESKTOP` — each a `#RRGGBB` string, plus `PAPIRUS_FOLDER` and `GTK_THEME_NAME`. Sourced by `sway/scripts/screenshot_*.sh`, `waybar/scripts/keyhint.sh` and `bin/theme` in later tasks.

- [ ] **Step 0: Confirm the Gruvbox GTK theme is present**

**Already installed — do not install anything.** The theme name is
`Colloid-Yellow-Dark-Gruvbox`, in `~/.themes/`. Verify and move on:

```bash
test -d ~/.themes/Colloid-Yellow-Dark-Gruvbox/gtk-3.0 && echo "theme present ✓"
```

If that fails, stop and report — do not substitute another theme name.

Background, for the docs task later. This replaced the AUR route the design
assumed. `gruvbox-gtk-theme-git` depends on `gtk-engine-murrine`, which pulls a
from-source **gtk2** build; gtk2 is not installed on this machine and nothing
here uses it. Colloid ships an installer that places exactly one variant into a
user directory with no root at all, which is also how `alacritty-theme` and
`lightline` are already handled (PLAYBOOK §8). It was installed with:

```bash
git clone --depth 1 https://github.com/vinceliuice/Colloid-gtk-theme
cd Colloid-gtk-theme
./install.sh -d ~/.themes -c dark -s standard -t yellow --tweaks gruvbox
```

**Never pass `-l`/`--libadwaita` to that installer.** It writes a theme into
`~/.config/gtk-4.0/`, destroying the stow-managed `gtk.css` there — the same
failure mode PLAYBOOK §9.1 documents for nwg-look.

- [ ] **Step 1: Write the Nord palette**

`sway/.config/sway/theme-nord.env`:

```sh
# Nord — the thirteen theme roles as shell variables.
#
# Sourced by scripts that cannot parse CSS: sway/scripts/screenshot_*.sh,
# waybar/scripts/keyhint.sh, and ~/.local/bin/theme.
#
# This file is the shell-readable half of a palette that also exists as
# sway `set $var` (colors-nord.conf), GTK @define-color (waybar, gtklock,
# nwg-drawer), and per-application colour keys (foot, fuzzel, mako, alacritty).
# All of them must agree. Roles are documented in PLAYBOOK.md §3.1.

BG=#2E3440
SURFACE=#3B4252
SEL=#434C5E
MUTED=#4C566A
FG=#D8DEE9
FG_BRIGHT=#ECEFF4
ACCENT=#88C0D0
ACCENT2=#5E81AC
INDICATOR=#8FBCBB
CRITICAL=#BF616A
WARNING=#EBCB8B
SUCCESS=#A3BE8C
DESKTOP=#272B33

# papirus-folders calls the Nord folder colour "nordic" and rejects "nord"
# outright. The icons really are Nord. See PLAYBOOK.md §3.2.
PAPIRUS_FOLDER=nordic

# /usr/share/themes/<name>, from the AUR package `nordic-theme`.
GTK_THEME_NAME=Nordic
```

- [ ] **Step 2: Write the Gruvbox palette**

`sway/.config/sway/theme-gruvbox.env`:

```sh
# Gruvbox Dark — the thirteen theme roles as shell variables.
#
# The counterpart to theme-nord.env; both must define exactly the same
# variable names. `theme` refuses to switch if they diverge.
#
# Focus is gruvbox's warm yellow, its signature colour, with warning one hue
# step away in orange. They sit closer together than Nord's cyan/yellow pair,
# so warning states read as *hotter* rather than as a different colour.

BG=#282828
SURFACE=#3C3836
SEL=#504945
MUTED=#7C6F64
FG=#EBDBB2
FG_BRIGHT=#FBF1C7
ACCENT=#FABD2F
ACCENT2=#D65D0E
INDICATOR=#8EC07C
CRITICAL=#FB4934
WARNING=#FE8019
SUCCESS=#B8BB26

# bg0_h, gruvbox's canonical "hard" background. Nord needs a hand-darkened
# #272B33 here because the palette has nothing below nord0; gruvbox ships
# exactly this idea, so no off-palette value is needed.
DESKTOP=#1D2021

# papirus-folders has no gruvbox colour; `yellow` is the closest match to the
# palette's signature accent.
PAPIRUS_FOLDER=yellow

# ~/.themes/<name>, installed from vinceliuice/Colloid-gtk-theme. See Step 0.
GTK_THEME_NAME=Colloid-Yellow-Dark-Gruvbox
```

- [ ] **Step 3: Create the symlink and verify both parse**

```bash
cd ~/repos/dotfiles/sway/.config/sway
ln -sfn theme-nord.env theme.env
sh -n theme-nord.env && sh -n theme-gruvbox.env && echo "syntax OK"
( . ./theme.env && echo "accent=$ACCENT papirus=$PAPIRUS_FOLDER" )
```

Expected: `syntax OK` then `accent=#88C0D0 papirus=nordic`.

- [ ] **Step 4: Verify the two palettes define identical variable names**

```bash
cd ~/repos/dotfiles/sway/.config/sway
diff <(grep -oE '^[A-Z_]+=' theme-nord.env | sort) \
     <(grep -oE '^[A-Z_]+=' theme-gruvbox.env | sort) && echo "roles match"
```

Expected: `roles match` with no diff output. This is the check the switcher will automate in Task 3.

- [ ] **Step 5: Deploy and confirm folding survived**

```bash
cd ~/repos/dotfiles
stow -n -v sway          # dry run first, always
stow -R sway
ls -la ~/.config | grep ' sway'
```

Expected: `sway -> ../repos/dotfiles/sway/.config/sway` — still a symlink, i.e. still folded. What matters is the arrow, not the exact number of `../` segments.

- [ ] **Step 6: Commit**

```bash
cd ~/repos/dotfiles
git add sway/.config/sway/theme-nord.env sway/.config/sway/theme-gruvbox.env sway/.config/sway/theme.env
git commit -m "Add the Nord and Gruvbox palettes as shell role variables"
```

---

### Task 2: sway colours

**Files:**
- Create: `sway/.config/sway/colors-nord.conf`
- Create: `sway/.config/sway/colors-gruvbox.conf`
- Create: `sway/.config/sway/colors.conf` (symlink → `colors-nord.conf`)
- Modify: `sway/.config/sway/config.d/theme` — replace the `client.*` block and the `output * bg` line with an include

**Interfaces:**
- Consumes: nothing from Task 1 at runtime (sway cannot read `.env` files); the hexes are duplicated here as `set $var`. This duplication is inherent — see the note in Step 1.
- Produces: sway variables `$bg $surface $sel $muted $fg $fg_bright $accent $accent2 $indicator $critical $warning $success $desktop`.

- [ ] **Step 1: Write the Nord sway fragment**

`sway/.config/sway/colors-nord.conf`:

```
# Nord — sway's copy of the thirteen theme roles.
#
# sway cannot source theme-nord.env (it has no shell), so the hexes appear
# twice. Keep the two in step; PLAYBOOK.md §3.1 is the authority.
#
# Included by config.d/theme as `include ../colors.conf`, where colors.conf is
# a symlink to this file or to colors-gruvbox.conf.

set $bg        #2E3440
set $surface   #3B4252
set $sel       #434C5E
set $muted     #4C566A
set $fg        #D8DEE9
set $fg_bright #ECEFF4
set $accent    #88C0D0
set $accent2   #5E81AC
set $indicator #8FBCBB
set $critical  #BF616A
set $warning   #EBCB8B
set $success   #A3BE8C
set $desktop   #272B33
```

- [ ] **Step 2: Write the Gruvbox sway fragment**

`sway/.config/sway/colors-gruvbox.conf`:

```
# Gruvbox Dark — sway's copy of the thirteen theme roles.
# Counterpart to colors-nord.conf; both must define the same set of names.

set $bg        #282828
set $surface   #3C3836
set $sel       #504945
set $muted     #7C6F64
set $fg        #EBDBB2
set $fg_bright #FBF1C7
set $accent    #FABD2F
set $accent2   #D65D0E
set $indicator #8EC07C
set $critical  #FB4934
set $warning   #FE8019
set $success   #B8BB26
set $desktop   #1D2021
```

- [ ] **Step 3: Rewrite the colour half of `config.d/theme`**

In `sway/.config/sway/config.d/theme`, put the include at the very top of the file (before `exec_always ~/.config/sway/scripts/import-gsettings`), because sway variables must be defined before use:

```
# Palette. `colors.conf` is a symlink to colors-nord.conf or
# colors-gruvbox.conf; ~/.local/bin/theme flips it. The path is relative to
# THIS file's directory (config.d/), so `../` reaches ~/.config/sway/.
#
# This must come before anything that uses $accent and friends.
include ../colors.conf
```

Then replace the `output * bg #272B33 solid_color` line with:

```
output * bg $desktop solid_color
```

And replace the five `client.*` lines plus `client.background` with:

```
# class                 border     bground    text       indicator   child_border
client.focused          $accent    $bg        $fg_bright $indicator  $accent
client.focused_inactive $accent2   $bg        $fg        $accent2    $accent2
client.unfocused        $muted     $bg        $muted     $muted      $muted
client.urgent           $critical  $critical  $fg_bright $critical   $critical
client.placeholder      $muted     $bg        $fg        $muted      $muted
client.background       $bg
```

Keep every surrounding comment in the file intact — the tuning notes, the brightness-ladder explanation and the `smart_borders` discussion are still accurate. Update only the two places that name a literal hex: the `#272B33` explanation in the background comment (now `$desktop`) and the `nord3 #4C566A` mentions in the border comment (now `$muted`, with the Nord value given as an example).

- [ ] **Step 4: Create the symlink and validate**

```bash
cd ~/repos/dotfiles/sway/.config/sway
ln -sfn colors-nord.conf colors.conf
sway --validate -c ~/.config/sway/config
```

Expected: no output, exit 0.

- [ ] **Step 5: Validate the Gruvbox fragment too**

```bash
cd ~/repos/dotfiles/sway/.config/sway
ln -sfn colors-gruvbox.conf colors.conf
sway --validate -c ~/.config/sway/config
ln -sfn colors-nord.conf colors.conf          # back to Nord
sway --validate -c ~/.config/sway/config
```

Expected: no output, exit 0, both times. This catches a role defined in one fragment but not the other.

- [ ] **Step 6: Apply and check the swayidle invariant**

```bash
stow -R sway
swaymsg reload
pgrep -xc swayidle        # must print 1
swaymsg reload
pgrep -xc swayidle        # must still print 1
```

Look at the screen: focused window border cyan, desktop background a shade darker than window backgrounds. Nothing should have changed visually.

- [ ] **Step 7: Commit**

```bash
cd ~/repos/dotfiles
git add sway/.config/sway/colors-nord.conf sway/.config/sway/colors-gruvbox.conf \
        sway/.config/sway/colors.conf sway/.config/sway/config.d/theme
git commit -m "Move sway colours into a switchable palette fragment"
```

---

### Task 3: The `theme` switcher

Built now, before the remaining applications, so every later task can be verified by actually switching rather than by hand-editing symlinks. It discovers symlinks by pattern, so it needs no updating as later tasks add fragments.

**Files:**
- Create: `bin/.local/bin/theme`
- Modify: `sway/.config/sway/config.d/default` — add the keybinding

**Interfaces:**
- Consumes: `sway/.config/sway/theme-{nord,gruvbox}.env` from Task 1 (for `PAPIRUS_FOLDER`).
- Produces: the `theme` command. Later tasks verify with `theme gruvbox && theme nord`.

- [ ] **Step 1: Write the script**

`bin/.local/bin/theme`:

```sh
#!/bin/sh
# theme — switch the desktop between Nord and Gruvbox Dark.
#
#   theme                 print the active theme
#   theme nord|gruvbox    switch
#   theme toggle          switch to the other one          ($mod+Shift+t)
#
#   --restart-terminals   also restart `foot --server`, applying the palette to
#                         foot immediately at the cost of every open shell
#   --no-icons            skip papirus-folders (avoids the sudo prompt)
#
# HOW IT WORKS
#   Every colour-bearing config includes a theme-neutral filename which is a
#   symlink tracked in the repo, e.g.
#       waybar/.config/waybar/colors.css -> colors-nord.css
#   This script finds every symlink in the repo whose target ends in
#   `-nord.<ext>` / `-nord` (or the gruvbox equivalent) and repoints it at its
#   sibling. Nothing is hardcoded, so adding a new themed application means
#   adding the two fragments and the symlink — no change here.
#
#   stow is deliberately NOT involved. Flipping a symlink inside the repo
#   leaves every package's fold state untouched; switching with stow packages
#   would unfold them. See PLAYBOOK.md.
set -eu

REPO="$HOME/repos/dotfiles"
THEMES="nord gruvbox"

# NOTE ON `set -e`: a bare `[ cond ] && action` is a landmine here. When the
# test fails the whole list returns non-zero and `set -e` kills the script. Use
# `if` blocks for every guard below, never `&&`.
die() { printf 'theme: %s\n' "$*" >&2; exit 1; }

# The active theme, read from the symlinks themselves rather than a state file,
# so it can never disagree with reality.
current_theme() {
    t=$(readlink "$REPO/sway/.config/sway/theme.env" 2>/dev/null) || return 1
    case "$t" in
        theme-nord.env)    echo nord ;;
        theme-gruvbox.env) echo gruvbox ;;
        *) return 1 ;;
    esac
}

# Every repo symlink pointing at a per-theme fragment.
theme_links() {
    find "$REPO" -name .git -prune -o -type l -print | while read -r link; do
        target=$(readlink "$link")
        case "$target" in
            *-nord|*-nord.*|*-gruvbox|*-gruvbox.*) printf '%s\n' "$link" ;;
        esac
    done
}

# Both palettes must define the same role names. A role defined in only one of
# them renders as black in GTK CSS with no error, which is near-impossible to
# diagnose from the symptom — so refuse to switch instead.
#
# Plain string comparison rather than `diff <(...) <(...)`: process substitution
# is a bashism, and this script is /bin/sh. (On Arch /bin/sh happens to be bash,
# so it would work today — but the shebang says sh, so it stays sh.)
check_roles() {
    d="$REPO/sway/.config/sway"
    a=$(grep -oE '^[A-Z_]+=' "$d/theme-nord.env" | sort)
    b=$(grep -oE '^[A-Z_]+=' "$d/theme-gruvbox.env" | sort)
    if [ "$a" != "$b" ]; then
        die "theme-nord.env and theme-gruvbox.env define different roles"
    fi

    an=$(grep -oE '^set \$[a-z_]+' "$d/colors-nord.conf" | sort)
    bn=$(grep -oE '^set \$[a-z_]+' "$d/colors-gruvbox.conf" | sort)
    if [ "$an" != "$bn" ]; then
        die "colors-nord.conf and colors-gruvbox.conf define different roles"
    fi
}

# Rename one fragment path from theme $from to theme $to. Pure POSIX parameter
# expansion rather than sed, so that `.gtkrc-2.0-nord` (no extension) and
# `colors-nord.css` (extension) are both handled unambiguously.
retarget() {
    case $1 in
        *-"$2".*) printf '%s-%s.%s' "${1%-$2.*}" "$3" "${1##*.}" ;;
        *-"$2")   printf '%s-%s' "${1%-$2}" "$3" ;;
        *)        return 1 ;;
    esac
}

switch_to() {
    to=$1
    from=$(current_theme) || die "cannot determine the active theme; is sway/.config/sway/theme.env a symlink?"
    if [ "$to" = "$from" ]; then
        echo "Already $to."
        return 0
    fi

    check_roles

    # `for` over command substitution, not a `while read` pipeline: the counter
    # must survive the loop, and a pipeline would run it in a subshell. Safe
    # because no path in this repo contains whitespace.
    n=0
    for link in $(theme_links); do
        target=$(readlink "$link")
        newtarget=$(retarget "$target" "$from" "$to") || continue
        if [ ! -e "$(dirname "$link")/$newtarget" ]; then
            die "missing fragment: $(dirname "$link")/$newtarget"
        fi
        ln -sfn "$newtarget" "$link"
        n=$((n + 1))
    done
    echo "Switched $n symlinks: $from -> $to"
}

reload_desktop() {
    # sway reload also restarts waybar (it owns the bar process), re-runs
    # scripts/import-gsettings (pushing the new GTK/icon/cursor names into
    # gsettings, which is what libadwaita apps read), and re-execs nwg-drawer.
    if command -v swaymsg >/dev/null 2>&1 && swaymsg -t get_version >/dev/null 2>&1; then
        sway --validate -c "$HOME/.config/sway/config" || die "sway config is invalid; not reloading"
        swaymsg reload >/dev/null
        echo "  sway, waybar, nwg-drawer, gsettings  reloaded"
    else
        echo "  sway not running; skipped"
    fi

    # mako is exec'd, not exec_always'd, so a sway reload does not restart it.
    if command -v makoctl >/dev/null 2>&1 && makoctl reload 2>/dev/null; then
        echo "  mako                                  reloaded"
    fi
}

reload_icons() {
    . "$REPO/sway/.config/sway/theme-$1.env"
    command -v papirus-folders >/dev/null 2>&1 || return 0

    # `papirus-folders -l` marks the active colour with a leading "> ".
    active=$(papirus-folders -l 2>/dev/null | awk '/^ *>/ {print $2}')
    if [ "$active" = "$PAPIRUS_FOLDER" ]; then
        return 0
    fi

    # Writes into /usr/share/icons, so it is the one step needing root and the
    # one thing that cannot be stowed. Skip rather than hang when there is no
    # terminal to prompt on.
    if [ ! -t 0 ]; then
        echo "  papirus-folders  SKIPPED (no tty for sudo); run: sudo papirus-folders -C $PAPIRUS_FOLDER -t Papirus-Dark"
        return 0
    fi
    echo "  papirus-folders -> $PAPIRUS_FOLDER (needs sudo)"
    sudo papirus-folders -C "$PAPIRUS_FOLDER" -t Papirus-Dark >/dev/null
}

do_icons=1
restart_terminals=0
target=""
for arg in "$@"; do
    case "$arg" in
        --no-icons)          do_icons=0 ;;
        --restart-terminals) restart_terminals=1 ;;
        -h|--help)           sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)                  die "unknown option: $arg" ;;
        *)                   target=$arg ;;
    esac
done

if [ -z "$target" ]; then
    current_theme || die "cannot determine the active theme"
    exit 0
fi

if [ "$target" = toggle ]; then
    case $(current_theme) in
        nord) target=gruvbox ;;
        *)    target=nord ;;
    esac
fi

case " $THEMES " in
    *" $target "*) ;;
    *) die "unknown theme '$target' (known: $THEMES)" ;;
esac

switch_to "$target"
reload_desktop
if [ "$do_icons" -eq 1 ]; then
    reload_icons "$target"
fi

if [ "$restart_terminals" -eq 1 ]; then
    pkill -x foot 2>/dev/null || true
    foot --server >/dev/null 2>&1 &
    echo "  foot --server restarted"
else
    # foot has no config-reload signal: SIGUSR1/2 only pick between the
    # [colors-dark] and [colors-light] blocks loaded at startup.
    echo
    echo "Not yet showing the new palette:"
    echo "  foot        open terminals and the running server keep the old colours."
    echo "              Re-run with --restart-terminals, or log out."
fi
echo "  GTK apps    already-running ones keep the old theme; restart them."
echo
echo "The flipped symlinks are uncommitted; \`git -C $REPO status\` to see them."
```

- [ ] **Step 2: Make it executable, deploy, and check it reads the current theme**

```bash
cd ~/repos/dotfiles
chmod +x bin/.local/bin/theme
stow -n -v bin
stow bin
which theme && theme
```

Expected: `/home/xinye/.local/bin/theme` then `nord`.

- [ ] **Step 3: Switch to Gruvbox and confirm the symlinks moved**

```bash
theme gruvbox
readlink ~/repos/dotfiles/sway/.config/sway/colors.conf
readlink ~/repos/dotfiles/sway/.config/sway/theme.env
```

Expected: `Switched 2 symlinks: nord -> gruvbox`, then `colors-gruvbox.conf` and `theme-gruvbox.env`. The desktop background and window borders should now be gruvbox — dark brown-grey background, warm yellow focus border.

- [ ] **Step 4: Confirm folding survived the switch — the core claim of the design**

```bash
for p in sway waybar foot mako fuzzel gtklock nwg-drawer; do
  printf '%-12s ' "$p"
  if [ -L ~/.config/$p ]; then echo "folded (symlink)"; else echo "UNFOLDED (real dir)"; fi
done
```

Expected: seven lines, every one `folded (symlink)`. Any `UNFOLDED (real dir)` means something has written into the target tree from outside its package — stop and investigate.

Do **not** test this with `ls -la ~/.config | grep -E ' (pkg)$'`. `ls -la` renders a symlink as `name -> target`, so a `$` anchor matches only the unfolded case: the command prints nothing when folding is healthy, which reads as a pass but proves nothing. Test the link type directly with `[ -L ]`, as above.

- [ ] **Step 5: Switch back, and confirm idempotence**

```bash
theme nord
theme nord
pgrep -xc swayidle
```

Expected: the second `theme nord` prints `Already nord.` and exits 0. `pgrep` prints `1`.

- [ ] **Step 6: Add the keybinding**

In `sway/.config/sway/config.d/default`, alongside the other `bindsym` lines:

```
# Switch between the Nord and Gruvbox palettes. See ~/.local/bin/theme.
bindsym $mod+Shift+t exec theme toggle
```

- [ ] **Step 7: Validate, reload, and test the binding**

```bash
cd ~/repos/dotfiles
stow -R sway
sway --validate -c ~/.config/sway/config
swaymsg reload
```

Press `$mod+Shift+t` twice. The desktop should flip to Gruvbox and back.

- [ ] **Step 8: Commit**

```bash
cd ~/repos/dotfiles
git add bin sway/.config/sway/config.d/default
git commit -m "Add the theme switcher and bind it to \$mod+Shift+t"
```

---

### Task 4: waybar

The largest single diff: `@nord0`…`@nord15` become role names throughout `style.css`.

**Files:**
- Create: `waybar/.config/waybar/colors-nord.css`, `colors-gruvbox.css`, `colors.css` (symlink)
- Create: `waybar/.config/waybar/colors-nord.json`, `colors-gruvbox.json`, `colors.json` (symlink)
- Modify: `waybar/.config/waybar/style.css` — replace the palette block with `@import`, rename every `@nordN`
- Modify: `waybar/.config/waybar/config` — add `include`, **remove** the `clock` module

**Interfaces:**
- Consumes: the role names from Task 1.
- Produces: GTK `@define-color` names `bg surface sel muted fg fg_bright accent accent2 indicator critical warning success desktop`, reused by Task 7's gtklock and nwg-drawer fragments.

- [ ] **Step 1: Write the two CSS fragments**

`waybar/.config/waybar/colors-nord.css`:

```css
/* Nord — the thirteen theme roles as GTK named colours.
 *
 * Imported by style.css via a `colors.css` symlink that ~/.local/bin/theme
 * flips. The same thirteen names are defined by gtklock's and nwg-drawer's
 * fragments, so a rule can be moved between them unchanged.
 *
 * All thirteen are defined even where waybar does not use them, so that adding
 * a module later means picking an existing role rather than inventing a hex.
 * Roles are documented in PLAYBOOK.md §3.1. */

@define-color bg        #2E3440;
@define-color surface   #3B4252;
@define-color sel       #434C5E;
@define-color muted     #4C566A;
@define-color fg        #D8DEE9;
@define-color fg_bright #ECEFF4;
@define-color accent    #88C0D0;
@define-color accent2   #5E81AC;
@define-color indicator #8FBCBB;
@define-color critical  #BF616A;
@define-color warning   #EBCB8B;
@define-color success   #A3BE8C;
@define-color desktop   #272B33;
```

`waybar/.config/waybar/colors-gruvbox.css`: identical structure, Gruvbox values from the Global Constraints table, with this header:

```css
/* Gruvbox Dark — the thirteen theme roles as GTK named colours.
 * Counterpart to colors-nord.css; both must define the same thirteen names.
 * A name defined in only one renders as black with no error. */
```

- [ ] **Step 2: Rewrite `style.css`**

Replace the entire `@define-color nord0 … nord15` block (and its surrounding "Nord palette" comment) with:

```css
/* -----------------------------------------------------------------------------
 * Palette
 *
 * `colors.css` is a symlink to colors-nord.css or colors-gruvbox.css;
 * ~/.local/bin/theme flips it. Never write a hex below — use a role.
 *
 * Role convention, shared with sway's colors.conf and every other config here:
 *   accent   focus / active        muted     inactive
 *   warning  warning               critical  urgent
 * -------------------------------------------------------------------------- */

@import url("colors.css");
```

Then rename every reference in the rest of the file:

| Was | Now |
|---|---|
| `@nord0` | `@bg` |
| `@nord3` | `@muted` |
| `@nord4` | `@fg` |
| `@nord6` | `@fg_bright` |
| `@nord8` | `@accent` |
| `@nord10` | `@accent2` |
| `@nord11` | `@critical` |
| `@nord13` | `@warning` |
| `@nord14` | `@success` |

Also update the `#waybar` comment that says "the desktop background … is a shade darker than this bar" — it still holds, but the parenthetical naming `nord0` should say `@bg`.

- [ ] **Step 3: Verify no `@nord` reference survives**

```bash
grep -n '@nord' ~/repos/dotfiles/waybar/.config/waybar/style.css || echo "clean"
```

Expected: `clean`.

- [ ] **Step 4: Verify the CSS actually parses, with both palettes**

This uses the same GTK CSS engine waybar does, so it catches an undefined role before waybar silently renders it black.

```bash
cd ~/repos/dotfiles/waybar/.config/waybar
ln -sfn colors-nord.css colors.css
for pal in nord gruvbox; do
  ln -sfn "colors-$pal.css" colors.css
  python3 - style.css "$pal" <<'EOF'
import sys, gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio
p = Gtk.CssProvider()
try:
    p.load_from_file(Gio.File.new_for_path(sys.argv[1]))
    print(f"{sys.argv[2]}: CSS OK")
except Exception as e:
    print(f"{sys.argv[2]}: FAILED: {e}"); sys.exit(1)
EOF
done
ln -sfn colors-nord.css colors.css
```

Expected: `nord: CSS OK` and `gruvbox: CSS OK`.

- [ ] **Step 5: Extract the `clock` module**

waybar's `include` gives precedence to the **including** file, so `clock` must be **deleted** from `config` entirely, not merely overridden.

`waybar/.config/waybar/colors-nord.json`:

```json
{
    "clock": {
        "format": "󰅐\n{:%a\n%d/%m\n%H:%M}",
        "justify": "center",
        "format-alt": "󰅐\n{:%OI\n%M\n%p}",
        "tooltip-format": " {:%A %d/%m}\n\n<tt>{calendar}</tt>",
        "calendar": {
            "on-scroll": 1,
            "format": {
                "months":   "<span color='#88C0D0'><b>{}</b></span>",
                "days":     "<span color='#D8DEE9'><b>{}</b></span>",
                "weeks":    "<span color='#4C566A'><b>W{}</b></span>",
                "weekdays": "<span color='#8FBCBB'><b>{}</b></span>",
                "today":    "<span color='#EBCB8B'><b><u>{}</u></b></span>"
            }
        }
    }
}
```

The whole module lives here, not just its colours, because JSON has no variables and waybar's include cannot merge into an object the including file already defines. The non-colour keys are therefore duplicated between the two fragments — keep them in step.

Note `weekdays` moves from `#81A1C1` (nord9) to `#8FBCBB` (nord7, the `indicator` role). Both are Frost colours and the change is barely visible; nord9 has no role of its own and inventing a fourteenth for one tooltip line is not worth it.

`waybar/.config/waybar/colors-gruvbox.json`: same object with the calendar colours replaced by `accent` `#FABD2F`, `fg` `#EBDBB2`, `muted` `#7C6F64`, `indicator` `#8EC07C`, `warning` `#FE8019` in that order.

- [ ] **Step 6: Wire the include and delete the old module**

In `waybar/.config/waybar/config`, delete the entire `"clock": { … }` object (including the Nord comment above it), and add near the top, after `"spacing": 0,`:

```json
    // The clock module lives in colors.json — a symlink to colors-nord.json or
    // colors-gruvbox.json, flipped by ~/.local/bin/theme — because its calendar
    // tooltip carries inline Pango colours and JSON has no variables.
    //
    // waybar's include gives precedence to the INCLUDING file, so `clock` must
    // NOT also be defined here or the fragment would be ignored entirely.
    "include": ["~/.config/waybar/colors.json"],
```

- [ ] **Step 7: Create the JSON symlink and restart waybar**

```bash
cd ~/repos/dotfiles/waybar/.config/waybar
ln -sfn colors-nord.json colors.json
cd ~/repos/dotfiles && stow -R waybar
swaymsg reload
```

Expected: the bar comes back looking exactly as before. Hover the clock — the calendar tooltip should render with Nord colours and no missing days.

- [ ] **Step 8: Switch and look at it**

```bash
theme gruvbox
```

Expected: bar background dark brown-grey, focused workspace outlined in warm yellow, clock tooltip in gruvbox colours. Then `theme nord` and confirm it returns.

- [ ] **Step 9: Commit**

```bash
cd ~/repos/dotfiles
git add waybar
git commit -m "Move waybar to role-named colours and a switchable palette"
```

---

### Task 5: foot and alacritty

**Files:**
- Create: `foot/.config/foot/colors-nord.ini`, `colors-gruvbox.ini`, `colors.ini` (symlink)
- Modify: `foot/.config/foot/foot.ini`
- Create: `alacritty/.config/alacritty/colors-nord.toml`, `colors-gruvbox.toml`, `colors.toml` (symlink)
- Modify: `alacritty/.config/alacritty/alacritty.toml`

**Interfaces:**
- Consumes: nothing. Terminal ramps are 16 ANSI colours, not the thirteen roles.
- Produces: the ANSI ramp that `dircolors` (Task 9) and starship rely on to theme themselves for free.

- [ ] **Step 1: Write the foot fragments**

`foot/.config/foot/colors-nord.ini`:

```ini
# Nord — foot's 16-colour ramp.
#
# The section MUST be [colors-dark]: foot deprecated plain [colors] and warns
# on every launch if you use it. With no [colors-light] block defined, foot
# picks colors-dark unconditionally.
#
# Included by foot.ini via a `colors.ini` symlink that ~/.local/bin/theme flips.

[colors-dark]
background=2e3440
foreground=d8dee9

selection-foreground=2e3440
selection-background=4c566a

regular0=3b4252
regular1=bf616a
regular2=a3be8c
regular3=ebcb8b
regular4=81a1c1
regular5=b48ead
regular6=88c0d0
regular7=e5e9f0

bright0=4c566a
bright1=bf616a
bright2=a3be8c
bright3=ebcb8b
bright4=81a1c1
bright5=b48ead
bright6=8fbcbb
bright7=eceff4
```

`foot/.config/foot/colors-gruvbox.ini`:

```ini
# Gruvbox Dark — foot's 16-colour ramp.
#
# Canonical gruvbox values, with one deliberate deviation: regular0 is bg1
# (3c3836) rather than the canonical 282828, which would make "black" text
# invisible against the background. The Nord ramp makes the same choice.

[colors-dark]
background=282828
foreground=ebdbb2

selection-foreground=282828
selection-background=504945

regular0=3c3836
regular1=cc241d
regular2=98971a
regular3=d79921
regular4=458588
regular5=b16286
regular6=689d6a
regular7=a89984

bright0=928374
bright1=fb4934
bright2=b8bb26
bright3=fabd2f
bright4=83a598
bright5=d3869b
bright6=8ec07c
bright7=ebdbb2
```

- [ ] **Step 2: Rewrite `foot.ini`**

Delete the whole `[colors-dark]` block and its Nord comment. Add the include at the top of the file, after the header comment and **before** `[main]`:

```ini
# Palette. `colors.ini` is a symlink to colors-nord.ini or colors-gruvbox.ini;
# ~/.local/bin/theme flips it.
#
# foot has NO config-reload signal — SIGUSR1/SIGUSR2 only switch between the
# [colors-dark] and [colors-light] blocks that were loaded at startup. So a
# theme switch reaches foot only after `foot --server` restarts, which closes
# every open terminal. `theme --restart-terminals` does that on request.
include=~/.config/foot/colors.ini
```

- [ ] **Step 3: Validate both palettes**

```bash
cd ~/repos/dotfiles/foot/.config/foot
for pal in nord gruvbox; do
  ln -sfn "colors-$pal.ini" colors.ini
  foot --check-config -c foot.ini && echo "$pal OK"
done
ln -sfn colors-nord.ini colors.ini
```

Expected: `nord OK` and `gruvbox OK`, with **no** deprecation warnings. A warning about `[colors]` means the section header is wrong.

- [ ] **Step 4: Write the alacritty fragments**

`alacritty/.config/alacritty/colors-nord.toml`:

```toml
# Nord — alacritty's 16-colour ramp.
#
# Inlined rather than imported from ~/.config/alacritty/themes (the untracked
# alacritty-theme clone), so this package is self-contained: a fresh machine
# needs no clone for the colours to be right. Must stay in step with
# foot/.config/foot/colors-nord.ini.

[colors.primary]
background = "#2e3440"
foreground = "#d8dee9"

[colors.selection]
text       = "#2e3440"
background = "#4c566a"

[colors.normal]
black   = "#3b4252"
red     = "#bf616a"
green   = "#a3be8c"
yellow  = "#ebcb8b"
blue    = "#81a1c1"
magenta = "#b48ead"
cyan    = "#88c0d0"
white   = "#e5e9f0"

[colors.bright]
black   = "#4c566a"
red     = "#bf616a"
green   = "#a3be8c"
yellow  = "#ebcb8b"
blue    = "#81a1c1"
magenta = "#b48ead"
cyan    = "#8fbcbb"
white   = "#eceff4"
```

`colors-gruvbox.toml`: same tables using the Gruvbox ramp from Step 1's foot fragment (`background #282828`, `foreground #ebdbb2`, selection text `#282828` / background `#504945`, normal `#3c3836 #cc241d #98971a #d79921 #458588 #b16286 #689d6a #a89984`, bright `#928374 #fb4934 #b8bb26 #fabd2f #83a598 #d3869b #8ec07c #ebdbb2`).

- [ ] **Step 5: Rewrite `alacritty.toml`'s import**

Replace the `[general] import` block with:

```toml
[general]
import = [
    # `colors.toml` is a symlink to colors-nord.toml or colors-gruvbox.toml;
    # ~/.local/bin/theme flips it. Both live in this package, so alacritty no
    # longer depends on the untracked ~/.config/alacritty/themes clone for its
    # palette — the clone is only needed if you want other schemes to hand.
    "~/.config/alacritty/colors.toml"
]
```

- [ ] **Step 6: Deploy — note alacritty is unfolded, so `-R` is required**

```bash
cd ~/repos/dotfiles/alacritty/.config/alacritty
ln -sfn colors-nord.toml colors.toml
cd ~/repos/dotfiles
stow -n -v foot alacritty
stow -R foot alacritty
ls -la ~/.config/alacritty/colors.toml     # must exist; alacritty is unfolded
```

- [ ] **Step 7: Look at both terminals**

```bash
theme gruvbox
pkill -x foot; foot --server &          # foot needs the restart
```

Open a new terminal (`$mod+Return`) — gruvbox background. Run `alacritty` — same palette. Then `theme nord` and repeat.

- [ ] **Step 8: Commit**

```bash
cd ~/repos/dotfiles
git add foot alacritty
git commit -m "Move the terminal palettes into switchable fragments"
```

---

### Task 6: fuzzel and mako

**Files:**
- Create: `fuzzel/.config/fuzzel/colors-{nord,gruvbox}.ini`, `colors.ini` (symlink)
- Modify: `fuzzel/.config/fuzzel/fuzzel.ini`
- Create: `mako/.config/mako/colors-{nord,gruvbox}`, `colors` (symlink)
- Modify: `mako/.config/mako/config`

- [ ] **Step 1: Write the fuzzel fragments**

`fuzzel/.config/fuzzel/colors-nord.ini`:

```ini
# Nord — fuzzel's colours. Alpha is significant here: the launcher is
# translucent (background ...ee), everything else fully opaque (...ff).
#
# Included by fuzzel.ini via a `colors.ini` symlink that ~/.local/bin/theme
# flips. fuzzel reads its config at launch, so a switch applies to the next
# invocation with no reload needed.

[colors]
background=2e3440ee
text=d8dee9ff
placeholder=4c566aff
prompt=88c0d0ff
input=eceff4ff
match=ebcb8bff
selection-match=ebcb8bff
selection=434c5eff
selection-text=eceff4ff
counter=4c566aff
border=88c0d0ff
```

`colors-gruvbox.ini`: same keys, values `282828ee`, `ebdbb2ff`, `7c6f64ff`, `fabd2fff`, `fbf1c7ff`, `fe8019ff`, `fe8019ff`, `504945ff`, `fbf1c7ff`, `7c6f64ff`, `fabd2fff` in that order — i.e. `bg surface-less` roles: background=bg, text=fg, placeholder=muted, prompt=accent, input=fg_bright, match/selection-match=warning, selection=sel, selection-text=fg_bright, counter=muted, border=accent.

- [ ] **Step 2: Rewrite `fuzzel.ini`**

Delete the `[colors]` block and its Nord comment. Add at the top of the file, before any section:

```ini
# Palette. `colors.ini` is a symlink to colors-nord.ini or colors-gruvbox.ini;
# ~/.local/bin/theme flips it.
include=~/.config/fuzzel/colors.ini
```

- [ ] **Step 3: Validate both palettes**

```bash
cd ~/repos/dotfiles/fuzzel/.config/fuzzel
for pal in nord gruvbox; do
  ln -sfn "colors-$pal.ini" colors.ini
  fuzzel --check-config --config fuzzel.ini && echo "$pal OK"
done
ln -sfn colors-nord.ini colors.ini
```

Expected: `nord OK` and `gruvbox OK`.

- [ ] **Step 4: Write the mako fragments**

The file is `mako/.config/mako/colors-nord` — **no extension**, matching mako's own `config`:

```
# Nord — mako's colours.
#
# Included by config via a `colors` symlink that ~/.local/bin/theme flips.
# mako's include accepts criteria sections, so the per-urgency overrides live
# here too rather than being split across two files.
#
# surface body against fg text: one step up from the desktop background so
# notifications read as raised rather than as a hole in the wallpaper.

background-color=#3B4252
text-color=#D8DEE9
border-color=#88C0D0
progress-color=over #88C0D080

[urgency=low]
border-color=#4C566A
text-color=#8FBCBB

[urgency=normal]
border-color=#88C0D0

# Critical notifications never time out on their own.
[urgency=high]
border-color=#BF616A
text-color=#ECEFF4
ignore-timeout=1
```

`mako/.config/mako/colors-gruvbox`: same keys with `#3C3836`, `#EBDBB2`, `#FABD2F`, `over #FABD2F80`; low `#7C6F64` / `#8EC07C`; normal `#FABD2F`; high `#FB4934` / `#FBF1C7` with `ignore-timeout=1`.

- [ ] **Step 5: Rewrite `mako/config`**

Delete `background-color`, `text-color`, `border-color`, `progress-color` and all three `[urgency=…]` sections. Add after the `font=` line:

```
# Palette. `colors` is a symlink to colors-nord or colors-gruvbox;
# ~/.local/bin/theme flips it, then runs `makoctl reload` — mako is exec'd
# rather than exec_always'd in sway, so a sway reload does NOT restart it.
include=~/.config/mako/colors
```

Everything below the include (`width`, `icon-path`, `border-size`, `default-timeout`, …) is theme-independent and stays put. Keep the `icon-path` comment, correcting `papirus-folders -C nord` to `-C nordic` while you are in there — `nord` is rejected outright.

- [ ] **Step 6: Deploy and test both**

```bash
cd ~/repos/dotfiles/mako/.config/mako && ln -sfn colors-nord colors
cd ~/repos/dotfiles && stow -R fuzzel mako
makoctl reload
notify-send "Nord" "Body text and a cyan border"
notify-send -u critical "Critical" "Red border, never times out"
```

Expected: two notifications, the second red-bordered. Dismiss with `makoctl dismiss -a`.

- [ ] **Step 7: Switch and re-test**

```bash
theme gruvbox
notify-send "Gruvbox" "Yellow border now"
$mod+d      # press it: the launcher should be gruvbox
theme nord
```

- [ ] **Step 8: Commit**

```bash
cd ~/repos/dotfiles
git add fuzzel mako
git commit -m "Move fuzzel and mako colours into switchable fragments"
```

---

### Task 7: gtklock and nwg-drawer

**Files:**
- Create: `gtklock/.config/gtklock/colors-{nord,gruvbox}.css`, `colors.css` (symlink)
- Modify: `gtklock/.config/gtklock/style.css`, `gtklock/.config/gtklock/config.ini`
- Create: `nwg-drawer/.config/nwg-drawer/colors-{nord,gruvbox}.css`, `colors.css` (symlink)
- Modify: `nwg-drawer/.config/nwg-drawer/drawer.css`

**Interfaces:**
- Consumes: the same thirteen `@define-color` names as Task 4's waybar fragments. The fragment files are near-identical in content — that is intentional; each package must be self-contained because GTK CSS `@import` is relative to the importing file and cannot reach across packages.

- [ ] **Step 1: Create the CSS fragments**

Four files, each holding the same thirteen `@define-color` lines as the corresponding waybar fragment from Task 4 Step 1. Copy the waybar files wholesale, then rewrite each header comment to name its own application.

```bash
cd ~/repos/dotfiles
for pal in nord gruvbox; do
  cp "waybar/.config/waybar/colors-$pal.css" "gtklock/.config/gtklock/colors-$pal.css"
  cp "waybar/.config/waybar/colors-$pal.css" "nwg-drawer/.config/nwg-drawer/colors-$pal.css"
done
( cd gtklock/.config/gtklock    && ln -sfn colors-nord.css colors.css )
( cd nwg-drawer/.config/nwg-drawer && ln -sfn colors-nord.css colors.css )
```

The duplication is deliberate and unavoidable: GTK CSS `@import` resolves relative to the importing file, so it cannot reach into another stow package. Each package must carry its own copy. The `theme` script's role check (Task 3) only compares the sway `.env` and `.conf` pairs, so if you edit one of these four by hand, edit its counterpart too.

- [ ] **Step 2: Rewrite `gtklock/style.css`**

Replace the hardcoded values with roles. `rgba(…)` becomes `alpha(@role, f)`, which GTK CSS supports:

```css
/* gtklock — the lock screen ($mod+f1, and on idle/before-sleep).
 *
 * Palette: `colors.css` is a symlink to colors-nord.css or colors-gruvbox.css;
 * ~/.local/bin/theme flips it. gtklock reads its style at launch, so a switch
 * applies to the next lock with no reload needed.
 *
 * The background was a 22M image sitting in this config dir; it now lives in
 * ~/Pictures/wallpapers and this is a solid @bg, matching the desktop. */

@import url("colors.css");

* {
  border: none;
  text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.8)
}
window {
  background-image: none;
  background-color: @bg;
}
#clock-label {
  font-family: "JetBrainsMono Nerd Font";
  font-size: 64.0px;
  color: @fg_bright;
}
#unlock-button {
  background: none;
  background-color: alpha(@accent2, 0.4);
  border: 2px solid alpha(@accent, 0.5);
  border-radius: 10px;
  color: @fg_bright;
  padding: 4px;
}
#unlock-button:hover {
  background-color: alpha(@accent, 0.9);
  color: @bg;
}
#input-field {
  border-radius: 10px;
  background-color: alpha(@surface, 0.6);
  border: 2px solid alpha(@accent, 0.5);
  color: @fg_bright;
  padding-top: 5px;
  padding-bottom: 5px;
}
#input-field:focus {
  border: 2px solid @accent;
}
#powerbar-box button {
  background: none;
  background-color: alpha(@accent2, 0.4);
  border: 2px solid alpha(@accent, 0.5);
  border-radius: 10px;
  color: @fg_bright;
  padding: 4px;
}
#powerbar-box button:hover {
  background-color: alpha(@accent, 0.9);
  color: @bg;
}
#input-label {
  font-size: 0px;
}
#window-box infobar {
  background-color: transparent;
}
```

- [ ] **Step 3: Let gtklock inherit the GTK theme**

In `gtklock/.config/gtklock/config.ini`, delete the `gtk-theme=Nordic` line and replace it with:

```ini
# gtk-theme is deliberately unset: with no value, gtklock (a GTK app) resolves
# the theme from ~/.config/gtk-3.0/settings.ini like every other GTK app, which
# is what the theme switcher rewrites. Hardcoding it here would pin the lock
# screen to Nordic while the rest of the desktop switched.
```

- [ ] **Step 4: Rewrite `nwg-drawer/drawer.css`**

```css
/* nwg-drawer — the application grid on $mod+Shift+d.
 *
 * Palette: `colors.css` is a symlink to colors-nord.css or colors-gruvbox.css;
 * ~/.local/bin/theme flips it. nwg-drawer runs resident (-r), and sway's
 * exec_always re-execs it on reload, so the switch applies automatically. */

@import url("colors.css");

window {
    background-color: alpha(@bg, 0.9);
    color: @fg_bright;
    border-radius: 30px
}

/* search entry */
entry {
    box-shadow: 0 0 6px 5px @bg;
    background-color: alpha(@surface, 0.6);
    color: @fg_bright;
    border: 1px solid @muted
}

button, image {
    background-color: @surface;
    background: none;
    border: none;
    margin: 10px
}

button:hover {
    background-color: alpha(@accent, 0.3);
    box-shadow: 0 0 6px 5px @bg
}

/* in case you wanted to give category buttons a different look */
#category-button {
    margin: 0 0px 0 0px
}

#pinned-box {
    padding-bottom: 1px;
    border-bottom: 1px solid @muted
}

#files-box {
    padding: 1px;
    border: 1px solid @muted
}
```

- [ ] **Step 5: Verify both stylesheets parse under both palettes**

```bash
cd ~/repos/dotfiles
for f in gtklock/.config/gtklock/style.css nwg-drawer/.config/nwg-drawer/drawer.css; do
  d=$(dirname "$f")
  for pal in nord gruvbox; do
    ln -sfn "colors-$pal.css" "$d/colors.css"
    python3 - "$f" "$f:$pal" <<'EOF'
import sys, gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio
p = Gtk.CssProvider()
try:
    p.load_from_file(Gio.File.new_for_path(sys.argv[1])); print(f"{sys.argv[2]}: OK")
except Exception as e:
    print(f"{sys.argv[2]}: FAILED: {e}"); sys.exit(1)
EOF
  done
  ln -sfn colors-nord.css "$d/colors.css"
done
```

Expected: four `OK` lines.

- [ ] **Step 6: Deploy and look at both surfaces**

```bash
cd ~/repos/dotfiles && stow -R gtklock nwg-drawer && swaymsg reload
```

Press `$mod+Shift+d` — the drawer should look unchanged. Press `$mod+f1` and unlock — the lock screen should look unchanged. Then `theme gruvbox` and check both again.

- [ ] **Step 7: Commit**

```bash
cd ~/repos/dotfiles
git add gtklock nwg-drawer
git commit -m "Move gtklock and nwg-drawer to role-named switchable palettes"
```

---

### Task 8: The GTK stack

The only task that installs a package, and the only one where a value must be read off the system rather than copied from this plan.

**Files:**
- Create: `gtk/.config/gtk-3.0/settings-{nord,gruvbox}.ini`, `gtk-{nord,gruvbox}.css`
- Create: `gtk/.config/gtk-4.0/settings-{nord,gruvbox}.ini`, `gtk-{nord,gruvbox}.css`
- Create: `gtk/.gtkrc-2.0-{nord,gruvbox}`
- Create: `gtk/.config/xsettingsd/xsettingsd-{nord,gruvbox}.conf`
- Replace with symlinks: `gtk/.config/gtk-3.0/settings.ini`, `gtk-3.0/gtk.css`, `gtk-4.0/settings.ini`, `gtk-4.0/gtk.css`, `.gtkrc-2.0`, `xsettingsd/xsettingsd.conf`

**Interfaces:**
- Consumes: `GTK_THEME_NAME` from `sway/.config/sway/theme-gruvbox.env` — `Colloid-Yellow-Dark-Gruvbox`, in `~/.themes/`. Referred to below as `<GRUVBOX_GTK>`. Do not invent a value for it.

- [ ] **Step 1: Recover the Gruvbox GTK theme name**

Installed and recorded in Task 1 Step 0. Read it back rather than re-deriving it, and confirm it still matches what `theme-gruvbox.env` says:

```bash
GRUVBOX_GTK=$(grep -oP '(?<=^GTK_THEME_NAME=).*' ~/repos/dotfiles/sway/.config/sway/theme-gruvbox.env)
test -d "$HOME/.themes/$GRUVBOX_GTK/gtk-3.0" && echo "theme present: $GRUVBOX_GTK"
```

Note it lives in `~/.themes`, not `/usr/share/themes` — GTK searches both, but
anything you write about paths must say the right one.

Expected: the directory exists. If it does not, the Task 1 value was wrong — stop and report rather than guessing a replacement.

- [ ] **Step 2: Split the GTK3 settings**

`gtk/.config/gtk-3.0/settings-nord.ini` — the current `settings.ini` content verbatim, with this header:

```ini
# GTK3 settings, Nord. `settings.ini` is a symlink to this or to
# settings-gruvbox.ini; ~/.local/bin/theme flips it, and sway's
# scripts/import-gsettings pushes the values into gsettings on every reload.
#
# settings.ini has no include mechanism, so the whole file is switched. The
# non-colour half (fonts, hinting, toolbar) is duplicated into
# settings-gruvbox.ini — keep the two in step.
[Settings]
gtk-theme-name=Nordic
gtk-icon-theme-name=Papirus-Dark
gtk-font-name=Noto Sans 10
gtk-cursor-theme-name=Qogir-dark
gtk-cursor-theme-size=24
gtk-toolbar-style=GTK_TOOLBAR_BOTH_HORIZ
gtk-toolbar-icon-size=GTK_ICON_SIZE_LARGE_TOOLBAR
gtk-button-images=0
gtk-menu-images=0
gtk-enable-event-sounds=1
gtk-enable-input-feedback-sounds=0
gtk-xft-antialias=1
gtk-xft-hinting=1
gtk-xft-hintstyle=hintslight
gtk-xft-rgba=rgb
gtk-application-prefer-dark-theme=1
```

`settings-gruvbox.ini`: identical except `gtk-theme-name=<GRUVBOX_GTK from Step 1>`.

- [ ] **Step 3: Split the GTK3 user CSS**

`gtk/.config/gtk-3.0/gtk-nord.css` — the current `gtk.css` verbatim. `gtk-gruvbox.css`:

```css
/* GTK3 user overrides — loaded after the Gruvbox theme.
 *
 * Kept deliberately small. The theme does the work; this only pins the accent
 * so selections match sway's focus border exactly. */

@define-color theme_selected_bg_color #FABD2F;
@define-color theme_selected_fg_color #282828;

selection {
  background-color: #FABD2F;
  color: #282828;
}
```

- [ ] **Step 4: Split the GTK4 settings and libadwaita CSS**

`gtk-4.0/settings-nord.ini` and `settings-gruvbox.ini`: current `gtk-4.0/settings.ini` with the respective `gtk-theme-name`.

`gtk-4.0/gtk-nord.css`: the current `gtk-4.0/gtk.css` verbatim.

`gtk-4.0/gtk-gruvbox.css`: same structure, Gruvbox values:

```css
/* GTK4 / libadwaita user overrides, Gruvbox Dark.
 *
 * This is the file that actually matters for modern apps. libadwaita apps
 * ignore gtk-theme-name entirely, and would render in stock Adwaita dark
 * against an otherwise Gruvbox desktop. Redefining libadwaita's named colours
 * here is the supported way to reach them.
 *
 * CAUTION: nwg-look's "export-gtk4-symlinks" replaces this file with a symlink
 * into /usr/share/themes/. Check `ls -la ~/.config/gtk-4.0/` and re-run
 * `stow -R gtk` if it has been clobbered. */

@define-color window_bg_color        #282828;
@define-color window_fg_color        #EBDBB2;
@define-color view_bg_color          #3C3836;
@define-color view_fg_color          #EBDBB2;
@define-color headerbar_bg_color     #3C3836;
@define-color headerbar_fg_color     #FBF1C7;
@define-color sidebar_bg_color       #282828;
@define-color sidebar_fg_color       #EBDBB2;
@define-color card_bg_color          #3C3836;
@define-color card_fg_color          #EBDBB2;
@define-color popover_bg_color       #3C3836;
@define-color popover_fg_color       #EBDBB2;
@define-color dialog_bg_color        #3C3836;
@define-color dialog_fg_color        #EBDBB2;

@define-color accent_bg_color        #FABD2F;
@define-color accent_fg_color        #282828;
@define-color accent_color           #FABD2F;

@define-color destructive_bg_color   #FB4934;
@define-color destructive_fg_color   #FBF1C7;
@define-color destructive_color      #FB4934;

@define-color success_bg_color       #B8BB26;
@define-color success_fg_color       #282828;
@define-color success_color          #B8BB26;

@define-color warning_bg_color       #FE8019;
@define-color warning_fg_color       #282828;
@define-color warning_color          #FE8019;

@define-color error_bg_color         #FB4934;
@define-color error_fg_color         #FBF1C7;
@define-color error_color            #FB4934;

@define-color theme_selected_bg_color #FABD2F;
@define-color theme_selected_fg_color #282828;
```

- [ ] **Step 5: Split GTK2 and drop the dangling include**

`gtk/.gtkrc-2.0-nord` — the current `.gtkrc-2.0`, **with the `include "/home/xinye/.gtkrc-2.0.mine"` line deleted** (that file does not exist; the include has always been dangling) and this header:

```
# DO NOT EDIT DIRECTLY — this file is switched by ~/.local/bin/theme.
# ~/.gtkrc-2.0 is a symlink to this or to .gtkrc-2.0-gruvbox.
#
# nwg-look will overwrite ~/.gtkrc-2.0 (destroying the symlink) if you ever
# click Apply. See PLAYBOOK.md §9.1; `stow -R gtk` repairs it.
gtk-theme-name="Nordic"
gtk-icon-theme-name="Papirus-Dark"
gtk-font-name="Noto Sans 10"
gtk-cursor-theme-name="Qogir-dark"
gtk-cursor-theme-size=24
gtk-toolbar-style=GTK_TOOLBAR_BOTH_HORIZ
gtk-toolbar-icon-size=GTK_ICON_SIZE_LARGE_TOOLBAR
gtk-button-images=0
gtk-menu-images=0
gtk-enable-event-sounds=1
gtk-enable-input-feedback-sounds=0
gtk-xft-antialias=1
gtk-xft-hinting=1
gtk-xft-hintstyle="hintslight"
gtk-xft-rgba="rgb"
```

`.gtkrc-2.0-gruvbox`: identical with `gtk-theme-name="<GRUVBOX_GTK>"`.

- [ ] **Step 6: Track xsettingsd**

```bash
cp ~/.config/xsettingsd/xsettingsd.conf ~/repos/dotfiles/gtk/.config/xsettingsd/xsettingsd-nord.conf
cat ~/repos/dotfiles/gtk/.config/xsettingsd/xsettingsd-nord.conf
```

Read what it contains, then create `xsettingsd-gruvbox.conf` with the same keys and the Gruvbox theme name substituted for `Nordic`. Add a header comment to both noting they are switched by `theme`, and that xsettingsd serves XWayland clients (PLAYBOOK §2.2).

- [ ] **Step 7: Replace the originals with symlinks**

```bash
cd ~/repos/dotfiles/gtk
rm .config/gtk-3.0/settings.ini .config/gtk-3.0/gtk.css \
   .config/gtk-4.0/settings.ini .config/gtk-4.0/gtk.css .gtkrc-2.0
( cd .config/gtk-3.0 && ln -sfn settings-nord.ini settings.ini && ln -sfn gtk-nord.css gtk.css )
( cd .config/gtk-4.0 && ln -sfn settings-nord.ini settings.ini && ln -sfn gtk-nord.css gtk.css )
ln -sfn .gtkrc-2.0-nord .gtkrc-2.0
( cd .config/xsettingsd && ln -sfn xsettingsd-nord.conf xsettingsd.conf )
```

- [ ] **Step 8: Deploy — `gtk` is unfolded, so `-R` is mandatory**

```bash
cd ~/repos/dotfiles
stow -n -v gtk
stow -R gtk
ls -la ~/.config/gtk-3.0/ ~/.gtkrc-2.0 ~/.config/xsettingsd/
cat ~/.config/gtk-3.0/settings.ini | head -3      # must resolve through two symlinks
```

Expected: `gtk-theme-name=Nordic` printed, proving the chained symlink resolves.

- [ ] **Step 9: Confirm gsettings still gets the right values**

```bash
swaymsg reload
gsettings get org.gnome.desktop.interface gtk-theme       # 'Nordic'
gsettings get org.gnome.desktop.interface color-scheme    # 'prefer-dark'
```

- [ ] **Step 10: Switch and verify GTK follows**

```bash
theme gruvbox
gsettings get org.gnome.desktop.interface gtk-theme       # the Gruvbox name
thunar -q; thunar &                                        # a GTK3 app, freshly started
```

Per PLAYBOOK §9.9, only *newly started* GTK apps pick up the change. Launch a GTK4/libadwaita app too and confirm it is gruvbox rather than stock Adwaita dark.

- [ ] **Step 11: Commit**

```bash
cd ~/repos/dotfiles
git add gtk
git commit -m "Switch the whole GTK stack per theme, and track xsettingsd"
```

---

### Task 9: vim and LS_COLORS

Two gap fixes. `dircolors` is theme-independent by construction — using only the 16 ANSI slots means it follows whichever terminal palette is active.

**Files:**
- Create: `vim/.vim/colorscheme-{nord,gruvbox}.vim`, `colorscheme.vim` (symlink)
- Modify: `vim/.vimrc`
- Create: `bash/.config/dircolors`
- Modify: `bash/.bashrc`

- [ ] **Step 1: Clone the two colorschemes**

They are installed the same way lightline already is — a plain clone into vim's native package directory.

```bash
git clone https://github.com/arcticicestudio/nord-vim ~/.vim/pack/plugins/start/nord-vim
git clone https://github.com/morhetz/gruvbox ~/.vim/pack/plugins/start/gruvbox
ls ~/.vim/pack/plugins/start/
```

Expected: `gruvbox`, `lightline`, `nord-vim`.

- [ ] **Step 2: Write the two colorscheme files**

`vim/.vim/colorscheme-nord.vim`:

```vim
" Nord — vim and lightline colours.
"
" Sourced from ~/.vimrc. `colorscheme.vim` is a symlink to this file or to
" colorscheme-gruvbox.vim; ~/.local/bin/theme flips it. Already-running vim
" instances keep their colours; new ones pick this up.
"
" Requires ~/.vim/pack/plugins/start/nord-vim (see PLAYBOOK.md §8).

set termguicolors
colorscheme nord
let g:lightline = { 'colorscheme': 'nord' }
```

`vim/.vim/colorscheme-gruvbox.vim`:

```vim
" Gruvbox Dark — vim and lightline colours.
"
" Requires ~/.vim/pack/plugins/start/gruvbox (see PLAYBOOK.md §8).
" `background=dark` must be set before the colorscheme: gruvbox reads it to
" choose between its light and dark variants, and defaults to light.

set termguicolors
set background=dark
colorscheme gruvbox
let g:lightline = { 'colorscheme': 'gruvbox' }
```

- [ ] **Step 3: Source it from `.vimrc`**

In `vim/.vimrc`, under the existing `""==== Colours ====` heading, after `syntax enable`:

```vim
" Palette. colorscheme.vim is a symlink switched by ~/.local/bin/theme.
" Guarded so a machine without the clones from PLAYBOOK.md §8 still starts vim
" instead of erroring on every launch.
if filereadable(expand('~/.vim/colorscheme.vim'))
  source ~/.vim/colorscheme.vim
endif
```

`g:lightline` must be set before lightline loads, and vim loads `pack/*/start/*` plugins *after* sourcing `.vimrc`, so this ordering is correct.

- [ ] **Step 4: Write the dircolors file**

`bash/.config/dircolors`:

```
# LS_COLORS — evaluated from ~/.bashrc.
#
# THEME-INDEPENDENT BY CONSTRUCTION. Every colour below is one of the 16 ANSI
# slots, never a 256-colour index or a truecolor escape. The terminal supplies
# the actual hexes from foot/alacritty's palette, which the theme switcher
# already changes — so this file themes itself and needs no per-theme variant.
#
# Regenerate the stock version for reference with: dircolors -p

RESET 0
NORMAL 00
FILE 00
DIR 01;34
LINK 01;36
ORPHAN 40;31;01
MISSING 40;31;01
FIFO 40;33
SOCK 01;35
DOOR 01;35
BLK 40;33;01
CHR 40;33;01
EXEC 01;32
SETUID 37;41
SETGID 30;43
CAPABILITY 30;41
STICKY_OTHER_WRITABLE 30;42
OTHER_WRITABLE 34;42
STICKY 37;44

# Archives
.tar 01;31
.tgz 01;31
.zip 01;31
.gz 01;31
.bz2 01;31
.xz 01;31
.zst 01;31
.7z 01;31
.rar 01;31

# Images and video
.jpg 01;35
.jpeg 01;35
.png 01;35
.gif 01;35
.svg 01;35
.webp 01;35
.mp4 01;35
.mkv 01;35
.webm 01;35

# Audio
.mp3 00;36
.flac 00;36
.ogg 00;36
.wav 00;36

# Documents
.pdf 00;33
.md 00;33
.txt 00;33
```

- [ ] **Step 5: Wire it into `.bashrc`**

Add near the other tool activations in `bash/.bashrc`:

```sh
# LS_COLORS. The file uses only the 16 ANSI slots, so it follows whichever
# terminal palette the theme switcher has set — no per-theme variant needed.
if [ -r "$HOME/.config/dircolors" ]; then
    eval "$(dircolors -b "$HOME/.config/dircolors")"
fi
```

- [ ] **Step 6: Deploy — `vim` is unfolded (`~/.vim` holds the plugin clones)**

```bash
cd ~/repos/dotfiles/vim/.vim && ln -sfn colorscheme-nord.vim colorscheme.vim
cd ~/repos/dotfiles
stow -n -v vim bash
stow -R vim bash
ls -la ~/.vim/colorscheme.vim        # must exist
```

- [ ] **Step 7: Test both**

```bash
vim ~/repos/dotfiles/README.md       # Nord colours, lightline in Nord; :q
bash -lc 'ls -la ~ | head'           # directories readable blue, not dark-on-dark
theme gruvbox
vim ~/repos/dotfiles/README.md       # gruvbox now; :q
theme nord
```

- [ ] **Step 8: Commit**

```bash
cd ~/repos/dotfiles
git add vim bash
git commit -m "Theme vim per palette, and add ANSI-only LS_COLORS"
```

---

### Task 10: Cursor and slurp

The last two gap fixes.

**Files:**
- Create: `gtk/.icons/default/index.theme`
- Modify: `sway/.config/sway/config.d/theme` — add `seat * xcursor_theme`
- Modify: `sway/.config/sway/scripts/screenshot_display.sh`, `screenshot_window.sh`
- Modify: `waybar/.config/waybar/scripts/keyhint.sh`

- [ ] **Step 1: Add the cursor index.theme**

`gtk/.icons/default/index.theme`:

```ini
# Cursor theme for the desktop and for XWayland clients.
#
# GTK apps get their cursor from gtk-cursor-theme-name in settings.ini, but
# nothing else does — the sway cursor and XWayland clients read this file and
# `seat * xcursor_theme` in sway's config.d/theme. Without it the cursor over
# the desktop is the default, not Qogir-dark, which is why the theme appeared
# to apply only inside GTK windows.
#
# Theme-independent: Qogir-dark is neutral grey and reads against both palettes.
[Icon Theme]
Name=Default
Comment=Default cursor theme
Inherits=Qogir-dark
```

- [ ] **Step 2: Set the sway cursor**

In `sway/.config/sway/config.d/theme`, near the font declaration:

```
# Cursor. Must match gtk-cursor-theme-name in the gtk package's settings.ini
# and ~/.icons/default/index.theme — those three cover GTK apps, the sway
# cursor, and XWayland clients respectively. Deliberately NOT per-theme:
# Qogir-dark is neutral grey and works against both palettes.
seat * xcursor_theme Qogir-dark 24
```

- [ ] **Step 3: Give slurp the palette**

Read the two screenshot scripts first:

```bash
cat ~/repos/dotfiles/sway/.config/sway/scripts/screenshot_display.sh
cat ~/repos/dotfiles/sway/.config/sway/scripts/screenshot_window.sh
grep -rn slurp ~/repos/dotfiles/sway/.config/sway/
```

In every script that invokes `slurp`, add near the top:

```sh
# Palette, so the selection box matches the active theme. theme.env is a
# symlink switched by ~/.local/bin/theme.
. "$HOME/.config/sway/theme.env"
```

and give each `slurp` invocation:

```sh
slurp -b "${BG}cc" -c "$ACCENT" -s "${ACCENT}22" -B "${BG}66"
```

`-b` background, `-c` selection border, `-s` selection fill, `-B` the dimmed area outside it. slurp takes `#RRGGBBAA`, and the role variables already carry the leading `#`.

- [ ] **Step 4: Give keyhint.sh the palette**

In `waybar/.config/waybar/scripts/keyhint.sh`, replace `header="#88C0D0"` with:

```sh
# Section headers use the accent role. theme.env is a symlink switched by
# ~/.local/bin/theme, so this follows the active palette.
. "$HOME/.config/sway/theme.env"
header="$ACCENT"
```

- [ ] **Step 5: Validate and deploy**

```bash
cd ~/repos/dotfiles
sh -n sway/.config/sway/scripts/screenshot_display.sh
sh -n sway/.config/sway/scripts/screenshot_window.sh
sh -n waybar/.config/waybar/scripts/keyhint.sh
stow -R sway gtk waybar
sway --validate -c ~/.config/sway/config
swaymsg reload
pgrep -xc swayidle        # 1
```

- [ ] **Step 6: Test each surface**

Press `Print` — the selection box should be drawn in the accent colour. Click the waybar keyboard-layout module — section headers in the accent colour. Move the cursor over the empty desktop — it should be the Qogir-dark pointer, not the default X arrow. Then `theme gruvbox` and re-check `Print` and the keyhint.

- [ ] **Step 7: Commit**

```bash
cd ~/repos/dotfiles
git add sway gtk waybar
git commit -m "Apply the cursor theme outside GTK, and theme the slurp selection"
```

---

### Task 11: Documentation

**Files:**
- Modify: `PLAYBOOK.md`
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/setup.html`

- [ ] **Step 1: Rework `PLAYBOOK.md`**

- **Title and intro:** off "Sway + Nord", onto two palettes.
- **§2.3 "Where the palette lives":** rewrite. It currently says "There is no central colour file". That is no longer true — say instead that each package carries its own pair of fragments plus a symlink, that `waybar/.config/waybar/colors-*.css` is the canonical listing of the thirteen roles, and that `sway/.config/sway/theme-*.env` is the shell-readable copy.
- **§3:** retitle to "The palettes". Keep the Nord swatch block, add the Gruvbox one, and make §3.1's role table three columns — Role / Nord / Gruvbox — matching this plan's Global Constraints. Keep §3.2 ("Nord is not Nordic") unchanged; add the parallel gruvbox trap that papirus-folders has no gruvbox colour and `yellow` is the stand-in.
- **New section, "Switching":** the fragment/symlink model, why stow is *not* used for switching (it would unfold every themed package), the `theme` command and its flags, the keybinding, what does not update immediately (foot, running GTK apps), and the fact that the symlinks are committed.
- **§4.2:** add `gruvbox-gtk-theme-git`, and the two vim colorscheme clones.
- **§5.2:** add a paragraph explaining that the fold column is *unchanged* by the theming work, and why — the symlinks live inside each package, so nothing is ever written into a folded target from outside.
- **§8:** add the two vim clones and the `gruvbox-gtk-theme-git` install. Note the `stow bin` step.
- **§9, new gotchas:**
  - Role names replaced `@nordN` in waybar's CSS; a hex in an application config is now a bug.
  - GTK CSS renders an undefined `@name` as **black, with no error** — this is why `theme` refuses to switch when the two palettes define different roles.
  - foot has no config-reload signal; `SIGUSR1`/`SIGUSR2` only pick between `[colors-dark]` and `[colors-light]`. Record the rejected trick (parking the second palette in `[colors-light]`) and why, so it is not re-proposed.
  - foot's plain `[colors]` section is deprecated; fragments must use `[colors-dark]`.
  - waybar's `include` gives precedence to the **including** file, so a module defined in `config` silently wins over the fragment.
- **§9.2:** add the observation that `exec_always nwg-drawer -r` and `exec_always foot --server` lack the `pkill` prefix the section prescribes, and that neither leaks because both refuse to double-start.
- **§10:** new troubleshooting rows — a surface stuck on the old palette after switching (foot server / running GTK apps); a widget rendering black (undefined role); `theme` reporting a missing fragment; folder icons not matching (papirus-folders skipped, needs sudo).
- **§10 verification sweep:** add `readlink ~/repos/dotfiles/sway/.config/sway/theme.env` and the folding check from Task 3 Step 4.

- [ ] **Step 2: Update `README.md`**

Add `bin` to the package table. Rewrite the theming paragraph around the two palettes and the `theme` command, linking to the playbook's new switching section.

**Required, not optional** — `CLAUDE.md` mandates that a new package is added to the README table *and* to `PLAYBOOK.md` §5.2 with its fold decision and the reason. `bin` is the new package this plan introduces, and it was flagged in review as missing both. Its §5.2 row is:

| `bin` | **No** | `~/.local/bin` is a real directory holding untracked binaries — `claude`, `coderabbit` (104 MB), `herdr` (22 MB), plus mise/starship shims. Folding would pull all of it into the repo. A newly added file therefore needs `stow -R bin`. |

- [ ] **Step 3: Update `CLAUDE.md`**

Under Conventions, add:

```markdown
- **Two palettes.** Colours come from the thirteen-role table in `PLAYBOOK.md` §3.1, which has a
  Nord column and a Gruvbox column. Adding a colour means adding **both** values under a role
  name — never inline a hex in an application config. The roles are declared in
  `waybar/.config/waybar/colors-{nord,gruvbox}.css` (GTK), `sway/.config/sway/colors-*.conf`
  (sway) and `sway/.config/sway/theme-*.env` (shell).
- **Switching is `theme <name>`** (`bin/.local/bin/theme`, bound to `$mod+Shift+t`). It flips the
  `colors.*` symlinks inside each package. Never switch by editing configs, and never introduce a
  theme stow package — a second package writing into a folded target would unfold it.
- A new themed file must be named `<base>-nord.<ext>` / `<base>-gruvbox.<ext>` with a
  `<base>.<ext>` symlink, or `theme` will not find it.
```

Under Gotchas, add the foot `[colors-dark]` requirement, waybar's include precedence, and that GTK CSS renders an undefined `@name` as black without erroring.

- [ ] **Step 4: Update `docs/setup.html`**

Read the existing file to match its structure and styling, then bring it in step with the playbook: the `gruvbox-gtk-theme-git` and vim-clone install steps, the `stow bin` step, and a new section for switching. Keep the copy buttons and the progress persistence that already exist.

- [ ] **Step 5: Verify the docs against reality**

Every command quoted in the docs must be one that was actually run during this plan. Spot-check:

```bash
cd ~/repos/dotfiles
theme            # nord
theme gruvbox && theme nord
for p in sway waybar foot mako fuzzel gtklock nwg-drawer; do
  printf '%-12s ' "$p"
  if [ -L ~/.config/$p ]; then echo "folded (symlink)"; else echo "UNFOLDED (real dir)"; fi
done
```

Expected: seven lines, every one `folded (symlink)` — folding intact, which is the claim §5.2 now makes.

- [ ] **Step 6: Commit**

```bash
cd ~/repos/dotfiles
git add PLAYBOOK.md README.md CLAUDE.md docs/setup.html
git commit -m "Document the two-palette model and the theme switcher"
```

---

## Final verification

- [ ] Switch to Gruvbox, then log out and back in, so every daemon starts fresh under the new palette. Walk the full surface list from PLAYBOOK §10: `$mod+d`, `notify-send test`, `$mod+Shift+d`, the waybar clock tooltip, `$mod+f1`, thunar, a GTK4 app, `$mod+Return`, `Print`, `vim`, `ls`.
- [ ] Switch back to Nord and confirm the desktop is indistinguishable from how it looked before this work started — the Nord path is a refactor, not a redesign. The two known-deliberate exceptions: the waybar calendar's weekday colour moves nord9 → nord7, and the slurp selection box is now themed where it previously was not.
- [ ] `pgrep -xc swayidle` is 1.
- [ ] `git status` is clean.
