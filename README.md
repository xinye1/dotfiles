# Dotfile collection

My small collection, managed with [GNU Stow](https://www.gnu.org/software/stow/).

Each top-level directory is a stow *package* whose contents mirror the layout under
`$HOME`. Stowing a package symlinks its files into place:

| Package      | Links to                                                        |
|--------------|-----------------------------------------------------------------|
| `bash`       | `~/.bashrc`                                                     |
| `vim`        | `~/.vimrc`                                                      |
| `alacritty`  | `~/.config/alacritty/alacritty.toml`                            |
| `foot`       | `~/.config/foot/foot.ini`                                       |
| `starship`   | `~/.config/starship.toml`                                       |
| `waybar`     | `~/.config/waybar/` — `config`, `style.css`, `scripts/`         |
| `sway`       | `~/.config/sway/` — `config`, `config.d/`, `scripts/`           |
| `kanshi`     | `~/.config/kanshi/config`                                       |
| `gtk`        | `~/.config/gtk-3.0/`, `~/.config/gtk-4.0/`, `~/.gtkrc-2.0`      |
| `mako`       | `~/.config/mako/config`                                         |
| `fuzzel`     | `~/.config/fuzzel/fuzzel.ini`                                   |
| `nwg-drawer` | `~/.config/nwg-drawer/drawer.css`                               |
| `gtklock`    | `~/.config/gtklock/`                                            |

The desktop is themed with [Nord](https://www.nordtheme.com/) throughout.

* **[PLAYBOOK.md](PLAYBOOK.md)** — the full technical manual: architecture, the palette and its role
  conventions, every deviation from stock EndeavourOS and why, the keybinding reference, and the
  gotchas. Read this one.
* **[docs/setup.html](docs/setup.html)** — the same setup as an interactive checklist with copy
  buttons and saved progress. Open it in a browser when rebuilding on a new machine.

## Setup

```sh
git clone https://github.com/xinye1/dotfiles.git
cd dotfiles
stow bash vim alacritty foot starship  # or one package at a time: stow vim
```

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
  `~/.config/alacritty/themes` — `alacritty.toml` imports
  `themes/themes/nord.toml` from it. Without it alacritty still starts, but logs
  a config error and falls back to the default colours. Note the clone also ships
  `nordic.toml`, `nordfox.toml` and `nord_light.toml` — all different schemes.
* [foot](https://codeberg.org/dnkl/foot) — the terminal sway launches on
  `mod+Return`. `~/.config/sway/config.d/default` sets `$term footclient` and
  `autostart_applications` execs `foot --server`, so the daemon must be running
  for the binding to work. `sudo pacman -S foot`. The `foot` package here is
  self-contained — unlike `alacritty`, the Nordic palette is inlined rather than
  imported from an untracked clone. Wayland-only, hence keeping `alacritty`.
* [lightline](https://github.com/itchyny/lightline.vim) - vim' status bar.
  Run `git clone https://github.com/itchyny/lightline.vim ~/.vim/pack/plugins/start/lightline`
  to clone it.

### Desktop packages

Needed by the `sway`, `waybar`, `gtk`, `mako`, `fuzzel` and `gtklock` packages, on top of what
EndeavourOS Sway Community Edition already installs:

```sh
sudo pacman -S --needed ttf-jetbrains-mono-nerd kanshi papirus-icon-theme
yay -S nordic-theme papirus-folders-nord
papirus-folders -C nord -t Papirus-Dark   # one-off, recolours the folder icons
```

* `nordic-theme` — the Nord GTK2/3/4 theme. Nothing in the base install provides one.
* `ttf-jetbrains-mono-nerd` — the *patched* font. The base install ships only
  `ttf-nerd-fonts-symbols`, so waybar's icons render via a fontconfig fallback rather than by
  configuration. `fc-match "JetBrainsMono Nerd Font"` must not return NotoSansMono.
* `papirus-icon-theme` + `papirus-folders-nord` — icons for mako, fuzzel and GTK.
* `kanshi` — display hotplug profiles (`kanshi` package in this repo).

