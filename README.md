# Dotfile collection

My small collection, managed with [GNU Stow](https://www.gnu.org/software/stow/).

Each top-level directory is a stow *package* whose contents mirror the layout under
`$HOME`. Stowing a package symlinks its files into place:

| Package     | Links to                              |
|-------------|---------------------------------------|
| `bash`      | `~/.bashrc`                           |
| `vim`       | `~/.vimrc`                            |
| `alacritty` | `~/.config/alacritty/alacritty.toml`  |
| `starship`  | `~/.config/starship.toml`             |
| `waybar`    | `~/.config/waybar/config`             |

## Setup

```sh
git clone https://github.com/xinye1/dotfiles.git
cd dotfiles
stow bash vim alacritty starship      # or one package at a time: stow vim
```

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
  `themes/themes/nordic.toml` from it. Without it alacritty still starts, but logs
  a config error and falls back to the default colours.
* [lightline](https://github.com/itchyny/lightline.vim) - vim' status bar.
  Run `git clone https://github.com/itchyny/lightline.vim ~/.vim/pack/plugins/start/lightline`
  to clone it.

