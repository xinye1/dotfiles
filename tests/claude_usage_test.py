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

    def test_force_debounce_survives_failure(self):
        # With an always-failing urlopen, two forced calls 5s apart should make exactly ONE attempt
        st = {}
        fail_mock = mock.MagicMock(side_effect=Exception("fail"))
        cu.refresh_limits(st, self.creds, True, 1000.0, urlopen=fail_mock)
        fail_mock.assert_called_once()  # first call attempts fetch
        self.assertEqual(st["limits_forced_at"], 1000.0)
        self.assertEqual(st["limits_error"], "network error")
        # Second call 5s later should be debounced (< 30s)
        boom = mock.MagicMock(side_effect=AssertionError("must not fetch"))
        cu.refresh_limits(st, self.creds, True, 1005.0, urlopen=boom)
        boom.assert_not_called()


class CredsShapeTest(unittest.TestCase):
    def test_non_dict_json_null(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / ".credentials.json"
            p.write_text("null")
            tok, err, meta = cu.read_credentials(p, 0)
        self.assertIsNone(tok)
        self.assertEqual(err, "not logged in")
        self.assertEqual(meta, {})

    def test_non_dict_json_array(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / ".credentials.json"
            p.write_text("[]")
            tok, err, meta = cu.read_credentials(p, 0)
        self.assertIsNone(tok)
        self.assertEqual(err, "not logged in")
        self.assertEqual(meta, {})

    def test_non_dict_json_string(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / ".credentials.json"
            p.write_text('"42"')
            tok, err, meta = cu.read_credentials(p, 0)
        self.assertIsNone(tok)
        self.assertEqual(err, "not logged in")
        self.assertEqual(meta, {})


def usage_line(ts, model, mid, rid, tokens=100):
    return jsonlib.dumps({
        "parentUuid": "x", "message": {
            "id": mid, "model": model,
            "usage": {"input_tokens": tokens, "output_tokens": 0,
                      "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0}},
        "requestId": rid, "timestamp": ts}) + "\n"


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.proj = Path(self.td.name) / "projects" / "p1"
        self.proj.mkdir(parents=True)
        self.now = NOW.timestamp()

    def tearDown(self):
        self.td.cleanup()

    def scan(self, st):
        cu.scan_jsonl(Path(self.td.name) / "projects", st, self.now)
        return st

    def test_within_file_duplicates_counted_once(self):
        # One line per content block, identical usage — the dominant mode.
        f = self.proj / "a.jsonl"
        f.write_text(usage_line("2026-08-22T10:00:00.000Z", "claude-fable-5", "m1", "r1") * 3)
        st = self.scan({})
        self.assertEqual(st["days"]["2026-08-22"]["claude-fable-5"], 100)

    def test_cross_file_duplicates_counted_once(self):
        (self.proj / "a.jsonl").write_text(
            usage_line("2026-08-22T10:00:00.000Z", "claude-fable-5", "m1", "r1"))
        (self.proj / "b.jsonl").write_text(
            usage_line("2026-08-22T10:00:00.000Z", "claude-fable-5", "m1", "r1"))
        st = self.scan({})
        self.assertEqual(st["days"]["2026-08-22"]["claude-fable-5"], 100)

    def test_offset_resume_and_unchanged_skip(self):
        f = self.proj / "a.jsonl"
        f.write_text(usage_line("2026-08-22T10:00:00.000Z", "claude-fable-5", "m1", "r1"))
        st = self.scan({})
        rec = st["files"][str(f)]
        self.assertEqual(rec["offset"], f.stat().st_size)
        # Append a new message; only it is aggregated on the next tick.
        with f.open("a") as fh:
            fh.write(usage_line("2026-08-22T11:00:00.000Z", "claude-opus-5", "m2", "r2"))
        self.scan(st)
        self.assertEqual(st["days"]["2026-08-22"],
                         {"claude-fable-5": 100, "claude-opus-5": 100})

    def test_shrunk_file_rescans_from_zero(self):
        f = self.proj / "a.jsonl"
        f.write_text(usage_line("2026-08-22T10:00:00.000Z", "claude-fable-5", "m1", "r1") * 2)
        st = self.scan({})
        f.write_text(usage_line("2026-08-22T10:00:00.000Z", "claude-opus-5", "m9", "r9"))
        self.scan(st)
        self.assertIn("claude-opus-5", st["days"]["2026-08-22"])

    def test_partial_trailing_line_deferred(self):
        f = self.proj / "a.jsonl"
        full = usage_line("2026-08-22T10:00:00.000Z", "claude-fable-5", "m1", "r1")
        f.write_text(full + '{"half": ')  # no trailing newline
        st = self.scan({})
        self.assertEqual(st["files"][str(f)]["offset"], len(full.encode()))
        self.assertEqual(st["days"]["2026-08-22"]["claude-fable-5"], 100)

    def test_synthetic_and_old_lines_skipped_and_pruned(self):
        f = self.proj / "a.jsonl"
        f.write_text(
            usage_line("2026-08-22T10:00:00.000Z", "<synthetic>", "m1", "r1")
            + usage_line("2026-08-01T10:00:00.000Z", "claude-fable-5", "m2", "r2"))
        st = {"days": {"2026-08-01": {"claude-fable-5": 5}},
              "seen": {"old|old": self.now - 9 * 86400}}
        self.scan(st)
        self.assertNotIn("<synthetic>", st.get("days", {}).get("2026-08-22", {}))
        self.assertNotIn("2026-08-01", st["days"])   # pruned past 8 days
        self.assertNotIn("old|old", st["seen"])      # seen-set pruned too

    def test_deleted_file_state_dropped(self):
        f = self.proj / "a.jsonl"
        f.write_text(usage_line("2026-08-22T10:00:00.000Z", "claude-fable-5", "m1", "r1"))
        st = self.scan({})
        f.unlink()
        self.scan(st)
        self.assertEqual(st["files"], {})

    def test_same_size_different_content_rescans(self):
        # File rewritten in-place without size change: mtime changed but size unchanged.
        # Offset should reset to 0 and new content should be read.
        f = self.proj / "a.jsonl"
        line1 = usage_line("2026-08-22T10:00:00.000Z", "claude-opus-5", "m1", "rxx")
        line2 = usage_line("2026-08-22T10:00:00.000Z", "claude-fable-5", "m2", "r2")
        # Ensure lines have identical byte length for the test to be meaningful
        self.assertEqual(len(line1.encode()), len(line2.encode()),
                        msg="Test fixture: lines must have same byte length")
        f.write_text(line1)
        st = self.scan({})
        self.assertIn("claude-opus-5", st["days"]["2026-08-22"])
        self.assertNotIn("claude-fable-5", st["days"]["2026-08-22"])
        # Overwrite with different content, same size; force different mtime
        f.write_text(line2)
        t = self.now - 100  # mtime in the past but within the window
        os.utime(f, (t, t))
        self.scan(st)
        # Both models should now be in state (dedup prevents double-counting via seen set)
        self.assertIn("claude-fable-5", st["days"]["2026-08-22"])


class RenderTest(unittest.TestCase):
    def fresh_state(self, **over):
        st = {"limits": LIMITS, "limits_fetched_at": NOW.timestamp() - 60,
              "limits_error": None,
              "creds_meta": {"subscriptionType": "max", "rateLimitTier": "max_20x"},
              "days": {"2026-08-22": {"claude-fable-5": 57_700_000},
                       "2026-08-20": {"claude-opus-5": 256_200_000}}}
        st.update(over)
        return st

    def test_bar_text_stacks_all_limit_rows(self):
        out = cu.render(self.fresh_state(), cu.FALLBACK_THEME, NOW)
        self.assertEqual(out["text"], f"{cu.ICON}\n44\n41\n70")
        self.assertEqual(out["class"], "warning")  # worst = 70

    def test_class_thresholds(self):
        st = self.fresh_state()
        st["limits"] = [dict(LIMITS[0], percent=95)]
        self.assertEqual(cu.render(st, cu.FALLBACK_THEME, NOW)["class"], "critical")
        st["limits"] = [dict(LIMITS[0], percent=10)]
        self.assertEqual(cu.render(st, cu.FALLBACK_THEME, NOW)["class"], "normal")

    def test_stale_class_and_banner(self):
        out = cu.render(self.fresh_state(limits_error="HTTP 429"),
                        cu.FALLBACK_THEME, NOW)
        self.assertEqual(out["class"], "stale")
        self.assertIn("stale", out["tooltip"])
        self.assertIn("HTTP 429", out["tooltip"])

    def test_never_logged_in(self):
        out = cu.render({"limits_error": "not logged in"}, cu.FALLBACK_THEME, NOW)
        self.assertEqual(out["text"], f"{cu.ICON}\n–")
        self.assertEqual(out["class"], "stale")
        self.assertIn("not logged in", out["tooltip"])

    def test_tooltip_content_and_escaping(self):
        st = self.fresh_state()
        st["limits"] = [dict(LIMITS[2])]
        st["limits"][0]["scope"] = {"model": {"display_name": "Fab<le&"}}
        out = cu.render(st, cu.FALLBACK_THEME, NOW)
        tip = out["tooltip"]
        self.assertIn('face="JetBrainsMono Nerd Font"', tip)
        self.assertIn("Fab&lt;le&amp; Wk", tip)      # escaped label
        self.assertIn("TOKENS BY DAY", tip)
        self.assertIn("Today", tip)
        self.assertIn("57.7M", tip)
        self.assertIn("Opus 5", tip)                  # model chart
        self.assertIn("Max 20X", tip)                 # tier from creds_meta
        self.assertNotIn("<synthetic>", tip)

    def test_unknown_limit_kind_not_dropped(self):
        st = self.fresh_state()
        st["limits"] = [{"kind": "mystery_window", "percent": 12,
                         "resets_at": None, "scope": None}]
        out = cu.render(st, cu.FALLBACK_THEME, NOW)
        self.assertIn("mystery_window", out["tooltip"])
        self.assertEqual(out["text"], f"{cu.ICON}\n12")

    def test_cells(self):
        self.assertEqual(cu.cells(0), "░" * 16)
        self.assertEqual(cu.cells(100), "█" * 16)
        self.assertEqual(cu.cells(50).count("█"), 8)

    def test_tokens_by_model_respects_window(self):
        st = self.fresh_state()
        # Remove default days and add out-of-window data
        st["days"] = {
            "2026-08-15": {"claude-sonnet-5": 999_000_000},  # outside 7-day window
            "2026-08-22": {"claude-fable-5": 1_000},          # inside window
        }
        out = cu.render(st, cu.FALLBACK_THEME, NOW)
        tip = out["tooltip"]
        self.assertIn("Fable 5", tip)                         # in-window model appears
        self.assertNotIn("Sonnet 5", tip)                     # out-of-window model hidden


if __name__ == "__main__":
    unittest.main(verbosity=2)
