# dotfiles

GNU Stow-managed. Each top-level dir is a package; contents mirror the layout under `$HOME`.

## Gotchas

- Repo lives at `~/repos/dotfiles`, **not** `$HOME`. Stow's default `--target` is the repo's
  *parent* — wrong here. `.stowrc` pins `--target=~`; don't remove it or run stow from elsewhere.
- Stow exits 0 when it links to the wrong target. "Config not applied" is diagnosed by checking
  where the symlink actually landed (`ls -la ~/repos/`, `ls -la ~/.config/<app>`), not by exit code.
- Package contents are paths relative to `$HOME`: `foo/.config/foo/x.toml` → `~/.config/foo/x.toml`.
  `foo/x.toml` → `~/x.toml`. Getting this wrong is silent.
- **Folded vs unfolded dirs.** If the target dir doesn't exist, stow links the whole directory
  (`~/.config/waybar` → package dir) and new files in the package appear with no further action.
  If it already exists as a real dir, stow links file-by-file and a *newly added* file needs
  `stow -R <pkg>` — it is silently absent until then. Check with
  `[ -L ~/.config/<pkg> ] && echo folded || echo unfolded`. **Don't check with
  `ls -la ~/.config | grep -E ' <pkg>$'`** — `ls` prints a symlink as `<pkg> -> target`, so the `$`
  anchor matches only the *unfolded* case and the check silently passes when all is well. To fold
  one that isn't: `stow -D <pkg> && rmdir <the now-empty target dirs> && stow <pkg>`.
- Don't fold a dir that a tool writes into or that holds untracked content — `~/.config/alacritty`
  stays unfolded because the `themes` clone lives inside it, so alacritty does need `-R`.
  `gtk` is unfolded for the same reason: **nwg-look writes into `~/.config/gtk-{3,4}.0`.**
  `bin` is unfolded because `~/.local/bin` holds untracked binaries (`coderabbit` is 104 MB);
  folding it would drag them into the repo, so a new script there needs `stow -R bin`.
- **nwg-look clobbers the `gtk` package.** All five of its export toggles are on, so clicking Apply
  rewrites `settings.ini`, `.gtkrc-2.0`, xsettingsd, and — via `export-gtk4-symlinks` — replaces
  `~/.config/gtk-4.0/gtk.css` with a symlink into `/usr/share/themes/`, destroying the libadwaita
  overrides. After ever opening nwg-look: `ls -la ~/.config/gtk-4.0/` and `git status`, then
  `stow -R gtk` if needed. nwg-look isn't needed at runtime — `settings.ini` is the source of truth
  and `sway/.config/sway/scripts/import-gsettings` pushes it to gsettings on every reload.
- **sway `exec` vs `exec_always`.** `exec_always` starting a daemon without `pkill -x <name>;` in
  front leaks one process per reload (this is how 40 swayidle processes accumulated). `exec` only
  runs at startup, so a fix using it can't be tested with `swaymsg reload` and looks broken.
  `exec export FOO=bar` does nothing at all — the subshell exits with the variable.
- `sway/.config/sway/config.d/*` is read **alphabetically**; `theme` sorts last and wins conflicts.
  sway `$variables` therefore **cannot cross that ordering** — a `$role` in a binding in `default`
  is parsed before `theme` defines it and fails with `Invalid border color $accent`. Anything in an
  earlier file that needs a colour must call a script that sources `theme.gen.env` at runtime.
- **`vim.pack` writes `nvim-pack-lock.json` into `~/.config/nvim`**, not into the data dir where the
  plugin code goes — and `nvim` is folded, so that is *the repo*. It is **tracked on purpose**: a
  pinned revision belongs to the configuration, unlike the active palette. So `:lua vim.pack.update()` dirties
  the tree by design and the lockfile diff is meant to be committed. Don't "fix" it by gitignoring —
  that would put untracked content inside a folded package. Note §5.2 now records one standing
  exception to that rule — the rendered `*.gen.*` palette files — and it is an exception precisely
  because a glob catches them; do not read it as a general licence.
- **A plugin that themes itself will silently diverge from the palette.** lualine's default
  `theme = 'auto'` reads `g:colors_name` and loads its *own* bundled theme of that name — it ships
  both `nord` and `gruvbox`, so it always finds one and paints the bar a few shades off the waybar
  above it, erroring never. `nvim/.config/nvim/statusline.lua` hands it a table built from the
  thirteen roles instead. Apply the same rule to any future self-theming plugin.
- **GTK CSS renders an undefined `@name` as black, with no error.** No warning, no fallback — a
  widget just turns black. This is why `theme` refuses to render when the two sections of
  `palettes.toml` do not define identical keys; that refusal is the guard working.
- **waybar's `include` gives precedence to the INCLUDING file.** A module defined in `config`
  silently overrides the same module in an included file. The `clock` module had to be deleted
  from `config` entirely and defined only in `colors.gen.json`.
- **foot's plain `[colors]` section is deprecated** — the template uses `[colors-dark]`. foot has no
  config-reload signal at all; `SIGUSR1`/`SIGUSR2` only pick between the `[colors-dark]` and
  `[colors-light]` blocks loaded at startup, so a switch needs a server restart or a logout.
- **`.bashrc` line 6 is `[[ $- != *i* ]] && return`**, so `bash -lc` skips the entire file. Test
  anything sourced from it with `bash -ic`.
- **`sh` has no function-local variables.** A name assigned inside a function is the caller's name.
  This cost the old `sh` version of `theme` a real bug: a function reused `target`, the global
  holding the requested palette, so it returned with `target` clobbered and sourced the wrong env
  file — aborting *after* the symlinks flipped but *before* papirus-folders ran, which presented as
  "the switch needs two runs". It is part of why `theme` is Python now. `tests/theme_test.sh` is
  still `sh`; the rule applies there.
- **Moving a config block wholesale silently loses whatever stays behind**, and every check here is
  syntactic. The waybar clock's `actions` block was dropped exactly this way and nothing complained.
  Diff the old block against the new one key by key before deleting it.
- **mako's `ignore-timeout=1` does not mean "never expire".** It means *ignore the timeout the app
  asked for and use `default-timeout` instead* — so on its own, under a global `default-timeout`, it
  makes a notification expire **sooner** than an app requested. Pair it with `default-timeout=0` in
  the same criteria. A comment claiming otherwise sat over `[urgency=high]` for months (PLAYBOOK
  §6.2). `border-size` is also **not** directional, though `margin`/`outer-margin`/`padding`/
  `border-radius` all are.
- **`mako --config <file>` is a real validator**, and the only one mako has: it fully parses the
  config *and its includes* before touching D-Bus, so the running daemon is unaffected and the
  second instance just exits on the name clash. Distinguish the parse error from the expected
  `Failed to acquire service name` — `check_consumers.sh` greps for the former, since the exit code
  is dominated by the latter.
- **tmux has no colour indirection, and no error for a missing one.** Every colour option takes a
  literal, so `tmux/.config/tmux/colors.gen.conf` carries the hexes twice over: as `@thm_*` user
  options for the format strings (`#[fg=#{@thm_accent}]` — tmux does expand `#{}` inside `#[]`) and
  as the plain style options, which take a colour and would not expand a format. An **undefined**
  `@thm_foo` expands to nothing, `#[fg=]` is accepted, and the bar quietly renders in the default
  colours — the GTK `@name` failure again. `check_consumers.sh` greps the expanded format for an
  empty `fg=`.
- **A `#` arriving from data breaks the tmux status bar downstream of itself.** tmux expands the
  format first and parses `#[...]` directives in the *result*, so a `#` from a pane title, window
  name or branch name is indistinguishable from the start of one — and a value ending in `#` pairs
  with the `#` of the next real directive to form `##`, an escaped literal, printing that directive
  as visible text. A Claude Code pane title truncated onto an issue number ate
  `#[nolist align=right]` and left the right-hand group unaligned. Wrap **every** dynamic value in
  `#{qh:…}` (`#S`/`#W` don't escape; use `#{qh:session_name}`/`#{qh:window_name}`), and have any
  `#()` script escape its own output. Two constraints on `qh` that are not in the man page:
  it does **not** apply to a nested `#{…}`, only to a plain variable name — hence chained modifiers
  and a conditional wrapping two modified branches, not one modifier wrapping a conditional; and in
  `#{=/50/…;qh:x}` the trim runs **first**, which is the only safe order, since escaping first lets
  the trim fall between the halves of a `##` and recreate the dangling `#`.
- **A hand-written tmux `status-format[0]` needs `list=on`/`nolist`, or every `align=` group is
  ignored.** Wrapping the `#{W:…}` window list in `#[list=on …]` … `#[nolist align=centre]` is what
  identifies the elastic part of the line; without it tmux accepts all three groups, reports
  nothing, and draws left, centre and right run together flush left. Taking the format over also
  drops the per-window activity/bell *style* options — the stock format's nested conditionals for
  them are gone, so those states have to be shown as characters in `window-status-format`. Neither
  loss is visible except by attaching a client and looking.
- **yazi ignores an unknown theme key in silence — no error, no warning, not even in `--debug`.**
  It is strict about everything else: `yazi --debug </dev/null` exits 1 with a caret under a bad
  hex, a bad value, malformed TOML or an unknown `[section]`, which makes it a better validator than
  most consumers here. But a *key* misspelt inside a known section is dropped without a word, and the
  schema does move (`[manager]` was renamed `[mgr]`). So the keys in `theme.toml.tmpl` are copied
  from the preset embedded in the installed binary, not from documentation — re-derive them the same
  way after an upgrade: `strings /usr/bin/yazi | grep -n 'schemas/theme.json'`, then read forward.
  More yazi traps, all the same shape — **a bare array key replaces, only `prepend_*`/`append_*`
  merge**: `keymap` wipes the whole preset keymap, and `[filetype] rules` and the four `[icon]`
  tables replace theirs, so every *fallback* rule has to be restated or files quietly stop being
  coloured or lose their icon. The `[icon]` tables are replaced here on purpose: the preset carries
  725 rules painted from the Material palette, a third colour scheme fixed in the binary that
  matches neither palette and does not move when one switches. Its `files` keys are **lowercase** —
  yazi folds the filename before matching, so a capitalised key never matches and says nothing.
  Interactively a bad config is not fatal either —
  yazi prints `Press <Enter> to continue with preset settings...` and starts anyway, which is why
  `check_consumers.sh` closes stdin and then asks whether the theme actually *loaded*.
- **`keyhint.sh` is a flat cell list in a 5-column yad grid, and `--geometry` does not track it.**
  Append a number of cells that is not a multiple of 5 and every later row silently shifts a column;
  overflow the height and yad clips with no scrollbar and no warning. Both failures look like
  nothing happened. See PLAYBOOK §7.

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

`check_consumers.sh` is the one that would have caught the two breakages that
reached the desktop: it asks waybar, foot, sway, vim and nvim whether they
accept what was rendered, rather than inspecting the files from outside. It
briefly starts a second waybar.

**Run it after any edit to `bin/.local/bin/theme`.** It builds a throwaway repo under a fake `$HOME`
and stubs `swaymsg`/`sway`/`makoctl` to exit 1, so it never touches the live desktop. `tests/` is a
repo-root directory like `docs/`, **not** a stow package — it is never named in a `stow` command, and
must not be: `tests/…` would install to `~/tests/…`.

For sway changes: `sway --validate -c ~/.config/sway/config` **before** `swaymsg reload`, then
`pgrep -xc swayidle` (must be exactly 1, and still 1 after a second reload).

## Conventions

- Adding a package: also add it to the README table, and to `PLAYBOOK.md` §5.2 with its fold
  decision and the reason.
- **Two palettes, one table.** `palettes.toml` holds both. **Never inline a hex in an application
  config** — `tests/theme_test.sh` fails on one. Adding a colour means adding the role to *both*
  palettes and using `{{role}}` in the relevant `*.tmpl`; `theme` refuses to render if the two
  palettes define different keys. `PLAYBOOK.md` §3.1 says what each role is *for*; the values live
  only in the table. Note *Nord* and *Nordic* are different schemes (§3.2).
  **A colour is not always spelled with a `#`.** fuzzel's `-t`/`-S` take a bare `RRGGBBAA`, and
  `tests/check_hex.py` looked only for `#`-prefixed forms — so it passed for months with
  `-t bf616aff` sitting in a sway binding. It now checks both spellings. When a consumer wants a
  colour in some third notation, extend the check *first*: a green assertion the guard cannot
  actually see is worse than no assertion, because the next colour gets added trusting it.
  For a file parsed before `config.d/theme`, derive the colour at runtime instead of typing it —
  `sway/.config/sway/scripts/cliphist_delete.sh` is the worked example (`${CRITICAL#\#}ff`).
- **Themed files are templates.** `<name>.tmpl` renders to `<name>` with the `.tmpl` stripped, so
  `colors.gen.css.tmpl` -> `colors.gen.css`. Rendered files match `*.gen.*` and are gitignored;
  editing one is pointless. The six GTK/xsettingsd files read at a hardcoded path cannot carry the
  marker and are listed individually in `.gitignore` — that list is structural, not growing.
- **Switching is `theme <name>`** (`bin/.local/bin/theme`). It has no keybinding on purpose:
  a shortcut is for something you do often, and changing palette is not. Never switch by
  editing configs, and never introduce a theme stow package — a second package writing into a folded
  target would unfold it.
- **Switching is not a repo change.** `$XDG_STATE_HOME/theme/palette` holds the active palette,
  outside the repo because it is machine state, not configuration; every rendered file
  are gitignored, so a switch leaves `git status` untouched. If a switch ever dirties the tree the
  naming scheme has been broken, which `tests/theme_test.sh` asserts.
- **`theme` must run before `stow` on a fresh clone** — rendered files don't exist in a clone, and
  the unfolded packages (`gtk`, `alacritty`, `vim`) link file-by-file and would miss them. Applying
  is idempotent; re-running repairs a deleted or edited artefact.
- `theme` skips papirus-folders when stdin is not a tty, because it needs `sudo`; `--no-icons`
  forces that skip in a terminal. Icon tint therefore only changes on an interactive run.
- `~/.config/alacritty/themes` (an untracked clone of alacritty/alacritty-theme) is **optional now**
  — `alacritty.toml` imports its own rendered `colors.gen.toml`. Not managed here either way.
- No binaries. Two wallpapers (3.3 MB and 22 MB) lived inside stock config dirs and were kept out
  deliberately; `~/Pictures/wallpapers` is where they go.
