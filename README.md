# Dotfile collection

My small collection, managed with [GNU Stow](https://www.gnu.org/software/stow/).

Each top-level directory is a stow *package* whose contents mirror the layout under
`$HOME`. Stowing a package symlinks its files into place:

| Package     | Links to                              |
|-------------|---------------------------------------|
| `vim`       | `~/.vimrc`                            |
| `alacritty` | `~/.config/alacritty/alacritty.toml`  |

## Setup

```sh
git clone https://github.com/xinye1/dotfiles.git
cd dotfiles
stow vim alacritty      # or one package at a time: stow vim
```

`.stowrc` in this repo sets `--target=~`, so stow links into `$HOME` regardless of
where the repo is cloned. Without it, stow would default to the repo's *parent*
directory — which is only correct if the repo lives directly in `$HOME`.

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

* [alacritty-theme](https://github.com/alacritty/alacritty-theme) cloned to
  `~/.config/alacritty/themes` — `alacritty.toml` imports
  `themes/themes/gruvbox_material_hard_dark.toml` from it. Without it alacritty still
  starts, but logs a config error and falls back to the default colours.
