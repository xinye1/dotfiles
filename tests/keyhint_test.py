"""Tests for waybar/.config/waybar/scripts/keyhint.py (stdlib unittest).

keyhint reads sway's config files itself, because sway has no IPC call that
lists bindings. So the thing worth testing is the reading: each case below is
a config shape sway accepts and keyhint once could not, or plausibly could
not, see. The last test runs it over the repo's own sway package, so a
config change that the parser cannot follow fails here rather than showing
up as a shorter cheat sheet nobody counts.
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "waybar/.config/waybar/scripts/keyhint.py"
spec = importlib.util.spec_from_file_location("keyhint", SCRIPT)
kh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kh)


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def rows(self, text, **files):
        for name, body in files.items():
            self.write(name.replace("__", "/"), body)
        return kh.bindings(self.write("config", text))

    def test_single_line_binding_and_variables(self):
        rows = self.rows("set $mod Mod4\nset $term kitty\nbindsym $mod+Return exec $term\n")
        self.assertEqual(rows, [("default", "Super+Return", "kitty")])

    def test_longest_variable_wins(self):
        rows = self.rows("set $mod Mod4\nset $mod_alt Mod1\nbindsym $mod_alt+x kill\n")
        self.assertEqual(rows[0][1], "Alt+X")

    def test_block_with_flags_and_comments(self):
        rows = self.rows("set $mod Mod4\nbindsym --locked --to-code {\n"
                         "    # a comment inside the block\n"
                         "    $mod+v splitv\n    $mod+b   splith\n}\n")
        self.assertEqual([r[1:] for r in rows], [("Super+V", "splitv"), ("Super+B", "splith")])

    def test_bindcode_digits(self):
        rows = self.rows("bindcode {\n    Mod4+10 workspace number 1\n"
                         "    Mod4+19 workspace number 10\n}\n")
        self.assertEqual([r[1] for r in rows], ["Super+1", "Super+0"])

    def test_mode_labels_its_bindings_and_closes(self):
        rows = self.rows('mode "resize" {\n    bindsym {\n        Left resize shrink width 10 px\n'
                         '        Escape mode "default"\n    }\n    bindsym Return mode "default"\n}\n'
                         'bindsym Mod4+r mode "resize"\n')
        self.assertEqual([r[0] for r in rows], ["resize", "resize", "resize", "default"])

    def test_non_binding_blocks_are_skipped(self):
        rows = self.rows("input type:touchpad {\n    tap enabled\n}\n"
                         "bar {\n    status_command waybar\n}\nbindsym Mod4+q kill\n")
        self.assertEqual(rows, [("default", "Super+Q", "kill")])

    def test_includes_home_glob_and_relative(self):
        old = os.environ.get("HOME")
        os.environ["HOME"] = str(self.dir)
        try:
            self.write("config.d/b", "bindsym Mod4+b splith\n")
            self.write("config.d/a", "bindsym Mod4+a focus parent\n")
            self.write("extra", "bindsym Mod4+e layout toggle split\n")
            rows = kh.bindings(self.write("config", "include $HOME/config.d/*\ninclude extra\n"))
        finally:
            os.environ["HOME"] = old
        self.assertEqual([r[1] for r in rows], ["Super+A", "Super+B", "Super+E"])

    def test_flag_with_a_value(self):
        rows = self.rows("bindsym --input-device=1:1:AT_keyboard --locked Mod4+x exec kitty\n")
        self.assertEqual(rows, [("default", "Super+X", "kitty")])

    def test_include_with_several_paths(self):
        self.write("one", "bindsym Mod4+1 kill\n")
        self.write("two words", "bindsym Mod4+2 kill\n")
        rows = kh.bindings(self.write("config", 'include one "two words"\n'))
        self.assertEqual([r[1] for r in rows], ["Super+1", "Super+2"])

    def test_continuation_lines(self):
        rows = self.rows("bindsym Mod4+c exec one \\\n    two\n")
        self.assertEqual(rows[0][2], "one two")

    def test_script_paths_shortened(self):
        rows = self.rows("bindsym Mod4+f1 exec ~/.config/sway/scripts/lock.sh\n")
        self.assertEqual(rows[0][2], "lock.sh")

    def test_include_cycle_terminates(self):
        self.write("other", "include config\nbindsym Mod4+o kill\n")
        rows = kh.bindings(self.write("config", "include other\n"))
        self.assertEqual(len(rows), 1)


class RepoConfigTest(unittest.TestCase):
    """The repo's own sway package, read as the live desktop reads it."""

    def test_every_bind_line_in_the_repo_is_listed(self):
        sway = REPO / "sway/.config/sway"
        old = os.environ.get("HOME")
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / ".config").mkdir()
            (Path(home) / ".config/sway").symlink_to(sway)
            os.environ["HOME"] = home
            try:
                rows = kh.bindings(Path(home) / ".config/sway/config")
            finally:
                os.environ["HOME"] = old
        # Count what a reader of the files would count: single-line binds,
        # plus every non-comment, non-brace line inside a bind block.
        expected, inside = 0, False
        for f in sorted((sway / "config.d").iterdir()):
            for line in f.read_text().splitlines():
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith(("bindsym", "bindcode")) and s.endswith("{"):
                    inside = True
                elif s == "}":
                    inside = False
                elif inside or s.startswith(("bindsym ", "bindcode ")):
                    expected += 1
        self.assertGreater(expected, 50)
        self.assertEqual(len(rows), expected)
        self.assertIn(("default", "Super+Return", "kitty"), rows)
        self.assertIn(("default", "Super+D", "fuzzel"), rows)


if __name__ == "__main__":
    unittest.main()
