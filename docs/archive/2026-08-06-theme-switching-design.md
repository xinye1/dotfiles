# Two-palette theming: Nord ↔ Gruvbox

Design for making the desktop switch between Nord and Gruvbox Dark with one command, without
losing stow's tree folding and without inventing a templating layer.

Status: approved design, not yet implemented.

---

## 1. Problem

The desktop is themed Nord across eleven applications. Every application parses its own config
format, so the palette is duplicated by necessity and each hex is inlined where it is used
(PLAYBOOK §2.3). Adding a second palette this way would mean maintaining two copies of eleven
configs, and switching would mean editing all of them.

Four surfaces are also unthemed or half-themed today, and any second palette has to cover them
too or the gap doubles.

## 2. Approach

**Colour moves out of each config into a fragment; the config includes a theme-neutral name;
that name is a symlink checked into the repo; a script flips the symlinks.**

Every colour-bearing format in this setup supports an include. This was verified against the
installed man pages rather than assumed:

| Format | Directive | Verified |
|---|---|---|
| mako | `include=` | `man 5 mako` line 29 |
| fuzzel | `include` | `man 5 fuzzel.ini` |
| foot | `include` | `man 5 foot.ini` line 101 |
| waybar (JSON) | `include` | `man 5 waybar` |
| sway | `include` | long-standing |
| GTK / waybar / gtklock / nwg-drawer CSS | `@import` | GTK CSS |
| alacritty | `import` | TOML |
| GTK2 gtkrc | `include` | already used by `.gtkrc-2.0` |

Only GTK3/GTK4 `settings.ini` have no include mechanism. Those are symlinked whole.

### 2.1 Shape, per package

```
waybar/.config/waybar/
├── style.css            @import url("colors.css");
├── colors-nord.css
├── colors-gruvbox.css
└── colors.css       ->  colors-nord.css        ← the only thing that moves
```

The symlink lives **inside the package**, so it is one more ordinary tracked file. Nothing is
added to a package directory from outside it.

### 2.2 Why not a second stow package

The rejected alternative was `theme-nord/` and `theme-gruvbox/` packages owning the fragments,
switched with `stow -D`/`stow`.

It works — verified — but stow's tree unfolding means a second package placing a file into
`~/.config/waybar` **converts that directory from a folded symlink into a real directory with
per-file symlinks.** Every themed package would have lost folding, so every subsequently added
file would have needed `stow -R`. That inverts most of PLAYBOOK §5.2 and was judged too high a
price.

The in-repo symlink approach was verified to preserve folding exactly:

```
$ ls -la ~/.config/ | grep waybar
waybar -> ../../repo/waybar/.config/waybar      # still folded, after the flip
```

Chained symlinks (`~/.config/gtk-3.0/gtk.css` → repo `gtk.css` → `gtk-nord.css`) resolve
correctly for unfolded packages too, because the second link is relative to its own directory
inside the repo.

**Stow is not involved in switching at all.** It deploys packages exactly as it does today.

### 2.3 The symlinks are committed

A fresh clone plus `stow` yields a working themed desktop with no extra step, and the repo
records which theme is active. Switching leaves ~10 typechange entries in `git status` until
committed; `theme` prints a reminder.

---

## 3. The palettes and the role table

PLAYBOOK §3.1's role table becomes the contract between the two palettes. Both fragments define
the **same thirteen role names**; no config refers to `nord8` or `yellow` directly.

| Role | Nord | Gruvbox Dark |
|---|---|---|
| Background | `nord0` `#2E3440` | `bg0` `#282828` |
| Raised surface | `nord1` `#3B4252` | `bg1` `#3C3836` |
| Selection | `nord2` `#434C5E` | `bg2` `#504945` |
| Inactive / muted | `nord3` `#4C566A` | `bg4` `#7C6F64` |
| Foreground | `nord4` `#D8DEE9` | `fg1` `#EBDBB2` |
| Bright foreground | `nord6` `#ECEFF4` | `fg0` `#FBF1C7` |
| **Focus / accent** | `nord8` `#88C0D0` | `yellow` `#FABD2F` |
| Secondary accent | `nord10` `#5E81AC` | `orange` `#D65D0E` |
| **Urgent / critical** | `nord11` `#BF616A` | `red` `#FB4934` |
| Warning | `nord13` `#EBCB8B` | `orange` `#FE8019` |
| Success | `nord14` `#A3BE8C` | `green` `#B8BB26` |
| Split indicator | `nord7` `#8FBCBB` | `aqua` `#8EC07C` |
| Desktop background | `#272B33` (darkened nord0) | `bg0_h` `#1D2021` |

Two notes:

- Gruvbox's desktop background needs no invented hex. PLAYBOOK §6.1 documents `#272B33` as the
  one deliberate off-palette value, chosen so the desktop sits a shade darker than the window
  background. Gruvbox ships exactly that as `bg0_h`, its canonical "hard" background.
- Focus is gruvbox's warm yellow, its signature colour. Warning is orange, one hue step away.
  They are closer than Nord's cyan/yellow pair, so warning states read as *hotter* rather than
  *different*. This was chosen deliberately over an aqua accent that would have mirrored Nord's
  hue relationships more exactly but looked less like gruvbox.

### 3.1 Terminal 16-colour ramp (Gruvbox Dark)

```
regular0 #282828   regular1 #CC241D   regular2 #98971A   regular3 #D79921
regular4 #458588   regular5 #B16286   regular6 #689D6A   regular7 #A89984
bright0  #928374   bright1  #FB4934   bright2  #B8BB26   bright3  #FABD2F
bright4  #83A598   bright5  #D3869B   bright6  #8EC07C   bright7  #EBDBB2
```

### 3.2 Naming: role names replace `@nord0`

`waybar/style.css` currently declares `@define-color nord0 … nord15` and refers to `@nord8`
throughout. A gruvbox fragment defining `@nord0` as `#282828` would be absurd, so the CSS is
refactored to role names — `@bg`, `@surface`, `@sel`, `@muted`, `@fg`, `@fg_bright`, `@accent`,
`@accent2`, `@critical`, `@warning`, `@success`.

This is the largest single diff in the implementation and it is the point of the whole design:
the role table stops being documentation and becomes the literal API.

---

## 4. Per-package changes

Fragment naming is uniform: `colors-<theme>.<ext>` plus a `colors.<ext>` symlink, except where
noted.

| Package | Config change | Fragments | Fold state |
|---|---|---|---|
| `waybar` | `style.css` → `@import url("colors.css")`, all `@nordN` → role names. `config` clock module extracted. | `colors-*.css`, `colors-*.json` | folded, unchanged |
| `foot` | `[colors-dark]` block → `include=` | `colors-*.ini` | folded, unchanged |
| `fuzzel` | `[colors]` block → `include` | `colors-*.ini` | folded, unchanged |
| `mako` | colour lines + `[urgency=*]` → `include=` | `colors-*` | folded, unchanged |
| `sway` | `client.*` + `output * bg` → `include` | `colors-*.conf`, `theme-*.env` | folded, unchanged |
| `gtklock` | `style.css` → `@import`; drop `gtk-theme=Nordic` so it inherits from `settings.ini` — if it does not inherit, fall back to symlinking `config.ini` whole | `colors-*.css` | folded, unchanged |
| `nwg-drawer` | `drawer.css` → `@import`, hexes → role names | `colors-*.css` | folded, unchanged |
| `alacritty` | `import` now points at an in-repo fragment | `colors-*.toml` | unfolded, unchanged |
| `gtk` | `settings.ini` ×2, `gtk.css` ×2, `.gtkrc-2.0`, `xsettingsd.conf` symlinked whole or `@import`ed | `*-nord.*`, `*-gruvbox.*` | unfolded, unchanged |
| `vim` | `.vimrc` sources `~/.vim/colorscheme.vim` | `colorscheme-*.vim` | unfolded (see below) |
| `bash` | `.bashrc` evaluates a dircolors file | none — theme-independent | unchanged |
| `bin` | **new package**, `~/.local/bin/theme` | — | new |

`~/.vim` already holds the untracked lightline clone, so it is unfolded for the same reason
`alacritty` is. Adding `colorscheme.vim` needs `stow -R vim`. Existing rule, not a new cost.

### 4.1 Shell-readable palette

Scripts cannot parse CSS. `sway/.config/sway/theme-<theme>.env` exports the thirteen roles as
shell variables, symlinked to `theme.env`, and is sourced by:

- `sway/scripts/screenshot_*.sh` — for slurp's selection colours
- `waybar/scripts/keyhint.sh` — replaces the hardcoded `header="#88C0D0"`
- `bin/theme` — for `PAPIRUS_FOLDER`

### 4.2 foot does not retheme live

`man 1 foot` documents no config-reload signal; `SIGUSR1`/`SIGUSR2` only switch between the
`[colors-dark]` and `[colors-light]` blocks loaded at startup. So foot's new palette applies to
terminals started after `foot --server` restarts.

An earlier draft exploited this by parking Nord in `[colors-dark]` and Gruvbox in
`[colors-light]` — both dark palettes, the section names being mere labels — giving instant live
retheming of every open terminal via `pkill -USR1 foot`. **Rejected:** it was the sole source of
asymmetry in the design, it caps the setup at exactly two themes, and it makes the config
actively misleading to read.

`theme` therefore prints that foot is pending, and accepts `--restart-terminals` to apply it
immediately at the cost of every open shell.

---

## 5. Gap fixes

Six gaps found in the Nord coverage, all fixed for both palettes.

| Gap | Fix | Theme-dependent? |
|---|---|---|
| `.vimrc` sets no `colorscheme`; lightline has no scheme | per-theme `~/.vim/colorscheme.vim` setting both. `nord-vim` and `gruvbox` cloned alongside lightline | yes |
| `LS_COLORS` unset — `ls` uses built-in defaults | `~/.config/dircolors` using **only the 16 ANSI slots**, evaluated from `.bashrc` | **no** — ANSI slots already flip with the terminal palette |
| `~/.config/xsettingsd/xsettingsd.conf` untracked | tracked in `gtk`, symlinked per theme | yes |
| `.gtkrc-2.0` includes non-existent `~/.gtkrc-2.0.mine` | line dropped; the whole file is symlinked per theme instead | — |
| Cursor theme applied only inside GTK apps | `seat * xcursor_theme Qogir-dark 24` in sway + `~/.icons/default/index.theme` | **no** — neutral grey suits both |
| `slurp` draws a stock selection box | screenshot scripts source `theme.env` and pass `-b/-c/-s` | yes |

`starship` needs no change: it already uses ANSI colour names, so it follows the terminal
palette for free. This is worth stating in the docs, because it looks like an omission.

Not fixed, and why:

- **greetd's login screen** — system config outside `$HOME`, already documented as unstowable
  (PLAYBOOK §6.4).
- **Qt** — no Qt apps in this setup; PLAYBOOK §4.3 already records the decision.
- **swappy** — GTK3, so it inherits the active GTK theme. No config file exists to track.

Also noted, not fixed: `exec_always nwg-drawer -r` and `exec_always foot --server` lack the
`pkill` prefix PLAYBOOK §9.2 says every `exec_always` daemon needs. Neither leaks — both refuse
to double-start — so this is a documentation inconsistency, recorded in §9.2 rather than
"fixed" with a `pkill` that would add a real restart on every reload.

---

## 6. The switcher

`bin/.local/bin/theme`, on `$PATH` via `.bashrc`'s existing `~/.local/bin` entry.

```
theme                      print the active theme
theme nord | gruvbox       switch
theme toggle               switch to the other one   ($mod+Shift+t)
  --restart-terminals      also restart foot --server
  --no-icons               skip the papirus-folders step (avoids the sudo prompt)
```

**Active theme detection:** `readlink waybar/.config/waybar/colors.css` → `colors-nord.css`.
No state file, so nothing can drift out of sync with reality.

**Sequence:**

1. Validate the requested theme; resolve the current one. No-op early if they match.
2. Self-check: confirm both fragments define the same set of role names, and abort before
   touching anything if they do not. See §9 for why this specific check.
3. Flip every symlink with `ln -sfn`, relative targets, inside the repo.
4. `swaymsg reload` — picks up sway colours, restarts waybar, re-runs `import-gsettings`
   (pushing the new GTK/icon/cursor names to gsettings), re-execs nwg-drawer.
5. `makoctl reload` — mako is `exec`, not `exec_always`, so a sway reload does not restart it.
6. `sudo papirus-folders -C <nordic|yellow> -t Papirus-Dark`, **only when the colour differs**.
   Skipped with a warning when non-interactive or `--no-icons`.
7. Report what will not have changed yet: foot's open terminals, and already-running GTK apps
   (PLAYBOOK §9.9).

**Idempotent.** Running `theme nord` twice is a no-op that still succeeds.

**Failure handling:** the symlink flip is the only step that mutates the repo, and it happens
before any reload. If a reload step fails the desktop is in a consistent state — the config is
correct and a manual `swaymsg reload` finishes the job. `theme` reports the failing step and
exits non-zero rather than continuing silently.

### 6.1 papirus-folders is the one root step

It writes into `/usr/share/icons`, so it cannot be stowed and needs `sudo` on each switch.
Folding it into `theme` means it stops being a thing to remember. Gruvbox uses papirus-folders'
`yellow`; Nord uses `nordic` (which, per PLAYBOOK §3.2, is what papirus-folders calls Nord).

---

## 7. New dependencies

| Package | Source | Why |
|---|---|---|
| `gruvbox-gtk-theme-git` | **AUR** | The Gruvbox counterpart to `nordic-theme`. Without it GTK3 chrome falls back to stock Adwaita dark while everything else is Gruvbox. The exact installed theme name must be read off `ls /usr/share/themes` after installing and used verbatim in `settings-gruvbox.ini`. |
| `nord-vim`, `gruvbox` | git clone | Vim colorschemes, cloned into `~/.vim/pack/plugins/start/` exactly as lightline already is. Both are always installed; `colorscheme.vim` selects. |

---

## 8. Documentation

| File | Change |
|---|---|
| `PLAYBOOK.md` | Retitled off "Sway + Nord". §3 becomes both palettes against the shared role table. New section on the fragment/symlink model and the switcher. §4 manifest, §8 post-install updated. §5.2's fold table gains a line explaining why folding survived. New gotchas: role names replaced `@nordN`; foot does not retheme live; the rejected `[colors-light]` trick, recorded so it is not re-proposed. §10 troubleshooting rows for a half-switched desktop. |
| `docs/setup.html` | Tracks the playbook — same content as a checklist with copy buttons and persisted progress. |
| `README.md` | Package table gains `bin`; theming section rewritten around the two palettes. |
| `CLAUDE.md` | Conventions: adding a colour means adding **both** palettes' values under a role name; never inline a hex; the switcher is the only supported way to change theme. |

---

## 9. Verification

No build, no tests. Per package, before `stow`: `stow -n -v <pkg>`.

**Structural:**

```sh
ls -la ~/.config | grep -E 'waybar|foot|mako|fuzzel|sway|gtklock|nwg-drawer'
        # every one still a SYMLINK — folding preserved, the core claim of this design
readlink ~/.config/waybar/colors.css      # tracks the active theme
```

**Per switch,** run `theme gruvbox` then `theme nord` and confirm each surface returns:

```sh
sway --validate -c ~/.config/sway/config     # before any reload
pgrep -xc swayidle                            # still exactly 1 after two reloads
grep -c . ~/.config/gtk-3.0/settings.ini     # resolves through the chained symlink
gsettings get org.gnome.desktop.interface gtk-theme
```

Then trigger each themed surface by hand, as PLAYBOOK §10 already prescribes: `$mod+d`,
`notify-send test`, `$mod+Shift+d`, the waybar clock tooltip, `$mod+f1`, thunar, a GTK4 app,
`$mod+Return`, `Print`, `vim`, `ls` in a fresh shell.

**The specific regression to watch for:** a role name referenced by a config but defined in only
one of the two fragments. GTK CSS silently renders an undefined `@name` as black. Both fragments
must define all thirteen roles; a `theme` self-check comparing the defined names across the two
files is cheap insurance and is step 2 of the switcher (§6).
