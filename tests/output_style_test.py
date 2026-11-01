"""Tests for claude/.claude/output-styles/*.md (stdlib unittest).

A custom output style without `keep-coding-instructions: true` replaces
Claude Code's built-in coding instructions instead of adding to them, and
nothing reports it: replies just change style while the engineering rules
silently leave the system prompt. That key is the reason this suite exists.

`settings.json` selects a style by its frontmatter `name` (the filename when
there is none), so the names are pinned too.

OUTPUT_STYLE_DIR points the suite at another copy (the mutation check).
"""
import os
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STYLES = Path(os.environ.get("OUTPUT_STYLE_DIR", REPO / "claude/.claude/output-styles"))


def scalar(path, key, value):
    """A YAML scalar this flat parser can read the same way YAML does.

    Claude Code loads a style whose frontmatter is invalid YAML without its
    fields, so `name` falls back to the filename and "outputStyle": "STE"
    stops matching. An unquoted value holding `: ` (`description: a: b` is
    invalid YAML) or ` #` (a comment YAML would cut off) is refused rather
    than read differently from Claude Code.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if ": " in value or value.endswith(":") or " #" in value:
        raise AssertionError(f"{path.name}: {key}: quote this value: {value!r}")
    if value[:1] and value[0] in "[]{}&*!|>'\"%@`#,?-":
        raise AssertionError(f"{path.name}: {key}: unsupported YAML form: {value!r}")
    return value


def frontmatter(path):
    """Flat `key: value` frontmatter between the leading `---` fences."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise AssertionError(f"{path.name}: no frontmatter on line 1")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise AssertionError(f"{path.name}: frontmatter is not closed")
    fields = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if not sep:
            raise AssertionError(f"{path.name}: not a key: value line: {line!r}")
        key = key.strip()
        if key in fields:
            raise AssertionError(f"{path.name}: duplicate key {key!r}")
        fields[key] = scalar(path, key, value.strip())
    body = "\n".join(lines[end + 1:]).strip()
    return fields, body


class OutputStyleTest(unittest.TestCase):
    def styles(self):
        found = sorted(STYLES.glob("*.md"))
        self.assertTrue(found, f"no output styles in {STYLES}")
        return found

    def test_every_style_keeps_coding_instructions(self):
        for path in self.styles():
            with self.subTest(style=path.name):
                fields, _ = frontmatter(path)
                self.assertEqual(fields.get("keep-coding-instructions"), "true")

    def test_every_style_has_name_description_and_body(self):
        for path in self.styles():
            with self.subTest(style=path.name):
                fields, body = frontmatter(path)
                self.assertTrue(fields.get("name"))
                self.assertTrue(fields.get("description"))
                self.assertTrue(body)

    def test_names_are_unique(self):
        names = [frontmatter(p)[0].get("name") for p in self.styles()]
        self.assertEqual(len(names), len(set(names)), names)

    def test_ste_is_selectable_as_STE(self):
        # settings.json carries "outputStyle": "STE"; a rename breaks it silently.
        fields, _ = frontmatter(STYLES / "ste.md")
        self.assertEqual(fields.get("name"), "STE")


if __name__ == "__main__":
    unittest.main()
