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
- **nwg-look clobbers the `gtk` package** — it rewrites the two `settings.ini` files and recreates
  `.gtkrc-2.0`, xsettingsd and a `gtk-4.0/gtk.css` symlink this repo no longer carries. After ever
  opening it: `git status`, delete what it created, `stow -R gtk`. It is never needed — the GTK
  look is static Adwaita dark for both palettes, and `import-gsettings` pushes `settings.ini` on
  every reload (§9.1, §2.2). There is no `Adwaita-dark` theme installed: naming it renders GTK3
  *light*; dark comes from `Adwaita` plus `gtk-application-prefer-dark-theme=1`.
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
- **waybar is a supervised daemon, not a `bar {}` block** — `scripts/waybar_run.sh` restarts it when
  it aborts. An **orphaned** bar (supervisor dead, `PPid: 1`) is pixel-identical to a healthy one,
  so the desktop looks right while crash recovery is silently gone — that cost a 13-hour outage.
  `setpriv --pdeathsig` ties the two lifetimes so even SIGKILL cannot orphan it, and
  `check_consumers.sh` asserts one supervisor with every bar its child. **Never `pkill -x waybar`
  or `pkill -x waybar_run.sh` from a test** — `-x` matches by name across the whole session and
  kills the live bar (§9.29).
- **`vim.pack` writes `nvim-pack-lock.json` into the folded `~/.config/nvim`** — i.e. the repo —
  and it is tracked **on purpose**: a pinned revision is configuration, unlike the active palette.
  Commit the lockfile diff; never gitignore it (§5.2, §8).
- A plugin that themes itself (lualine's `theme = 'auto'`) silently diverges from the palette —
  hand it a table built from the roles (§9.17).
- GTK CSS renders an undefined `@name` as **black, with no error** — the parity guard in `theme`
  exists for this (§9.10). tmux is the same shape: an undefined `@thm_foo` becomes an accepted
  empty `#[fg=]` and the bar quietly goes default (§9.18).
- waybar's `include` gives precedence to the **including** file — a module must live in `config`
  or the included file, never both (§9.12). kitty — the one terminal carried —
  reloads on SIGUSR1, sent only via kitty's own reloader, never `pkill` (§9.11).
- **`muted` is chrome, `dim` is text.** `muted` may be almost invisible (borders, rules); anything
  meant to be *read* quietly takes `dim`, which carries a 4.5:1 floor in **both** palettes. `muted`
  measured 1.87:1 on the GTK tooltip under nord and 3.64:1 under gruvbox — legible in the palette it
  was written under, unreadable in the other. Tooltips sit on the **GTK theme's** background, not
  `bg`, so measure against that (§3.1, §9.28).
- **A waybar state class is a bare GTK class** — `warning` collides with GtkInfoBar's stock one,
  which the old Nordic theme styled unscoped, so any module in that state painted an orange block.
  `style.css` declares `background`/`border`/`box-shadow` on every module for this reason; never
  delete that rule as "redundant" — today's Adwaita scopes the class, which is exactly how the bug
  hid under gruvbox's Colloid for months. Verify by rendering, not by reading —
  `tests/check_waybar_paint.py`, via `check_consumers.sh`, renders under the theme
  `gtk-3.0/settings.ini` names (§9.27).
- **herdr** runs every Claude pane, and this session is probably inside one: a bare `herdr …`
  reaches the LIVE server through the inherited `HERDR_SOCKET_PATH`. Tests use their own
  `XDG_CONFIG_HOME`/`XDG_STATE_HOME`/short `HERDR_SOCKET_PATH` under `/tmp`, `HERDR_*` unset, and
  stop the server by the PID `env … herdr server &` gave them — never `herdr server stop`, `pkill
  herdr` or `setsid` (§9.30). Every key must be in `herdr --default-config` of the installed binary
  (the website documents newer releases; unknown keys are ignored in silence); herdr's settings
  screen rewrites the tracked `config.toml` in place, so `git status` after using it. Don't add a
  Claude hook that reports agent *state* — herdr reads it from the screen on purpose. Any `pkill
  -RTMIN` to waybar needs `-x`, or it also kills the supervisor (§9.29, §9.30).
- waybar's claude widget treats `~/.claude` as **read-only** — never add token refresh; state/cache
  lives in `~/.cache/claude-usage/` (safe to delete) (§9.23). The one exception is the floor set by
  `claude_usage.py --limits-reset` after an early limits reset (it restarts the pace markers
  only — the token charts keep their history): it lives in `$XDG_STATE_HOME/claude-usage/`, so
  deleting the cache cannot undo it.
- **The Windows tray (`windows/claude-usage/`) only paints** — every decision stays in
  `claude_usage.py`, reached through `wsl.exe … --json`; change behaviour there, not in the `.ps1`.
  It is Windows PowerShell 5.1 (no Python on the host). Its timer must never boot WSL. **Never add a
  hidden-launch trick** (compiled launcher, VBScript, `conhost --headless`): Defender flagged the
  first as malware on this managed machine. `windows/` is not a stow package (§9.31); its
  operational commands live in `windows/claude-usage/README.md` — keep that in step with
  `install.py`'s flags.
- **`lock.sh` must never touch the network**, at any cost: a lock that waits on a socket is a lock
  that does not happen. It locks over the palette's wallpaper slot only behind a local guard
  (bare sibling name, not a link, readable, < 8 MB — swaylock decodes before locking), and every
  failure falls back to the solid `$desktop` colour with the screen still locking. Run
  `sh tests/lock_test.sh` after any edit; it uses a stub, never the real swaylock. The bare
  `exec swaylock "$@"` colour fail-safe stays flagless (§9.25).
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
- The keybinding list (waybar keyboard-icon click, `keyhint.py`) is **parsed from the sway config at click
  time** — sway has no IPC that lists bindings. A binding in a shape the parser does not follow
  would silently drop off the list, so `tests/keyhint_test.py` asserts row count = bind lines in
  the repo's sway package; extend the parser, not the count (§7).

## Verify

No build. `stow -n -v <pkg>` (dry run) is the verification step for a package — run it before
`stow <pkg>`. `stow -R <pkg>` to pick up deletions; `stow -D <pkg>` to unlink.

Fresh clone: `./setup.sh <palette>` is the README quickstart as a script — fold-guard `mkdir`s
(§5.2), render before stow, the `.bashrc` move, a `stow -n`-gated stow of every package (derived
from the tree, so a new package is picked up automatically), then `tests/theme_test.sh`.
Re-runnable; with no argument it re-applies the remembered palette. **Never run it with a palette
argument on the live machine** unless switching is intended — `./setup.sh nord` switches the
desktop exactly like `theme nord`.

Three things here have real logic, and each has a suite:

```sh
sh tests/theme_test.sh        # sandboxed; never touches the live desktop
sh tests/check_consumers.sh   # starts the real apps against the LIVE config
sh tests/tp_backup_test.sh    # sandboxed; never touches restic, ssh or the network
sh tests/waybar_run_test.sh   # sandboxed; kills only PIDs it started itself
sh tests/lock_test.sh         # stub swaylock; never locks; also run by theme_test.sh
python3 tests/herdr_test.py   # stubs only; also run by theme_test.sh
python3 tests/keyhint_test.py # sway config parser; also run by theme_test.sh
python3 tests/menu_test.py    # the Super+Space palette; also run by theme_test.sh
python3 tests/claude_tray_test.py # Windows tray; PowerShell half skips without WSL interop
```

**Run `theme_test.sh` after any edit to `bin/.local/bin/theme`.** It builds a throwaway repo under
a fake `$HOME` and stubs `swaymsg`/`sway`/`makoctl` to exit 1, so it never touches the live
desktop. `check_consumers.sh` is the one that would have caught the breakages that reached the
desktop: it asks waybar, kitty, sway, mako, nvim, tmux, yazi and herdr whether they accept what was
rendered, rather than inspecting files from outside; it briefly starts a second waybar, and it
offscreen-renders every waybar module under **both** palettes' GTK themes (§9.27). A check there
can report `skip` as well as ok/FAIL — a skip is not a pass, and the tally line says how many.
`tests/` is a repo-root directory like `docs/`, **not** a stow package — never name it in a
`stow` command.

**Run `waybar_run_test.sh` after any edit to `sway/.config/sway/scripts/waybar_run.sh`.** It runs the
script against a fake `waybar` on `PATH` under a throwaway `$HOME` and kills only PIDs it captured
itself — it must never `pkill` by name, which reaches the live desktop. It exists because the bar
spent two days running orphaned (supervisor dead, `PPid: 1`, crash recovery gone) while looking
perfectly healthy, and then stayed down 13 hours. Point `WBR_BIN` at another copy to check the
assertions can still fail; it was built by proving 4 of its 6 checks fail against the pre-fix
script (§9.29).

**Run `tests/herdr_test.py` after any edit to the herdr attention plugin,
`waybar/.config/waybar/scripts/herdr_blocked.py` or `bin/.local/bin/herdr-session-backup`.** Every
external command (notify-send, makoctl, swaymsg, pkill, herdr) is a logging stub on `PATH`, so
nothing reaches the desktop, the bar or a herdr socket. It was checked by mutation: dropping `-x`,
the focus filter, the withdraw, the blocked-only filter, the empty-session guard and the
unchanged-skip each turn it red. `check_consumers.sh` adds the live half: a throwaway herdr server
judges the deployed `config.toml` and links the plugin (§9.30).

**Run `tp_backup_test.sh` after any edit to `bin/.local/bin/tp-backup`.** It builds throwaway repos
under a fake `$HOME` and exercises only `__capture`, so restic, ssh and the network are never
touched and the real backup repository cannot be reached. It exists because the backup regime went
eight days taking no snapshot (2026-08-28..09-03) on a case nobody had run: a worktree registered in
`.git/worktrees` whose directory no longer exists, which `git -C` answers with exit 128. Point
`TPB_BIN` at another copy to check the assertions can still fail — a green suite that cannot go red
is the `gate-fixtures` trap, and this one was built by proving 5 of its 7 checks fail against a copy
with the guard removed.

**Run `tests/menu_test.py` after any edit to `menu.py`, `menu.toml` or `cliphist_pick.sh`.**
fuzzel, notify-send, kitty, cliphist and wl-copy are logging stubs and `HOME`/`XDG_RUNTIME_DIR`
are throwaway, so nothing reaches the desktop. Actions run with a **fixed** `PATH`
(`~/.local/bin` + system dirs), not the session's, which has no `~/.local/bin`; `menu.py --check`
resolves against that same `PATH`, and the suite's rot guard runs it over the repo's `menu.toml`.
Point `MENU_BIN` at a copy to check the assertions can still fail (PLAYBOOK §7).

For sway changes: `sway --validate -c ~/.config/sway/config` **before** `swaymsg reload`, then
`pgrep -xc swayidle` (must be exactly 1, and still 1 after a second reload) and
`pgrep -xc waybar_run.sh` (same, and every `waybar`'s `PPid` must be that supervisor — never 1,
which means orphaned; §9.29). A reload proves
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
- **Switching is `theme <name>`** (`bin/.local/bin/theme`; also `Style › Theme…`
  in the palette), deliberately unbound (§7). Never
  switch by editing configs, and never introduce a theme stow package — a second package writing
  into a folded target would unfold it (§5.2).
- **Switching is not a repo change.** The active palette lives in `$XDG_STATE_HOME/theme/palette`;
  every rendered file is gitignored, so a switch leaves `git status` untouched —
  `tests/theme_test.sh` asserts it.
- **`theme` must run before `stow` on a fresh clone** (`setup.sh` encodes the order) and after
  adding a themed file to an unfolded package (§3.3). Applying is idempotent; re-running repairs
  a deleted or edited artefact.
- No binaries. Wallpapers are slots — `~/Pictures/wallpapers/<palette>` symlinks — not files here (§9.25).
