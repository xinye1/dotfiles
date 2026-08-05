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
  `stow -R <pkg>` — it is silently absent until then. Check with `ls -la ~/.config | grep <pkg>`:
  a symlink means folded, a real dir means `-R` is required. To fold one that isn't:
  `stow -D <pkg> && rmdir <the now-empty target dirs> && stow <pkg>`.
- Don't fold a dir that a tool writes into or that holds untracked content — `~/.config/alacritty`
  stays unfolded because the `themes` clone lives inside it, so alacritty does need `-R`.
  `gtk` is unfolded for the same reason: **nwg-look writes into `~/.config/gtk-{3,4}.0`.**
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

## Verify

No build or tests. `stow -n -v <pkg>` (dry run) is the verification step — run it before `stow <pkg>`.
`stow -R <pkg>` to pick up deletions; `stow -D <pkg>` to unlink.

For sway changes: `sway --validate -c ~/.config/sway/config` **before** `swaymsg reload`, then
`pgrep -xc swayidle` (must be exactly 1, and still 1 after a second reload).

## Conventions

- Adding a package: also add it to the README table, and to `PLAYBOOK.md` §5.2 with its fold
  decision and the reason.
- Colours come from the Nord role table in `PLAYBOOK.md` §3.1 — pick a role, don't invent a hex.
  The 16 colours are declared as `@define-color` names in `waybar/.config/waybar/style.css`.
  Note *Nord* and *Nordic* are different schemes; this repo uses Nord.
- `alacritty.toml` imports from `~/.config/alacritty/themes` (an untracked clone of
  alacritty/alacritty-theme). Not managed here.
- No binaries. Two wallpapers (3.3 MB and 22 MB) lived inside stock config dirs and were kept out
  deliberately; `~/Pictures/wallpapers` is where they go.
