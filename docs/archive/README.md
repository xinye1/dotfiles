# Archive

Design docs and implementation plans for work that has landed. Kept because they are greppable and
record *why*, not because they describe the current system — for that, read `PLAYBOOK.md`.

| File | What it covers |
|---|---|
| `2026-08-06-theme-switching-design.md` | The original two-palette design. Its *model* still holds; its mechanism (paired fragments + symlink pointers) was replaced on 2026-08-13. |
| `2026-08-06-theme-switching.md` | The implementation plan for the above. |
| `2026-08-13-simplify-theming-design.md` | Replacing the pointers with generation from `palettes.toml`. |
| `2026-08-16-yazi-design.md` | Adding yazi as a themed package. Records the yazi 26.5.6 theme schema, why `syntect_theme` stays empty, and the measurements behind the `yazi --debug` consumer check — including the one fault it cannot see. |

`docs/setup.html` used to live here too — a 2086-line hand-maintained page that re-told PLAYBOOK in
a second format. It was deleted rather than archived: two documents describing one system is how
they drift, and git history has it.
