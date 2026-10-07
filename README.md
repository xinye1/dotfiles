# dotfiles

A Sway desktop on Arch, carrying two palettes — [Nord](https://www.nordtheme.com/) and
[Gruvbox](https://github.com/morhetz/gruvbox) — switchable with one command. Managed with
[GNU Stow](https://www.gnu.org/software/stow/).

```sh
git clone git@github.com:xinye1/dotfiles.git ~/repos/dotfiles
cd ~/repos/dotfiles
sudo pacman -S --needed $(cat packages.txt)   # the desktop and every tool a config here invokes
yay -S --needed $(cat packages-aur.txt)       # google-chrome
./setup.sh gruvbox                  # or nord
sh tests/check_consumers.sh         # once the desktop is up: asks the live apps
```

`setup.sh` is this quickstart made executable, in the one order that works: the fold-guard
`mkdir`s of PLAYBOOK §5.2 (on a fresh `$HOME` the unfolded packages' target dirs don't exist yet,
and stow would fold them — pulling every later plugin clone and installed binary into the repo),
`theme` before `stow`, the `/etc/skel` `~/.bashrc` move, then every package — gated on a `stow -n`
dry run, so existing configs stop it *before* anything is linked — and the sandboxed tests.
Re-running it is always safe; it manages nothing.

Full desktop, including the steps `setup.sh` cannot do — system packages, the default browser: **[PLAYBOOK.md](PLAYBOOK.md)** §4 and §8.

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

**Generated files are disposable, and named so you can tell.** Anything matching `*.gen.*` — or a
bare `*.gen`, which is what mako's `colors.gen` is, because mako's `include=` names the file with
no suffix at all — is a build artefact. Editing one is pointless: the next switch overwrites it.
That is what lets `.gitignore` be a glob instead of the twenty-two hand-maintained paths it used to
be, and what makes "did switching dirty the tree?" a question with a permanent answer of no. One
file cannot carry the marker, because yazi reads its theme at a hardcoded name and takes no include;
it is listed in `.gitignore`, next to the reason.

**Nothing is clever that could be obvious.** Stow does the linking; `setup.sh` only sequences the
documented steps and would change nothing if you typed them from PLAYBOOK §8 instead. `theme`
renders and reloads; it does not manage state beyond one word in
`$XDG_STATE_HOME/theme/palette`. The one genuinely
surprising rule — a file that cannot carry the `.gen` marker — is written down in `.gitignore` next
to the entry itself, because a rule you have to remember is a rule that will be broken.

What this costs, stated plainly, because a reader deserves it up front:

- You cannot theme one application differently from the rest without adding a role.
- GTK apps are not palette-tinted at all: they run plain Adwaita dark under both palettes, the
  trade taken on 2026-09-28 for six fewer templates, two fewer theme installs and a switch that
  never needs `sudo` (PLAYBOOK §2.2).
- A palette switch is a render, not a symlink flip, so it rewrites every rendered file rather than relinking them.
- `theme` must run **before** `stow` on a fresh clone (`setup.sh` encodes the order), and after
  adding a themed file to `yazi` — the one unfolded package that carries a
  template. See PLAYBOOK §5.2.
- Theming needs Python 3.11+ (for `tomllib`). It was `sh`; rendering needs a parser.

## Packages

Each top-level directory is a stow *package* whose contents mirror the layout under `$HOME`.

| Package | Links to |
|---|---|
| `bash` | `~/.bashrc`, `~/.config/dircolors` |
| `nvim` | `~/.config/nvim/` — `init.lua`, `highlights.lua`, `statusline.lua` |
| `bin` | `~/.local/bin/theme` — the palette renderer; `herdr-session-backup`; `tp-backup`, `tp-backup-ssd` |
| `claude` | `~/.claude/statusline.py` — the Claude Code status line |
| `herdr` | `~/.config/herdr/config.toml`, `local-plugins/attention/` — the agent multiplexer and its blocked-agent alerts |
| `kitty` | `~/.config/kitty/kitty.conf` — **the terminal**; ported from the retired `foot` package |
| `tmux` | `~/.config/tmux/` — `tmux.conf`, `colors.gen.conf`, `scripts/` |
| `starship` | `~/.config/starship.toml` |
| `htop` | `~/.config/htop/htoprc` |
| `yazi` | `~/.config/yazi/` — `yazi.toml`, `keymap.toml`, `theme.toml` |
| `waybar` | `~/.config/waybar/` — `config`, `style.css`, `scripts/` |
| `sway` | `~/.config/sway/` — `config`, `config.d/`, `scripts/` |
| `kanshi` | `~/.config/kanshi/config` |
| `gtk` | `~/.config/gtk-3.0/settings.ini`, `gtk-4.0/settings.ini`, `~/.icons/` — static, plain Adwaita dark |
| `mako` | `~/.config/mako/config` |
| `fuzzel` | `~/.config/fuzzel/fuzzel.ini` |

**The lock screen has no row of its own.** It is swaylock, which is configured entirely by the
flags in `sway/.config/sway/scripts/lock.sh` — a file in the `sway` package, not a package of its
own. swaylock does read `~/.config/swaylock/config` if one exists; deliberately none does, because
a config file could not derive its colours from the active palette and the script can (PLAYBOOK
§4.3, §9.13).

It locks over the solid **`$desktop`** colour — the field the desktop itself shows — and never
touches the network: a lock that waits on a socket is a lock that does not happen. It used to pick
a random palette-matched wallpaper from a ~320 MB cache that `walls-sync` downloaded; both retired
on 2026-09-28 (PLAYBOOK §9.25).

`docs/` and `tests/` are **not** packages and must never be named in a `stow` command — `tests/…`
would install to `~/tests/…`. `systemd-system/` mirrors the root filesystem (`/etc/systemd/system`,
`/etc/udev/rules.d`, `/usr/local/bin`) rather than `$HOME`, so it isn't stow-managed either —
`setup.sh` excludes it and `sudo systemd-system/deploy.sh` installs it instead, root-owned
throughout (PLAYBOOK §5.2). It carries the Jellyfin state dump and the never-sleep-on-AC inhibitor
this machine's server role depends on.

`windows/` is not a package either: it is for the **Windows host of a WSL machine**, where the
Claude Code sessions run in WSL and there is no waybar. `windows/claude-usage/` puts the claude
widget's limits, countdowns and token charts in the Windows notification area — a tray icon with
the worst percent, a hover summary, a click-open panel, toasts at 70/90/100% — fed by the same
`claude_usage.py` (`--json`). From inside WSL:

```sh
python3 windows/claude-usage/install.py              # install / update (re-run after a pull)
python3 windows/claude-usage/install.py --status     # also --start, --stop, --uninstall
```

Every operational command is in [`windows/claude-usage/README.md`](windows/claude-usage/README.md).

It needs nothing installed on Windows (Windows PowerShell 5.1 and WinForms ship with it), and it
never starts WSL on its own: while the distro is stopped it shows the last snapshot, greyed
(PLAYBOOK §9.31).

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
