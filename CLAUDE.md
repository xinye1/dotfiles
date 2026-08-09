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
  earlier file that needs a colour must call a script that sources `theme.env` at runtime.
- **GTK CSS renders an undefined `@name` as black, with no error.** No warning, no fallback — a
  widget just turns black. This is why `theme` refuses to switch when the two palettes define
  different role sets; that refusal is the guard working.
- **waybar's `include` gives precedence to the INCLUDING file.** A module defined in `config`
  silently overrides the same module in an included fragment. The `clock` module had to be deleted
  from `config` entirely and defined only in `colors.json`.
- **foot's plain `[colors]` section is deprecated** — the fragments use `[colors-dark]`. foot has no
  config-reload signal at all; `SIGUSR1`/`SIGUSR2` only pick between the `[colors-dark]` and
  `[colors-light]` blocks loaded at startup, so a switch needs a server restart or a logout.
- **`.bashrc` line 6 is `[[ $- != *i* ]] && return`**, so `bash -lc` skips the entire file. Test
  anything sourced from it with `bash -ic`.
- **`sh` has no function-local variables**, and `bin/.local/bin/theme` is `/bin/sh`. A name assigned
  inside a function is the caller's name. `switch_to()` used a loop variable called `target` — the
  same global holding the requested theme — so it returned with `target` set to the last symlink's
  old value and `reload_icons` sourced `theme-colors-nord.ini.env`. Under `set -e` that aborted
  *after* the symlinks flipped but *before* papirus-folders ran, which looked like "the switch needs
  two runs". Never reuse a caller's variable name in a function there; `tests/theme_test.sh` pins it.
- **Moving a config block wholesale silently loses whatever stays behind**, and every check here is
  syntactic. The waybar clock's `actions` block was dropped exactly this way and nothing complained.
  Diff the old block against the new one key by key before deleting it.

## Verify

No build. `stow -n -v <pkg>` (dry run) is the verification step for a package — run it before
`stow <pkg>`. `stow -R <pkg>` to pick up deletions; `stow -D <pkg>` to unlink.

One test suite, for the one thing here with real logic:

```sh
sh tests/theme_test.sh                                  # the copy in the repo
THEME_BIN=~/.local/bin/theme sh tests/theme_test.sh     # the installed symlink
```

**Run it after any edit to `bin/.local/bin/theme`.** It builds a throwaway repo under a fake `$HOME`
and stubs `swaymsg`/`sway`/`makoctl` to exit 1, so it never touches the live desktop. `tests/` is a
repo-root directory like `docs/`, **not** a stow package — it is never named in a `stow` command, and
must not be: `tests/…` would install to `~/tests/…`.

For sway changes: `sway --validate -c ~/.config/sway/config` **before** `swaymsg reload`, then
`pgrep -xc swayidle` (must be exactly 1, and still 1 after a second reload).

## Conventions

- Adding a package: also add it to the README table, and to `PLAYBOOK.md` §5.2 with its fold
  decision and the reason.
- **Two palettes.** Colours come from the thirteen-role table in `PLAYBOOK.md` §3.1, which has a
  Nord column and a Gruvbox column. Adding a colour means adding **both** values under a role name —
  never inline a hex in an application config. The roles are declared in
  `waybar/.config/waybar/colors-{nord,gruvbox}.css` (GTK), `sway/.config/sway/colors-*.conf` (sway)
  and `sway/.config/sway/theme-*.env` (shell). Note *Nord* and *Nordic* are different schemes; the
  GTK theme is genuinely named `Nordic` and the palette is Nord.
- **Switching is `theme <name>`** (`bin/.local/bin/theme`, bound to `$mod+Shift+t`). Never switch by
  editing configs, and never introduce a theme stow package — a second package writing into a folded
  target would unfold it.
- **Switching is not a repo change.** The active palette is one word in `.theme` at the repo root.
  From it `theme` derives 17 pointer symlinks (`colors.css`, `.gtkrc-2.0`, `theme.env`, …), one per
  themed file. `.theme` **and all 17 pointers are gitignored**, so switching leaves `git status`
  untouched. If a switch ever dirties the tree, the `.gitignore` list has fallen behind — which
  `tests/theme_test.sh` checks against the fragments on disk.
- **The pointers do not exist in a fresh clone.** `theme <name>` creates them, so it must run
  **before `stow`** — the unfolded packages (`gtk`, `alacritty`, `vim`) link file-by-file and would
  otherwise miss them. Applying is idempotent: re-running repairs a deleted or wrong pointer and
  picks up a themed file added since.
- A new themed file needs only the pair `<base>-nord.<ext>` / `<base>-gruvbox.<ext>`; `theme`
  creates the pointer. Name it anything else and it is silently never themed — `theme` finds its
  work by scanning for `*-nord`/`*-nord.*` **fragments**, not by any list. The printed count going
  from 17 to 18 is the confirmation.
- Don't run `theme` without `--no-icons` in a non-interactive context: papirus-folders needs `sudo`.
- `~/.config/alacritty/themes` (an untracked clone of alacritty/alacritty-theme) is **optional now**
  — `alacritty.toml` imports its own `colors.toml` fragment. Not managed here either way.
- No binaries. Two wallpapers (3.3 MB and 22 MB) lived inside stock config dirs and were kept out
  deliberately; `~/Pictures/wallpapers` is where they go.
