# Dotfile collection

My small collection, managed with [GNU Stow](https://www.gnu.org/software/stow/).

Each top-level directory is a stow *package* whose contents mirror the layout under
`$HOME`. Stowing a package symlinks its files into place:

| Package      | Links to                                                        |
|--------------|-----------------------------------------------------------------|
| `bash`       | `~/.bashrc`, `~/.config/dircolors`                              |
| `vim`        | `~/.vimrc`, `~/.vim/colorscheme*.vim`                           |
| `nvim`       | `~/.config/nvim/` — `init.lua`, `highlights.lua`, `statusline.lua`, `colorscheme*.lua` |
| `bin`        | `~/.local/bin/theme` — the palette switcher                     |
| `alacritty`  | `~/.config/alacritty/alacritty.toml`                            |
| `foot`       | `~/.config/foot/foot.ini`                                       |
| `starship`   | `~/.config/starship.toml`                                       |
| `claude`     | `~/.claude/statusline.py` — the Claude Code status line          |
| `htop`       | `~/.config/htop/htoprc`                                         |
| `waybar`     | `~/.config/waybar/` — `config`, `style.css`, `scripts/`         |
| `sway`       | `~/.config/sway/` — `config`, `config.d/`, `scripts/`           |
| `kanshi`     | `~/.config/kanshi/config`                                       |
| `gtk`        | `~/.config/gtk-3.0/`, `~/.config/gtk-4.0/`, `~/.config/xsettingsd/`, `~/.gtkrc-2.0`, `~/.icons/default/` |
| `mako`       | `~/.config/mako/config`                                         |
| `fuzzel`     | `~/.config/fuzzel/fuzzel.ini`                                   |
| `nwg-drawer` | `~/.config/nwg-drawer/drawer.css`                               |
| `gtklock`    | `~/.config/gtklock/`                                            |
| `htop`       | `~/.config/htop/htoprc`                                         |

## Theming

The desktop carries **two palettes** — [Nord](https://www.nordtheme.com/) and
[Gruvbox Dark](https://github.com/morhetz/gruvbox) — and switches between them with one keystroke:

```sh
theme            # print the active palette
theme gruvbox    # switch
theme toggle     # the other one — bound to $mod+Shift+t
```

No colour is written as a hex in an application config. Every one is a **role** (`bg`, `accent`,
`critical`, …) defined twice, once per palette, in a pair of fragments inside the package that owns
it. The active palette is one word in `.theme` at the repo root; from it `theme` points 18
symlinks at the right fragments and reloads sway, waybar, mako and gsettings. It touches sway,
waybar, foot, alacritty, fuzzel, mako, gtklock, nwg-drawer, vim, nvim and the whole GTK stack.

**Switching is an operational change, not a repo one.** `.theme` and the 18 pointers are
gitignored, so changing palette leaves `git status` completely untouched.

Stow is deliberately *not* how the switch happens — a second package writing into `~/.config/waybar`
would unfold it. See **[PLAYBOOK.md §3.3](PLAYBOOK.md)** for the mechanism, the flags, and what does
not update immediately (open terminals, running GTK apps).

* **[PLAYBOOK.md](PLAYBOOK.md)** — the full technical manual: architecture, the two palettes and
  their role conventions, the switching model, every deviation from stock EndeavourOS and why, the
  keybinding reference, and the gotchas. Read this one.
* **[docs/setup.html](docs/setup.html)** — the same setup as an interactive checklist with copy
  buttons and saved progress. Open it in a browser when rebuilding on a new machine. It opens with
  a diagrammed map of how the construct fits together — the two kinds of symlink, folded vs
  unfolded, and what sway owns at runtime — and phase 09 explains the switcher itself, in a
  technical and a plain-language register you can toggle between.

`theme` is the only thing here with enough logic to get wrong twice, so it has tests. Run them after
touching it — they use a throwaway `$HOME` and stubbed `swaymsg`, so the live desktop is untouched:

```sh
sh tests/theme_test.sh
```

## Setup

```sh
git clone https://github.com/xinye1/dotfiles.git
cd dotfiles
sh bin/.local/bin/theme nord --no-icons         # or gruvbox — creates the theme pointers
stow bash vim nvim alacritty foot starship htop bin  # or one at a time: stow nvim
```

**Run `theme` before `stow`.** The theme pointers are gitignored, so a fresh clone does not have
them; `theme` creates them. The unfolded packages link file-by-file, so pointers created after
`stow` would need `stow -R` to appear.

`bin` puts `theme` on `PATH`. It is **not** folded — `~/.local/bin` is a real directory holding
untracked binaries — so a script added to the package later needs `stow -R bin` before it appears.

For the full desktop, see [PLAYBOOK.md](PLAYBOOK.md) — the sway/gtk packages need packages
installed and stock configs moved aside first.

`.stowrc` in this repo sets `--target=~`, so stow links into `$HOME` regardless of
where the repo is cloned. Without it, stow would default to the repo's *parent*
directory — which is only correct if the repo lives directly in `$HOME`.

A fresh Arch install already has a `~/.bashrc` (copied from `/etc/skel`), and stow
refuses to replace a real file with a symlink. Move it aside first:

```sh
mv ~/.bashrc ~/.bashrc.bak && stow bash
```

Useful flags:

```sh
stow -n -v vim    # dry run, show what would be linked
stow -D vim       # unstow (remove the symlinks)
stow -R vim       # restow (unstow then stow, picks up deletions)
```

## Adding a package

Create a directory named after the package, then recreate the path *relative to
`$HOME`* inside it. For example, to manage `~/.config/foo/config.yml`:

```
foo/.config/foo/config.yml
```

A file placed at `foo/config.yml` would end up at `~/config.yml` instead.

## Dependencies

Both shell dependencies are activated behind a `command -v` guard in `bash/.bashrc`,
so the package works on a machine where neither is installed yet.

* [starship](https://starship.rs) — the prompt (`starship/.config/starship.toml`).
  Without the binary, the plain `PS1` set just above the guard stays in effect.
  `sudo pacman -S starship`.
* [mise](https://mise.jdx.dev) — applies a repo's `.mise.toml` tool pins on `cd`,
  which also makes starship's language modules report the project's interpreter
  rather than the ambient one. `sudo pacman -S mise`.
* [alacritty-theme](https://github.com/alacritty/alacritty-theme) cloned to
  `~/.config/alacritty/themes` — **optional now.** `alacritty.toml` used to import
  `themes/themes/nord.toml` from this clone; it imports its own
  `colors.toml` fragment instead, so the repo describes the colours on its own.
  Clone it only if you want other schemes to hand — and note it ships
  `nord.toml`, `nordic.toml`, `nordfox.toml` and `nord_light.toml`, three of
  which are *not* Nord.
* [foot](https://codeberg.org/dnkl/foot) — the terminal sway launches on
  `mod+Return`. `~/.config/sway/config.d/default` sets `$term footclient` and
  `autostart_applications` execs `foot --server`, so the daemon must be running
  for the binding to work. `sudo pacman -S foot`. Wayland-only, hence keeping
  `alacritty` alongside it. foot has no config-reload signal, so it is the one
  surface that keeps its old colours after `theme` — see PLAYBOOK §9.11.
* vim plugins, all cloned into `~/.vim/pack/plugins/start/`. `.vimrc` guards the
  colorscheme `source` with `filereadable`, so vim still starts without them:

  ```sh
  git clone https://github.com/itchyny/lightline.vim ~/.vim/pack/plugins/start/lightline
  git clone https://github.com/arcticicestudio/nord-vim ~/.vim/pack/plugins/start/nord-vim
  git clone https://github.com/morhetz/gruvbox   ~/.vim/pack/plugins/start/gruvbox
  ```
* **nvim plugins need no step here.** `init.lua` uses `vim.pack`, Neovim 0.12's built-in
  manager, so lualine and nvim-web-devicons install themselves on first launch — that one
  launch needs network; offline, nvim opens with the built-in statusline instead. The plugin
  code lands in `~/.local/share/nvim/`, and their revisions are pinned in the tracked
  `nvim/.config/nvim/nvim-pack-lock.json`, so a fresh clone gets the same versions.
  `:lua vim.pack.update()` updates them, and unlike a theme switch it **does** dirty the
  tree — the lockfile diff is the record of the bump, and is meant to be committed.
  nvim's colourschemes are not plugins at all: both are written from the thirteen roles,
  and lualine is themed from them too.

### Desktop packages

Needed by the `sway`, `waybar`, `gtk`, `mako`, `fuzzel` and `gtklock` packages, on top of what
EndeavourOS Sway Community Edition already installs:

```sh
sudo pacman -S --needed ttf-jetbrains-mono-nerd kanshi papirus-icon-theme
yay -S nordic-theme papirus-folders
sudo papirus-folders -C nordic -t Papirus-Dark   # one-off, recolours the folder icons

# The Gruvbox GTK theme — installed by hand into ~/.themes, not from the AUR
git clone https://github.com/vinceliuice/Colloid-gtk-theme /tmp/colloid
cd /tmp/colloid && ./install.sh -d ~/.themes -c dark -s standard -t yellow --tweaks gruvbox
```

* `nordic-theme` — the Nord GTK2/3/4 theme. Nothing in the base install provides one. Note the
  theme is genuinely called *Nordic*; there is no GTK theme called "Nord".
* `Colloid-Yellow-Dark-Gruvbox` — the counterpart for the Gruvbox palette. The AUR
  `gruvbox-gtk-theme-git` was rejected: it pulls in `gtk-engine-murrine`, which wants a
  from-source `gtk2` build. **Never pass `-l`/`--libadwaita` to that installer** — it overwrites
  `~/.config/gtk-4.0/gtk.css`, which this repo owns.
* `ttf-jetbrains-mono-nerd` — the *patched* font. The base install ships only
  `ttf-nerd-fonts-symbols`, so waybar's icons render via a fontconfig fallback rather than by
  configuration. `fc-match "JetBrainsMono Nerd Font"` must not return NotoSansMono.
* `papirus-icon-theme` + `papirus-folders` — icons for mako, fuzzel and GTK. `theme` re-runs
  `papirus-folders` per palette (`nordic` for Nord, `yellow` for Gruvbox — it has no gruvbox
  colour). It writes into `/usr/share/icons`, so it is the one step needing `sudo` on every
  switch; `theme --no-icons` skips it.
* `kanshi` — display hotplug profiles (`kanshi` package in this repo).

