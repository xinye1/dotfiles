# yazi — a themed file manager package

**Date:** 2026-08-16
**Status:** implemented 2026-08-16. Both suites pass (15 + 11 assertions); both failure arms of the
new `yazi` consumer check were provoked and observed to fire.
**Scope:** add `yazi` as a stow package whose colours render from `palettes.toml`, plus the
behavioural config and the one shell integration that makes it useful.

---

## 0. Background

yazi 26.5.6 is installed (`/usr/bin/yazi`, `/usr/bin/ya`) and has no config at all — `yazi --debug`
reports all six of its config paths as `No such file or directory`. It therefore runs on its embedded
presets, in whatever colours those presets name, which is the drift this repo exists to prevent.

Everything below is grounded in the presets extracted from the installed binary rather than from
documentation, because the schema moved recently (`[manager]` → `[mgr]`) and a wrong key here fails
in the worst possible way — see §6.

---

## 1. What carries colour, and what does not

yazi reads six files. Only one of them can contain a colour:

| File | Colour? | Decision |
|---|---|---|
| `theme.toml` | **yes** | Rendered from a template |
| `yazi.toml` | no | Tracked plainly |
| `keymap.toml` | no | Tracked plainly |
| `init.lua` | n/a | Not used — no plugins |
| `package.toml` | n/a | Not used — no plugins |
| `vfs.toml` | n/a | Not used |

A user `theme.toml` **overrides** the preset key by key rather than replacing it, so the template
sets only the keys that carry a colour. Separators, glyph padding and the hovered-row indicator are
left to the preset. This keeps the template a palette layer and nothing else,
which is the same division `colors.gen.conf` has in the `tmux` package.

`[mgr] syntect_theme` stays empty **and that is a substantive choice, not an omission.** The binary
embeds a tmTheme named `ANSI` whose every colour is a placeholder index into the 16 terminal slots
(`#01000000`, `#02000000`, …). With `syntect_theme = ""` yazi uses it, so syntax highlighting in the
preview pane resolves through the terminal's ANSI ramp — which already comes from `[nord.ansi]` /
`[gruvbox.ansi]` via kitty and foot. Preview highlighting therefore follows the palette **for free**,
and pointing `syntect_theme` at a generated tmTheme would be strictly worse: a second, parallel
definition of the same sixteen colours.

---

## 2. The filename problem, and the `.gitignore` exception

yazi reads `~/.config/yazi/theme.toml` at a hardcoded name. The rendered output therefore cannot
carry the `.gen.` marker, and the `*.gen.*` glob cannot catch it.

That means one new line in the individually-listed block of `.gitignore` — the block whose own
comment reads:

> The list is structural rather than growing — it can only change if an application with a hardcoded
> config filename joins the desktop.

yazi is exactly that application, so this is the rule firing as written rather than being bent. It is
still the first time it has fired since the six GTK files were written down, so the comment gets
updated to say so: the block becomes seven paths across two applications, and the sentence stays.

Alternatives considered and rejected:

- **A yazi *flavor*** (`[flavor] dark = "…"` + `flavors/<name>.yazi/flavor.toml`). Moves the problem
  without solving it — `flavor.toml` is a hardcoded name too — and adds a directory level.
- **Symlink-flipping between two tracked flavors.** This is the pointer mechanism the repo replaced
  on 2026-08-13, and it would reintroduce tracked hexes, which `check_hex.py` rejects.

**The `.gitignore` line is test-enforced, not merely conventional.** `theme_test.sh`'s final
assertion builds a sandbox repo, commits, switches palette, and requires `git status --porcelain` to
be byte-identical before and after. Forget the line and that assertion fails.

---

## 3. Fold decision: unfolded

`ya pkg add` writes `plugins/`, `flavors/` and `package.toml` into `~/.config/yazi`. That is
untracked content inside the package directory, which is precisely what PLAYBOOK §5.2's rule
forbids folding over — the same reason `alacritty` and `vim` are unfolded.

No plugin is used today. The decision is made now anyway, because unfolding *later* costs
`stow -D && rmdir && stow`, and the trap PLAYBOOK §5.2 documents is discovering the need in the
middle of something else.

**Consequence, stated because it will bite:** a file added to the package later is silently absent
from `~/.config/yazi` until `stow -R yazi`.

---

## 4. Role mapping

Thirteen roles, no additions to `palettes.toml`. The mapping, by intent rather than by hue:

| Intent | Role | Where it lands |
|---|---|---|
| Structure — borders, titles, active chrome | `accent` | every `border`, `title`, `cwd`, tab active, mode normal |
| Directories and secondary emphasis | `accent2` | `[filetype]` directory fallback, `which` descriptions, `tasks`/`pick` hovered |
| Recessive text | `muted` | `symlink_target`, `which.rest`, `perm_sep`, absent/stale VFS entries |
| Panel fill | `surface` | `which.mask`, mode/tab inactive, progress backgrounds |
| Selection fill | `sel` | `mgr.border_style` |
| Text on a filled chip | `bg` | foreground of every reversed chip, so a chip reads against its own fill |
| Danger | `critical` | cut markers, orphans, `perm_write`, archives, error notifications |
| Attention | `warning` | selected markers, `find_keyword`, images, `perm_read` |
| Confirmation | `success` | copied markers, executables, `perm_exec`, info notifications |
| Distinct-but-calm | `indicator` | `which.cand` |

`bg` as a *foreground* is the load-bearing trick: the preset uses `reversed = true` for chips, which
takes the terminal's colours rather than the palette's. Setting `{ fg = bg, bg = accent }` explicitly
means a mode chip or an active tab reads correctly whatever the terminal is doing.

The one place the preset's `reversed` is deliberately kept is `[indicator]` — the hovered row. Reverse
video there inverts against the *file's own* `[filetype]` colour, which is yazi's signature look and
is palette-neutral by construction.

### 4.1 Icons (added 2026-08-17)

The preset ships **725 icon rules and paints every one from the Material palette** — `#03a9f4`,
`#ffc107`, `#f44336`. That is a third colour scheme, fixed in the binary, matching neither palette
and not moving when the palette does. It is precisely the drift the README describes: "the desktop
previously drifted into four incompatible palettes because each config was themed by hand", except
this one arrived pre-drifted.

All four arrays (`dirs`, `files`, `exts`, `conds`) are therefore replaced. Bare keys replace where
`prepend_*`/`append_*` merge — the same property as `[filetype] rules`, cutting both ways: it makes
a clean sweep possible, and it means the fallbacks at the end of `conds` must be restated or every
unmatched file silently loses its icon.

**Colour is by bucket, never per-format.** Two files of the same kind cannot drift apart, which is
the palette table's own argument one level down. The buckets echo `[filetype]` deliberately, so a
row's glyph and its filename agree instead of arguing:

| Bucket | Role | Echoes |
|---|---|---|
| Source you write | `accent` | — |
| Data, markup, configuration | `indicator` | — |
| Documents and prose | `fg` | the default filename colour |
| Images | `warning` | `[filetype] image/*` |
| Audio and video | `accent2` | `[filetype] {audio,video}/*` |
| Archives | `critical` | `[filetype]` archive mimes |
| Shells and executables | `success` | `[filetype] is = "exec"` |
| Byproducts (log, bak, cache, swp) | `muted` | `[filetype] vfs/{absent,stale}` |
| Directories, named or not | `accent2` | `[filetype]` directory fallback |

**The trade, stated so nobody rediscovers it:** 725 rules become 171, and an extension outside that
set falls through to the generic file icon rather than getting a bespoke one. That is the README's
"granularity loses" applied to icons — a table readable in one screen, at the cost of not knowing
what a `.3mf` file is. Extending it is adding a line to a bucket.

Glyphs are lifted from the preset in the installed binary rather than chosen by hand, so every one
is a codepoint yazi already expects the Nerd Font to carry; the ~20 names the preset lacks
(`parquet`, `tsv`, `cargo.toml`, `rst`, …) borrow a sibling's glyph rather than inventing one that
might render as a box. `files` keys must be **lowercase** — yazi folds the filename before matching,
and the preset lists `dockerfile`, `makefile` and `license` that way. A capitalised key never
matches, with no error.

Verified by rendering both palettes and collecting every distinct `fg`: 11 colours in each, all of
them roles from `palettes.toml`. No Material colour survives.

---

## 5. Behaviour and integration

### 5.1 `yazi.toml`

```toml
[mgr]
ratio        = [ 1, 4, 3 ]   # yazi's default, restated for orientation
show_hidden  = true          # ≠ default
linemode     = "size"        # ≠ default
mouse_events = []            # ≠ default

[preview]
wrap = "yes"                 # ≠ default
```

Four lines differ from the preset, and each is a decision:

- **`show_hidden = true`.** The machine's working directories are dotfile trees. `.` still toggles.
- **`linemode = "size"`.** The one column worth its width by default; `ms`/`mm`/`mp` switch at runtime.
- **`mouse_events = []`.** Matches the deliberate "mouse off, matching vim" call in `nvim`
  (commit `eb50249`). Noted as a genuine tension: `tmux.conf:34` sets `mouse on`. The tie is broken
  toward the modal, keyboard-driven tools rather than the multiplexer.
- **`wrap = "yes"`.** Long lines in the preview pane truncate otherwise, which is the failure mode
  that makes a preview pane useless for prose and Markdown.

### 5.2 `keymap.toml`

The preset keymap is already good, and the additions are limited to what is genuinely missing.
`prepend_keymap` only — nothing the preset binds is taken away, so the muscle memory in yazi's own
docs and `~` help continues to work.

```toml
[[mgr.prepend_keymap]]
on   = [ "g", "r" ]
run  = 'shell -- ya emit cd "$(git rev-parse --show-toplevel)"'
desc = "Go to the repo root"

[[mgr.prepend_keymap]]
on   = [ "g", "p" ]
run  = "cd ~/repos"
desc = "Go to ~/repos"
```

Notably **not** added, because the preset already has them: `cc`/`cd`/`cf`/`cn` copy paths to the
system clipboard, `.` toggles hidden, `s`/`S` search by name via `fd` and by content via `rg`, `z`
jumps via `fzf`. All four of those tools are installed. `Z` (zoxide) is bound by the preset and will
fail at press time — zoxide is not installed; §7 lists it.

### 5.3 Shell integration

yazi's documented `y` wrapper, into `bash/.bashrc`: run yazi, and on exit `cd` to wherever it ended
up. Guarded on the binary being present, matching how `mise`, `starship` and `dircolors` are guarded
in that file, so the `.bashrc` still works on a machine without yazi.

```sh
command -v yazi >/dev/null && y() {
    local cwd
    cwd=$(mktemp -t "yazi-cwd.XXXXXX")
    yazi "$@" --cwd-file="$cwd"
    if [ -s "$cwd" ] && IFS= read -r dir < "$cwd" && [ -n "$dir" ] && [ "$dir" != "$PWD" ]; then
        builtin cd -- "$dir" || return
    fi
    rm -f -- "$cwd"
}
```

`.bashrc:6` returns early for non-interactive shells, so this must be tested with `bash -ic`, never
`bash -lc`.

**No sway keybinding.** yazi is a terminal application launched from a shell that already has `y`,
and `keyhint.sh` is a flat 5-column yad grid where adding cells that are not a multiple of five
silently shifts every later row (CLAUDE.md; PLAYBOOK §7). The binding would cost more than it buys.

---

## 6. Verification

`yazi --debug </dev/null` is a real validator, and better than most consumers in this repo. Measured
against a scratch `YAZI_CONFIG_HOME`:

| Fault | Result |
|---|---|
| Malformed TOML | **exit 1**, with the offending line and a caret |
| Unknown `[section]` | **exit 1**, `data did not match any variant of untagged enum CustomField` |
| Bad hex (`#zzzzzz`) | **exit 1**, `Failed to parse Colors`, caret under the value |
| Empty value (`fg = ""`) | **exit 1** |
| Valid config | exit 0, prints each config path and its byte count |
| **Unknown key in a known section** | **exit 0, silently ignored, no warning at all** |

The last row is the hole, and it is the same shape as GTK's undefined `@name`, tmux's empty `fg=` and
kitty's `Ignoring unknown config key` — except that yazi does not even log it. The mitigation is that
every key in the template is copied from the preset extracted from this exact binary, and that is
recorded in the template's own header so the next person knows where the keys came from.

The rest of the suite picks the package up with no changes:

- `check_syntax.py` globs `*.tmpl`, so it parses the rendered `theme.toml` with `tomllib` and checks
  the banner's comment marker automatically.
- `check_hex.py` skips `.tmpl` and reads `git ls-files`, so the gitignored output is correctly
  invisible to it and the tracked `yazi.toml`/`keymap.toml` are correctly checked.
- `theme_test.sh`'s "every placeholder resolves in both palettes" covers the new template for free.

**Honest caveat.** `theme_test.sh`'s determinism and round-trip assertions use
`find -name '*.gen*'`, so `theme.toml` falls outside both — exactly as the six GTK files already do.
This is a pre-existing gap that the new file joins rather than creates. Widening the glob to cover
the hardcoded-name files is a worthwhile follow-up and is deliberately not bundled here.

Interactively, a bad config makes yazi print `Press <Enter> to continue with preset settings…` and
start anyway. So a broken theme degrades to preset colours rather than to a crash, which is why the
check is by exit code in `check_consumers.sh` and not by "did it start".

---

## 7. Optional dependencies

Present already: `jq`, `poppler`, `fd`, `rg`, `fzf`, `resvg`, `imagemagick`, `file`. kitty speaks the
kitty graphics protocol natively and `tmux.conf:36` already sets `allow-passthrough on` (yazi also
runs `tmux set -p allow-passthrough on` itself), so image previews work in and out of tmux with no
`ueberzugpp`.

Missing, in descending order of what you would actually notice:

| Package | Buys |
|---|---|
| `7zip` | Archive preview and the `extract` opener — without it, archives show nothing |
| `ffmpegthumbnailer` | Video thumbnails |
| `perl-image-exiftool` | The `exif` opener, bound by the preset |
| `zoxide` | Makes the preset's `Z` binding work instead of erroring |
| `chafa` | Image fallback outside kitty |

None is required. This lands as a PLAYBOOK §4.2 note, not as an install step.

---

## 8. Build order

1. `yazi/.config/yazi/theme.toml.tmpl`, `yazi.toml`, `keymap.toml`
2. `.gitignore` — the new path, and the block comment updated to seven paths / two applications
3. `bash/.bashrc` — the `y` function
4. `theme` (re-render), then `stow -n -v yazi`, then `stow yazi`
5. `tests/check_consumers.sh` — the yazi block
6. `README.md` package table; `PLAYBOOK.md` §4.2 and §5.2; `docs/archive/README.md` row
7. `sh tests/theme_test.sh` and `sh tests/check_consumers.sh`

---

## 9. What this deliberately does not do

- **No plugins, no `init.lua`, no `package.toml`.** That would put untracked clones inside the
  package and re-open the `nvim-pack-lock.json` question about whether a lockfile is configuration.
  Worth doing on its own terms later, with the fold decision already made correctly here.
- **No sway keybinding** (§5.3).
- **No new palette role.** Thirteen cover it.
- **No `syntect_theme`** (§1).
