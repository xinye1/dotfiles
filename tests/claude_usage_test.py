#!/usr/bin/env python3
"""Tests for waybar/.config/waybar/scripts/claude_usage.py (stdlib unittest)."""
import importlib.util
import io
import json as jsonlib
import os
import tempfile
import time
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

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

    def test_ignores_unknown_keys(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "theme.gen.env"
            p.write_text("DESKTOP=#1d2021\nPAPIRUS_FOLDER=yellow\nGTK_THEME_NAME=Colloid\n")
            theme = cu.load_theme(p)
        self.assertEqual(theme["desktop"], "#1d2021")
        self.assertNotIn("papirus_folder", theme)
        self.assertNotIn("gtk_theme_name", theme)
        self.assertEqual(len(theme), 13)


LIMITS = [
    {"kind": "session", "group": "session", "percent": 44, "severity": "normal",
     "resets_at": "2026-08-22T15:13:00+00:00", "scope": None, "is_active": False},
    {"kind": "weekly_all", "group": "weekly", "percent": 41,
     "resets_at": "2026-08-27T10:00:00+00:00", "scope": None, "is_active": False},
    {"kind": "weekly_scoped", "group": "weekly", "percent": 70,
     "resets_at": "2026-08-27T10:00:00+00:00",
     "scope": {"model": {"display_name": "Fable"}}, "is_active": True},
]


def fake_urlopen(payload):
    def opener(req, timeout=None):
        assert req.get_header("Authorization") == "Bearer tok"
        assert timeout == cu.FETCH_TIMEOUT
        body = io.BytesIO(jsonlib.dumps(payload).encode())
        return mock.MagicMock(__enter__=lambda s: body, __exit__=mock.MagicMock())
    return opener


class CredsTest(unittest.TestCase):
    def creds_file(self, td, expires_ms):
        p = Path(td) / ".credentials.json"
        p.write_text(jsonlib.dumps({"claudeAiOauth": {
            "accessToken": "tok", "expiresAt": expires_ms,
            "subscriptionType": "max", "rateLimitTier": "max_20x"}}))
        return p

    def test_valid_token(self):
        with tempfile.TemporaryDirectory() as td:
            tok, err, meta = cu.read_credentials(self.creds_file(td, 2e12), 1e9)
        self.assertEqual((tok, err), ("tok", None))
        self.assertEqual(meta["rateLimitTier"], "max_20x")

    def test_expired_token(self):
        with tempfile.TemporaryDirectory() as td:
            tok, err, _ = cu.read_credentials(self.creds_file(td, 1000), 1e9)
        self.assertIsNone(tok)
        self.assertEqual(err, "token expired")

    def test_missing_file(self):
        tok, err, meta = cu.read_credentials("/nonexistent", 0)
        self.assertIsNone(tok)
        self.assertEqual(err, "not logged in")
        self.assertEqual(meta, {})


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.creds = Path(self.td.name) / ".credentials.json"
        self.creds.write_text(jsonlib.dumps(
            {"claudeAiOauth": {"accessToken": "tok", "expiresAt": 2e12}}))

    def tearDown(self):
        self.td.cleanup()

    def test_fetch_stores_limits(self):
        st = {}
        cu.refresh_limits(st, self.creds, False, 1000.0,
                          urlopen=fake_urlopen({"limits": LIMITS}))
        self.assertEqual(st["limits"], LIMITS)
        self.assertEqual(st["limits_fetched_at"], 1000.0)
        self.assertIsNone(st["limits_error"])

    def test_ttl_skips_fetch(self):
        st = {"limits": LIMITS, "limits_fetched_at": 900.0, "limits_error": None}
        boom = mock.MagicMock(side_effect=AssertionError("must not fetch"))
        cu.refresh_limits(st, self.creds, False, 1000.0, urlopen=boom)  # 100s < 300s
        boom.assert_not_called()

    def test_force_bypasses_ttl_but_debounces(self):
        st = {"limits": [], "limits_fetched_at": 990.0, "limits_forced_at": 995.0}
        boom = mock.MagicMock(side_effect=AssertionError("must not fetch"))
        cu.refresh_limits(st, self.creds, True, 1000.0, urlopen=boom)  # 5s < 30s
        boom.assert_not_called()
        cu.refresh_limits(st, self.creds, True, 1030.0,
                          urlopen=fake_urlopen({"limits": LIMITS}))  # 35s ≥ 30s
        self.assertEqual(st["limits"], LIMITS)
        self.assertEqual(st["limits_forced_at"], 1030.0)

    def test_failure_keeps_stale_data_and_age(self):
        st = {"limits": LIMITS, "limits_fetched_at": 400.0, "limits_error": None}
        err = urllib.error.URLError("dns")
        cu.refresh_limits(st, self.creds, False, 1000.0,
                          urlopen=mock.MagicMock(side_effect=err))
        self.assertEqual(st["limits"], LIMITS)          # old data kept
        self.assertEqual(st["limits_fetched_at"], 400.0)  # age stays honest
        self.assertIn("network", st["limits_error"])

    def test_expired_token_short_circuits(self):
        self.creds.write_text(jsonlib.dumps(
            {"claudeAiOauth": {"accessToken": "tok", "expiresAt": 1}}))
        st = {"limits": LIMITS, "limits_fetched_at": 400.0}
        boom = mock.MagicMock(side_effect=AssertionError("must not fetch"))
        cu.refresh_limits(st, self.creds, False, 1000.0, urlopen=boom)
        self.assertEqual(st["limits_error"], "token expired")
        boom.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
