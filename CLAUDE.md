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

## Verify

No build or tests. `stow -n -v <pkg>` (dry run) is the verification step — run it before `stow <pkg>`.
`stow -R <pkg>` to pick up deletions; `stow -D <pkg>` to unlink.

## Conventions

- Adding a package: also add it to the README table.
- `alacritty.toml` imports from `~/.config/alacritty/themes` (an untracked clone of
  alacritty/alacritty-theme). Not managed here.
