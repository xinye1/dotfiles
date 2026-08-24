# dotfiles

GNU Stow-managed. Each top-level dir is a package; contents mirror the layout under `$HOME`.
`PLAYBOOK.md` is the single reference — every §ref below points into it. These one-liners are
triggers, not the full story: read the named section before working in its area.

## Gotchas

- Repo lives at `~/repos/dotfiles`, **not** `$HOME`. `.stowrc` pins `--target=~`; don't remove it
  or run stow from elsewhere. Stow exits 0 even when it links to the wrong place — diagnose with
  `readlink`/`ls -la`, never by exit code (§5.1, §9.5).
- **Folded vs unfolded** decides whether a new file in a package appears without `stow -R`. Check
  with `[ -L ~/.config/<pkg> ]`, never `ls | grep` — the grep passes exactly when things are fine
  (§5.2, which also has each package's fold decision). Never fold a dir a tool writes into;
  `setup.sh` pre-creates the must-stay-unfolded targets on a fresh machine.
- **nwg-look clobbers the `gtk` package** — it rewrites `settings.ini`, `.gtkrc-2.0`, xsettingsd
  and replaces the libadwaita `gtk-4.0/gtk.css`. After ever opening it: `git status`, then
  `stow -R gtk`. It is never needed at runtime — `settings.ini` is the source of truth and
  `import-gsettings` pushes it on every reload (§9.1, §2.2).
- sway: `exec_always` starting a daemon needs `sh -c 'pkill -x <name>; exec <name>'` — the `pkill`
  or it leaks one process per reload, **and** the `sh -c` wrapper because an unquoted `;` on an
  exec line is split at startup (not at reload), so the daemon never starts at login while every
  `swaymsg reload` check reports 1. `exec` only runs at startup so a fix using it can't be tested
  with `swaymsg reload`; `exec export FOO=bar` does nothing (§9.2). `config.d/*` is read
  alphabetically and `theme` sorts last, so a `$role` in an earlier file fails `sway --validate`
  — scripts source `theme.gen.env` at runtime instead (§9.6, §9.13). swayidle's timeout chain is
  AC/battery-dependent and owned by `scripts/idle.sh`, not a static list in `config.d/*` — it
  polls power state and restarts swayidle on change; edit timeouts there, not by hand-writing a
  new `exec_always swayidle …` line (§9.26).
- **`vim.pack` writes `nvim-pack-lock.json` into the folded `~/.config/nvim`** — i.e. the repo —
  and it is tracked **on purpose**: a pinned revision is configuration, unlike the active palette.
  Commit the lockfile diff; never gitignore it (§5.2, §8).
- A plugin that themes itself (lualine's `theme = 'auto'`) silently diverges from the palette —
  hand it a table built from the roles (§9.17).
- GTK CSS renders an undefined `@name` as **black, with no error** — the parity guard in `theme`
  exists for this (§9.10). tmux is the same shape: an undefined `@thm_foo` becomes an accepted
  empty `#[fg=]` and the bar quietly goes default (§9.18).
- waybar's `include` gives precedence to the **including** file — a module must live in `config`
  or the included file, never both (§9.12). foot's colours use `[colors-dark]` and foot has no
  config-reload signal at all; kitty reloads on SIGUSR1, sent only via kitty's own reloader,
  never `pkill` (§9.11).
- **A waybar state class is a bare GTK class** — `warning` collides with GtkInfoBar's stock one,
  which Nordic styles unscoped, so any module in that state paints an orange block. `style.css`
  declares `background`/`border`/`box-shadow` on every module for this reason; never delete that
  rule as "redundant". It renders correct under a GTK theme that scopes the class (gruvbox's
  Colloid does) and breaks on the switch, so verify by rendering, not by reading —
  `tests/check_waybar_paint.py`, via `check_consumers.sh`, does it under *both* palettes' GTK
  themes (§9.27).
- waybar's claude widget treats `~/.claude` as **read-only** — never add token refresh; state/cache
  lives in `~/.cache/claude-usage/` (safe to delete) (§9.23).
- **`lock.sh` must never touch the network**, at any cost: a lock that waits on a socket is a lock
  that does not happen. Its wallpapers are pre-synced by `walls-sync` into
  `~/Pictures/walls/<palette>/` — palette name *is* the directory name — and every failure falls
  back to the solid colour with the screen still locking. The bare `exec swaylock "$@"` colour
  fail-safe stays flagless (§9.25).
- tmux formats: wrap **every** dynamic value in `#{qh:…}` (trim runs before escape, the only safe
  order), and a hand-written `status-format[0]` needs `#[list=on]`/`#[nolist]` or every `align=`
  is ignored (§9.19, §9.20).
- mako: `ignore-timeout=1` means "use `default-timeout` instead" — pair it with
  `default-timeout=0`; `border-size` is not directional; `mako --config <file>` is the one real
  validator (§9.21).
- yazi: an unknown theme *key* in a known section is dropped in silence (everything else errors
  loudly); bare array keys **replace** the preset, only `prepend_*`/`append_*` merge; `[icon]`
  `files` keys must be lowercase (§9.22).
- `.bashrc` line 6 bails for non-interactive shells, so `bash -lc` skips it — test with
  `bash -ic` (§9.15).
- **`sh` has no function-local variables** — an assignment inside a function is the caller's
  name. It cost the old `sh` `theme` a real bug and is part of why `theme` is Python;
  `tests/theme_test.sh` is still `sh` and the rule applies there.
- Moving a config block wholesale silently loses whatever stays behind, and every check in this
  repo is syntactic. Diff the old block against the new one key by key before deleting (§9.14).
- `keyhint.sh` is a flat cell list in a 5-column yad grid: a cell count that isn't a multiple of 5
  shifts every later row, and `--geometry` clips overflow with no scrollbar. Both look like
  nothing happened (§7).

## Verify

No build. `stow -n -v <pkg>` (dry run) is the verification step for a package — run it before
`stow <pkg>`. `stow -R <pkg>` to pick up deletions; `stow -D <pkg>` to unlink.

Fresh clone: `./setup.sh <palette>` is the README quickstart as a script — fold-guard `mkdir`s
(§5.2), render before stow, the `.bashrc` move, a `stow -n`-gated stow of every package (derived
from the tree, so a new package is picked up automatically), then `tests/theme_test.sh`.
Re-runnable; with no argument it re-applies the remembered palette. **Never run it with a palette
argument on the live machine** unless switching is intended — `./setup.sh nord` switches the
desktop exactly like `theme nord`.

One test suite, for the one thing here with real logic:

```sh
sh tests/theme_test.sh        # sandboxed; never touches the live desktop
sh tests/check_consumers.sh   # starts the real apps against the LIVE config
```

**Run `theme_test.sh` after any edit to `bin/.local/bin/theme`.** It builds a throwaway repo under
a fake `$HOME` and stubs `swaymsg`/`sway`/`makoctl` to exit 1, so it never touches the live
desktop. `check_consumers.sh` is the one that would have caught the breakages that reached the
desktop: it asks waybar, foot, sway, vim, nvim, tmux and yazi whether they accept what was
rendered, rather than inspecting files from outside; it briefly starts a second waybar, and it
offscreen-renders every waybar module under **both** palettes' GTK themes (§9.27). A check there
can report `skip` as well as ok/FAIL — a skip is not a pass, and the tally line says how many.
`tests/` is a repo-root directory like `docs/`, **not** a stow package — never name it in a
`stow` command.

For sway changes: `sway --validate -c ~/.config/sway/config` **before** `swaymsg reload`, then
`pgrep -xc swayidle` (must be exactly 1, and still 1 after a second reload). A reload proves
nothing about **login** — it takes a different code path — so `tests/theme_test.sh` carries the
startup-only assertion (`check_sway_exec.py`); run it for any `exec` line you touch (§9.2).

## Conventions

- Adding a package: also add it to the README table, and to `PLAYBOOK.md` §5.2 with its fold
  decision and the reason. New system packages go in `packages.txt` / `packages-aur.txt` (§4).
- **Two palettes, one table.** `palettes.toml` holds both. **Never inline a hex in an application
  config** — `tests/theme_test.sh` fails on one. Adding a colour means adding the role to *both*
  palettes and using `{{role}}` in the relevant `*.tmpl`; `theme` refuses to render if the two
  palettes define different keys. §3.1 says what each role is *for*; note Nord and Nordic are
  different schemes (§3.2). **A colour is not always spelled with a `#`** — fuzzel takes bare
  `RRGGBBAA`, and `check_hex.py` once passed for months while blind to that spelling. When a
  consumer wants a third notation, extend the check *first*: a green assertion the guard cannot
  see is worse than none. For a file parsed before `config.d/theme`, derive the colour at runtime
  — `sway/.config/sway/scripts/cliphist_delete.sh` is the worked example.
- **Themed files are templates.** `<name>.tmpl` renders to `<name>` with `.tmpl` stripped.
  Rendered files match `*.gen.*` — or a bare `*.gen`, which mako's `colors.gen` is, so `.gitignore`
  carries both globs — and are gitignored; editing one is pointless. The seven files
  read at hardcoded paths can't carry the marker and are listed individually in `.gitignore` —
  that list is structural, not growing (§2.3).
- **Switching is `theme <name>`** (`bin/.local/bin/theme`), deliberately unbound (§7). Never
  switch by editing configs, and never introduce a theme stow package — a second package writing
  into a folded target would unfold it (§5.2).
- **Switching is not a repo change.** The active palette lives in `$XDG_STATE_HOME/theme/palette`;
  every rendered file is gitignored, so a switch leaves `git status` untouched —
  `tests/theme_test.sh` asserts it.
- **`theme` must run before `stow` on a fresh clone** (`setup.sh` encodes the order) and after
  adding a themed file to an unfolded package (§3.3). Applying is idempotent; re-running repairs
  a deleted or edited artefact.
- `theme` skips papirus-folders when stdin is not a tty (it needs `sudo`); `--no-icons` forces the
  skip. Icon tint therefore only changes on an interactive run.
- No binaries. The two wallpapers live in `~/Pictures/wallpapers`, and the lock screen's ~320 MB of
  them in `~/Pictures/walls/<palette>/`, not here.
