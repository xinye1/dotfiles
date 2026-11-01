"""Tests for claude/.claude/output-styles/*.md (unittest + PyYAML).

A custom output style without `keep-coding-instructions: true` replaces
Claude Code's built-in coding instructions instead of adding to them, and
nothing reports it: replies just change style while the engineering rules
silently leave the system prompt. That key is the reason this suite exists.

`settings.json` selects a style by its frontmatter `name` (the filename when
there is none), so the names are pinned too. Claude Code loads a style whose
frontmatter is invalid YAML without its fields, so `name` falls back to the
filename and "outputStyle": "STE" stops matching. The frontmatter is therefore
parsed as real YAML (python-yaml, in packages.txt), not by hand: a flat
`key: value` reader accepted `description: a: b` and `'it's'`, which YAML
rejects.

OUTPUT_STYLE_DIR points the suite at another copy (the mutation check).
"""
import os
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
STYLES = Path(os.environ.get("OUTPUT_STYLE_DIR", REPO / "claude/.claude/output-styles"))


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses a duplicate key instead of keeping the last."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def frontmatter(path):
    """The YAML mapping between the leading `---` fences, and the body."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise AssertionError(f"{path.name}: no frontmatter on line 1")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise AssertionError(f"{path.name}: frontmatter is not closed")
    try:
        fields = yaml.load("\n".join(lines[1:end]), Loader=UniqueKeyLoader)
    except yaml.YAMLError as err:
        raise AssertionError(f"{path.name}: frontmatter is not valid YAML: {err}")
    if not isinstance(fields, dict):
        raise AssertionError(f"{path.name}: frontmatter is not a mapping")
    body = "\n".join(lines[end + 1:]).strip()
    return fields, body


class OutputStyleTest(unittest.TestCase):
    def styles(self):
        found = sorted(STYLES.glob("*.md"))
        self.assertTrue(found, f"no output styles in {STYLES}")
        return found

    def test_every_style_keeps_coding_instructions(self):
        # A YAML boolean, not the string "true".
        for path in self.styles():
            with self.subTest(style=path.name):
                fields, _ = frontmatter(path)
                self.assertIs(fields.get("keep-coding-instructions"), True)

    def test_every_style_has_name_description_and_body(self):
        for path in self.styles():
            with self.subTest(style=path.name):
                fields, body = frontmatter(path)
                for key in ("name", "description"):
                    self.assertIsInstance(fields.get(key), str, key)
                    self.assertTrue(fields[key].strip(), key)
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
