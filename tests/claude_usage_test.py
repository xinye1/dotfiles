#!/usr/bin/env python3
"""Tests for waybar/.config/waybar/scripts/claude_usage.py (stdlib unittest)."""
import importlib.util
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "claude_usage", REPO / "waybar/.config/waybar/scripts/claude_usage.py")
cu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cu)

# Deterministic local-midnight bucketing regardless of the machine's zone.
os.environ["TZ"] = "UTC"
time.tzset()

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)


class FormatTest(unittest.TestCase):
    def test_pango_escape(self):
        self.assertEqual(cu.pango_escape("A&B <x>"), "A&amp;B &lt;x&gt;")

    def test_humanize_caps_at_six_chars(self):
        cases = {0: "0", 999: "999", 7900: "7.9K", 7_900_000: "7.9M",
                 141_800_000: "141.8M", 999_940_000: "999.9M",
                 999_990_000: "1000M", 1_000_000_000: "1.0B"}
        for n, want in cases.items():
            self.assertEqual(cu.humanize(n), want)
            self.assertLessEqual(len(cu.humanize(n)), 6)

    def test_countdown(self):
        self.assertEqual(cu.countdown("2026-08-22T15:13:00+00:00", NOW), "3h 13m")
        self.assertEqual(cu.countdown("2026-08-27T10:00:00+00:00", NOW), "4d 22h")
        self.assertEqual(cu.countdown("2026-08-22T12:05:00+00:00", NOW), "5m")
        self.assertEqual(cu.countdown("2026-08-22T11:00:00+00:00", NOW), "now")
        self.assertEqual(cu.countdown(None, NOW), "")
        self.assertEqual(cu.countdown("garbage", NOW), "")

    def test_model_display(self):
        self.assertEqual(cu.model_display("claude-fable-5"), "Fable 5")
        self.assertEqual(cu.model_display("claude-opus-5"), "Opus 5")
        self.assertEqual(cu.model_display("claude-sonnet-5"), "Sonnet 5")
        self.assertEqual(cu.model_display("claude-haiku-4-5-20251001"), "Haiku 4.5")
        # Unknown ids prettified, date suffix dropped, version dotted.
        self.assertEqual(cu.model_display("claude-opus-4-1-20250805"), "Opus 4.1")


class ThemeTest(unittest.TestCase):
    def test_loads_roles_from_env_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "theme.gen.env"
            p.write_text("# comment\nBG=#282828\nWARNING=#fe8019\nNOISE\n")
            theme = cu.load_theme(p)
        self.assertEqual(theme["bg"], "#282828")
        self.assertEqual(theme["warning"], "#fe8019")
        # Roles missing from the file keep the named-colour fallback.
        self.assertEqual(theme["critical"], "red")

    def test_missing_file_falls_back_entirely(self):
        theme = cu.load_theme("/nonexistent/theme.gen.env")
        self.assertEqual(theme, cu.FALLBACK_THEME)


if __name__ == "__main__":
    unittest.main(verbosity=2)
