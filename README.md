# dotfiles

A Sway desktop on Arch, carrying two palettes — [Nord](https://www.nordtheme.com/) and
[Gruvbox](https://github.com/morhetz/gruvbox) — switchable with one command. Managed with
[GNU Stow](https://www.gnu.org/software/stow/).

```sh
git clone git@github.com:xinye1/dotfiles.git ~/repos/dotfiles
cd ~/repos/dotfiles
./setup.sh gruvbox                  # or nord
sh tests/check_consumers.sh         # once the desktop is up: asks the live apps
```

`setup.sh` is this quickstart made executable, in the one order that works: the fold-guard
`mkdir`s of PLAYBOOK §5.2 (on a fresh `$HOME` the unfolded packages' target dirs don't exist yet,
and stow would fold them — pulling every later plugin clone and installed binary into the repo),
`theme` before `stow`, the `/etc/skel` `~/.bashrc` move, then every package — gated on a `stow -n`
dry run, so existing configs stop it *before* anything is linked — and the sandboxed tests.
Re-running it is always safe; it manages nothing.

Full desktop, including the steps `setup.sh` cannot do — system packages, GTK themes, vim plugin
clones, the papirus tint: **[PLAYBOOK.md](PLAYBOOK.md)** §4 and §8.

## The intention

This repo is optimised for **being understood six months later**, not for having every knob. Where
those two conflict, granularity loses. Three commitments follow from that, and most of the design is
downstream of them.

**One source of truth for every colour.** `palettes.toml` holds both palettes. Nothing else in the
repo contains a literal hex — a test enforces it. Each themed file is a template of `{{role}}`
placeholders that `theme` renders. The cost is that you cannot hand-tune one application's blue:
you add or change a *role*, and it moves everywhere that role is used. That is the point. The
desktop previously drifted into four incompatible palettes precisely because each config was
themed by hand.

**Generated files are disposable, and named so you can tell.** Anything matching `*.gen.*` is a
build artefact. Editing one is pointless — the next switch overwrites it. This is what lets
`.gitignore` be a glob instead of the twenty-two hand-maintained paths it used to be, and what
makes "did switching dirty the tree?" a question with a permanent answer of no. Seven files cannot
carry the marker, because GTK, xsettingsd and yazi each read a config at a hardcoded name and take
no include; those are listed one by one in `.gitignore`, next to the reason.

**Nothing is clever that could be obvious.** Stow does the linking; `setup.sh` only sequences the
documented steps and would change nothing if you typed them from PLAYBOOK §8 instead. `theme`
renders and reloads; it does not manage state beyond one word in
`$XDG_STATE_HOME/theme/palette`. The one genuinely
surprising rule — seven files that cannot carry the `.gen` marker — is written down in
`.gitignore` next to the entries themselves, because a rule you have to remember is a rule that
will be broken.

What this costs, stated plainly, because a reader deserves it up front:

- You cannot theme one application differently from the rest without adding a role.
- A palette switch is a render, not a symlink flip, so it writes ~18 files rather than relinking 18.
- `theme` must run **before** `stow` on a fresh clone (`setup.sh` encodes the order), and after
  adding a themed file to `gtk`, `alacritty`, `vim` or `yazi` — the unfolded packages that carry
  templates. See PLAYBOOK §5.2.
- Theming needs Python 3.11+ (for `tomllib`). It was `sh`; rendering needs a parser.

## Packages

Each top-level directory is a stow *package* whose contents mirror the layout under `$HOME`.

| Package | Links to |
|---|---|
| `bash` | `~/.bashrc`, `~/.config/dircolors` |
| `vim` | `~/.vimrc`, `~/.vim/colorscheme.gen.vim` |
| `nvim` | `~/.config/nvim/` — `init.lua`, `highlights.lua`, `statusline.lua` |
| `bin` | `~/.local/bin/theme` — the palette renderer |
| `claude` | `~/.claude/statusline.py` — the Claude Code status line |
| `alacritty` | `~/.config/alacritty/alacritty.toml` |
| `foot` | `~/.config/foot/foot.ini` — standalone fallback, still themed |
| `kitty` | `~/.config/kitty/kitty.conf` — **the default terminal**; a port of `foot` |
| `tmux` | `~/.config/tmux/` — `tmux.conf`, `colors.gen.conf`, `scripts/` |
| `starship` | `~/.config/starship.toml` |
| `htop` | `~/.config/htop/htoprc` |
| `yazi` | `~/.config/yazi/` — `yazi.toml`, `keymap.toml`, `theme.toml` |
| `waybar` | `~/.config/waybar/` — `config`, `style.css`, `scripts/` |
| `sway` | `~/.config/sway/` — `config`, `config.d/`, `scripts/` |
| `kanshi` | `~/.config/kanshi/config` |
| `gtk` | `~/.config/gtk-3.0/`, `gtk-4.0/`, `xsettingsd/`, `~/.gtkrc-2.0` |
| `mako` | `~/.config/mako/config` |
| `fuzzel` | `~/.config/fuzzel/fuzzel.ini` |
| `nwg-drawer` | `~/.config/nwg-drawer/drawer.css` |
| `gtklock` | `~/.config/gtklock/` |

`docs/` and `tests/` are **not** packages and must never be named in a `stow` command — `tests/…`
would install to `~/tests/…`.

`.stowrc` pins `--target=~`. Without it stow targets the repo's *parent*, which is wrong here and
fails silently: stow exits 0 having linked to the wrong place. Diagnose by checking where the link
landed, never by exit code.

## Switching palettes

```sh
theme              # re-render the current palette
theme nord         # switch
theme --list       # what is available
```

Switching is an operational change, never a repo change. The active palette is one word in
`$XDG_STATE_HOME/theme/palette` (default `~/.local/state/theme/palette`) — outside the repo, because
it is state about this machine rather than configuration — and every file `theme` writes is
gitignored. If a switch ever dirties `git status`, something has broken the naming scheme;
`tests/theme_test.sh` asserts it.

## Adding a colour

1. Add the role to **both** palettes in `palettes.toml`. They must define identical keys; `theme`
   refuses to render otherwise.
2. Use `{{your_role}}` in the relevant `*.tmpl`.
3. `theme` and look at it.

Never inline a hex. A role defined in one palette and not the other used to render as silent black
in GTK CSS; now it is a named error at render time, which is the whole reason the table exists.

## Adding a package

Create a directory named after the package, then recreate the path *relative to `$HOME`* inside it:

```
foo/.config/foo/config.yml      ->  ~/.config/foo/config.yml
foo/config.yml                  ->  ~/config.yml          (probably not what you meant)
```

Then add it to the table above, and to PLAYBOOK §5.2 with its fold decision.
