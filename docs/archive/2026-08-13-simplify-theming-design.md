# Simplifying the theme layer: generate, don't point

**Date:** 2026-08-13
**Status:** Proposed — awaiting approval
**Supersedes mechanism from:** `2026-08-06-theme-switching-design.md` (the two-palette model itself is retained)

## §0 Background

The repo works. It is also heavier than a dotfiles repo should be, and the weight is not spread
evenly — it is concentrated almost entirely in the machinery that lets one keystroke swap Nord for
Gruvbox.

Measured, 2026-08-13:

| Artefact | Size | Exists only for palette switching? |
|---|---|---|
| Colour fragment files (`*-nord.*`, `*-gruvbox.*`) | 36 files | Half are pure duplication |
| `bin/.local/bin/theme` | 317 lines `sh` | Entirely |
| `tests/theme_test.sh` | 329 lines | Entirely — the switcher is its only subject |
| `.gitignore` pointer list | 22 entries, hand-synced, test-guarded | Entirely |
| PLAYBOOK §2.3, §3.x | 276 of 1056 lines (26%) | Entirely |
| `docs/setup.html` | 2086 lines | Partly; re-tells PLAYBOOK in a second format |

That is ~5,500 lines of documentation guarding 85 config files.

**The intention of this change**, stated plainly because it is the thing future-me will forget:
*keep the capability, delete the mechanism.* Switching palettes is genuinely used and stays. What
goes is the indirection that made switching expensive to understand — eighteen gitignored symlinks,
a hand-maintained ignore list, and an ordering rule between two commands.

## §1 The trade being made

Accepted losses, explicitly:

- **A palette can no longer be edited by hand per-application.** Colours come from one table.
  Tweaking waybar's background alone now means adding a role, not editing a file. This is the
  "less granular control" being traded away, and it is the whole point.
- **A generation step exists.** `colors.gen.css` is a build artefact. You cannot edit it; edits are
  lost on the next switch. Today's fragments are directly editable.
- **A Python dependency for theming.** Already true of the repo (`swayfader.py`, `statusline.py`),
  but previously not true of `theme` itself.

Bought in exchange:

- Every colour is written **once per palette**, in one table, instead of 36 times across 36 files.
- The 22-entry `.gitignore` list and the test that guards it collapse to two globs.
- Role-parity bugs become **structurally impossible** rather than caught by a runtime check.
- ~26% of PLAYBOOK stops needing to exist.

## §2 Why the ignore list exists today, and why generation kills it

PLAYBOOK §3.3 justifies the hand-maintained list correctly:

> Listed one by one because the names are semantic, not lexical — no glob catches `colors.css`,
> `.gtkrc-2.0` and `theme.env` without also catching tracked files.

True *today*, because a pointer must take the exact filename the application's include directive
names, and those names collide with tracked names. Under generation **we choose the output name**,
so the constraint dissolves: name every artefact with a `.gen` infix and one pair of globs catches
all of them and nothing else.

This is the load-bearing insight of the whole design.

## §3 Target architecture

### 3.1 One palette table (tracked)

`palettes.toml` at the repo root — the executable form of PLAYBOOK §3.1:

```toml
[nord]
bg = "#2E3440"
surface = "#3B4252"
# ... 13 roles
desktop = "#272B33"
papirus_folder = "nordic"
gtk_theme_name = "Nordic"

[gruvbox]
bg = "#282828"
# ... same keys, necessarily
```

Parsed with `tomllib` (stdlib since 3.11; the machine runs 3.14). Two non-colour per-palette values
(`gtk_theme_name`, `papirus_folder`) live here too — they are already per-palette in
`theme-*.env` and have nowhere better to go.

**Role parity stops being a runtime check.** `check_roles()` exists (theme:127-142) because a role
defined in one palette and not the other renders as black in GTK CSS with no error. With one table
the failure mode becomes a missing key, caught at render time by name, naming the role and the
palette. The 16-line guard and its bespoke `grep`-and-compare are deleted.

### 3.2 One template per themed file (tracked)

`waybar/.config/waybar/colors.css.tmpl`:

```css
@define-color bg {{bg}};
@define-color accent {{accent}};
```

18 templates replace 36 fragments. Each colour appears once per palette in the table; each
application's *syntax* appears once in its template.

**Delimiter: `{{role}}`, not `$role` or `@role`.** Not cosmetic —
`string.Template`'s `$name` would substitute sway's own `set $bg #282828`, and an `@` delimiter
would collide with GTK CSS `@define-color`. `{{…}}` appears in none of the six config syntaxes here
(TOML, INI, GTK CSS, sway, Lua, vimscript).

### 3.3 Generated output (gitignored)

`<base>.gen<.ext>` beside its template, e.g. `colors.gen.css`, `theme.gen.env`,
`.gtkrc-2.0.gen`. Application includes are repointed once, at implementation time, from
`colors.css` to `colors.gen.css`.

`.gitignore` gains exactly:

```
*.gen
*.gen.*
```

and loses 22 lines plus the paragraph explaining them.

### 3.4 `theme`, rewritten (Python)

Survives, with the same CLI. What it does: read `.theme` or the argument, render every `*.tmpl`
against the chosen palette, write the `.gen` artefacts, write `.theme`, then reload.

| Function today | Fate |
|---|---|
| `fragments()`, `neutral_of()`, `retarget()` (theme:91-126) | **Deleted** — pointer machinery |
| `check_roles()` (theme:127-142) | **Deleted** — structurally prevented (§3.1) |
| `read_state()`, `infer_state()` | Kept, trivial |
| `reload_desktop()` (theme:204-221) | **Kept verbatim in behaviour** — sway `--validate` before reload, mako's separate `makoctl reload` because it is `exec`'d not `exec_always`'d |
| `reload_icons()` (theme:222-) | **Kept** — papirus-folders, the one step needing root |

Estimated ~150 lines from 317. Python rather than `sh` because CLAUDE.md records a real bug caused
by `sh`'s lack of function-local variables (`switch_to()` clobbering the caller's `target`), and
because `tomllib` and templating in `sh` would mean re-implementing both.

### 3.5 Explicitly unchanged

Stow, `.stowrc`, the folded/unfolded matrix, every application's include *mechanism* (a static
include of a fixed filename), the 13 roles themselves, and the two palettes. This change is
confined to how the included file comes to exist.

## §4 Migration

1. Write `palettes.toml` from the existing `theme-nord.env` / `theme-gruvbox.env`, which already
   carry all 15 keys.
2. For each of the 18 themed files, convert the *gruvbox* fragment into a template by replacing
   literal hex with `{{role}}`. Gruvbox because it is the active palette, so the rendered output can
   be diffed byte-for-byte against the current file.
3. **Verification gate:** render both palettes and diff every artefact against the corresponding
   existing fragment. Byte-identical output for all 36 is the proof the migration is faithful.
4. Repoint the 18 include directives at `.gen` names.
5. Delete the 36 fragments, the 18 pointers, the 22 ignore entries, `check_roles`, `retarget`,
   `neutral_of`, `fragments`.

Step 3 is the safety property: this is a refactor with an exact expected output, not a rewrite.

## §5 Tests

`tests/theme_test.sh` (329 lines) is replaced, not deleted — its subject changes. New suite asserts:

- every `{{role}}` referenced by any template exists in both palettes;
- rendering is deterministic (twice → identical bytes);
- every `.gen` artefact is ignored by git (the drift the old suite guarded, now one assertion);
- `theme <unknown>` exits non-zero and names the valid palettes;
- sway config still validates after a render.

Retained from the old suite: the fake-`$HOME` harness and the `swaymsg`/`makoctl` stubs — that
design was right and is why the suite never touches the live desktop.

## §6 Documentation

Two living documents; everything else archived.

| File | Fate |
|---|---|
| `README.md` | Front door. What this is, **the intention and the trade** (§1 of this spec, in prose), install in five commands, package table. |
| `PLAYBOOK.md` | Runbook. Architecture, the role table as source of truth, traps that cost real debugging time, recovery. Target ~450 lines from 1056. |
| `docs/setup.html` | **Deleted.** 2086 hand-maintained lines duplicating PLAYBOOK's headings; it will rot silently. |
| `docs/superpowers/plans/`, `specs/` | Moved to `docs/archive/`. Git history holds them; keeping them greppable costs nothing but they are not living docs. |
| `CLAUDE.md` | Updated: the fold/unfold gotcha stays, the pointer/ignore-sync gotchas go. |

## §7 Honest caveats

- **The ordering trap shrinks but does not vanish.** `theme` must still run before `stow` for the
  three *unfolded* packages (`gtk`, `alacritty`, `vim`), which link file-by-file and would miss a
  `.gen` artefact created afterwards. It is no worse than today, and it now affects three packages
  rather than all themed ones.
- **Generated files inside a stow package** is exactly what PLAYBOOK §5.2 warns against ("never fold
  a directory that holds untracked content"). The warning is about *folded* packages, and the
  folded themed packages (`waybar`, `sway`, `foot`, …) will now contain ignored `.gen` files. This
  is tolerable only because they are ignored by a glob that cannot drift; it is the one place this
  design spends a principle rather than earning one, and it should be stated in PLAYBOOK rather
  than hidden.
- **`nvim-pack-lock.json` is unaffected** and stays tracked — it is configuration, not a theme
  artefact, and the `.gen` glob does not touch it.
- **Byte-identical migration is asserted, not assumed** (§4.3). If any file cannot be reproduced
  exactly, that file is a finding, not a rounding error.

## §8 Out of scope

Package set, keybindings, `swayfader.py`, the fold/unfold matrix, and the `claude` package added in
PR #2. This spec touches theming and documentation only.

## §9 Prerequisite

PR #2 (`feat/claude-statusline`) modifies `README.md` and `PLAYBOOK.md`, both rewritten here. It
should merge before this work starts, or it will need rebasing through a wholesale doc rewrite.
