#!/usr/bin/env python3
"""Tests for waybar/.config/waybar/scripts/claude_usage.py (stdlib unittest)."""
import contextlib
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

    def test_countdown_naive_timestamp_read_as_utc(self):
        # The one shape that used to take the widget down for good. The usage
        # endpoint is undocumented, so it may drop the trailing "Z" at any
        # time; fromisoformat parses that happily and the subtraction against a
        # tz-aware `now` then raised TypeError, which the ValueError-only
        # except did not catch. It escaped render() and main() BEFORE the state
        # write, so limits_fetched_at never advanced, the TTL never started,
        # and the next tick re-fetched and re-crashed — a blank bar forever.
        self.assertEqual(cu.countdown("2026-08-22T15:13:00", NOW), "3h 13m")
        self.assertEqual(cu.countdown("2026-08-27T10:00:00", NOW), "4d 22h")
        self.assertEqual(cu.countdown("2026-08-22T11:00:00", NOW), "now")
        # Belt and braces: the widened except swallows the next shape drift
        # too, rather than blanking the widget over a tooltip countdown. Bytes
        # are the demonstration: they carry a `.replace`, so they reach the try
        # body and raise TypeError there instead of on an attribute lookup.
        self.assertEqual(cu.countdown(b"2026-08-22T15:13:00Z", NOW), "")

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
    # Explicit raises, not bare asserts: these checks must survive `python -O`.
    def opener(req, timeout=None):
        # urllib normalizes header names on STORAGE (add_header uses
        # str.capitalize()); get_header does a raw lookup, so
        # "Anthropic-beta" is the correct key for "anthropic-beta".
        if req.get_header("Authorization") != "Bearer tok":
            raise AssertionError("missing/wrong Authorization header")
        if req.get_header("Anthropic-beta") != "oauth-2025-04-20":
            raise AssertionError("missing/wrong anthropic-beta header")
        if timeout != cu.FETCH_TIMEOUT:
            raise AssertionError(f"timeout {timeout!r} != FETCH_TIMEOUT")
        body = io.BytesIO(jsonlib.dumps(payload).encode())
        # __exit__ must return False — a truthy MagicMock would make the
        # with-block suppress exceptions raised by the code under test.
        return mock.MagicMock(__enter__=lambda s: body,
                              __exit__=lambda *a: False)
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

    def test_ttl_skip_clears_a_stale_error(self):
        # A transient failure since the last SUCCESSFUL fetch must not keep the
        # "⚠ stale" banner up over data the TTL still calls current, so the
        # skip branch clears the error instead of latching it for ~300s.
        st = {"limits": LIMITS, "limits_fetched_at": 900.0,
              "limits_error": "network error"}
        boom = mock.MagicMock(side_effect=AssertionError("must not fetch"))
        cu.refresh_limits(st, self.creds, False, 1000.0, urlopen=boom)
        boom.assert_not_called()
        self.assertIsNone(st["limits_error"])
        self.assertEqual(cu.render(st, cu.FALLBACK_THEME, NOW)["class"], "warning")

    def test_genuine_errors_survive_the_ttl_clear(self):
        # Past the TTL the data really is stale: a failing retry must set the
        # error, and the clearing above must not have made that unreachable.
        st = {"limits": LIMITS, "limits_fetched_at": 400.0, "limits_error": None}
        cu.refresh_limits(st, self.creds, False, 1000.0,
                          urlopen=mock.MagicMock(
                              side_effect=urllib.error.URLError("dns")))
        self.assertEqual(st["limits_error"], "network error")
        # Credentials errors are persistent, not transient: still latched.
        self.creds.write_text(jsonlib.dumps(
            {"claudeAiOauth": {"accessToken": "tok", "expiresAt": 1}}))
        st = {"limits": LIMITS, "limits_fetched_at": 900.0, "limits_error": None}
        cu.refresh_limits(st, self.creds, False, 1000.0, urlopen=None)
        self.assertEqual(st["limits_error"], "token expired")

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

    def test_creds_meta_merges_rather_than_replaces(self):
        # read_credentials reports only the keys it found, so a later read
        # missing one must not drop the tier label already on the tooltip.
        self.creds.write_text(jsonlib.dumps({"claudeAiOauth": {
            "accessToken": "tok", "expiresAt": 2e12,
            "subscriptionType": "max", "rateLimitTier": "max_20x"}}))
        st = {}
        cu.refresh_limits(st, self.creds, False, 1000.0,
                          urlopen=fake_urlopen({"limits": LIMITS}))
        self.assertEqual(st["creds_meta"],
                         {"subscriptionType": "max", "rateLimitTier": "max_20x"})
        self.creds.write_text(jsonlib.dumps({"claudeAiOauth": {
            "accessToken": "tok", "expiresAt": 2e12, "subscriptionType": "pro"}}))
        cu.refresh_limits(st, self.creds, False, 2000.0,
                          urlopen=fake_urlopen({"limits": LIMITS}))
        self.assertEqual(st["creds_meta"],
                         {"subscriptionType": "pro", "rateLimitTier": "max_20x"})

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

    def test_drifted_limits_shape_survives_refresh_and_render(self):
        # A non-dict entry and a string `percent` in the API response must
        # not crash refresh_limits or render — coerce/drop, degrade never.
        st = {}
        payload = {"limits": [
            "not-a-dict",  # drifted shape: rejected, not crashed on
            {"kind": "session", "percent": "50",
             "resets_at": "2026-08-22T15:13:00+00:00", "scope": None},
        ]}
        cu.refresh_limits(st, self.creds, False, 1000.0,
                          urlopen=fake_urlopen(payload))
        self.assertIsNone(st["limits_error"])
        self.assertEqual(len(st["limits"]), 1)
        self.assertEqual(st["limits"][0]["percent"], 50.0)
        out = cu.render(st, cu.FALLBACK_THEME, NOW)
        self.assertEqual(out["text"], f"{cu.ICON}\n50")
        self.assertIn("50", out["tooltip"])


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

    def test_non_numeric_expires_at(self):
        # A string expiresAt must degrade to a stale reason, not raise
        # TypeError at the `/1000` comparison.
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / ".credentials.json"
            p.write_text(jsonlib.dumps({"claudeAiOauth": {
                "accessToken": "tok", "expiresAt": "soon"}}))
            tok, err, meta = cu.read_credentials(p, 0)
        self.assertIsNone(tok)
        self.assertIsNotNone(err)

    def test_failed_force_backs_off_signal_rerun(self):
        # A failed forced fetch must not let the signal-triggered normal run
        # (arriving ~1s later) make a second attempt — otherwise every click
        # during an outage costs one API call, bypassing the debounce.
        with tempfile.TemporaryDirectory() as td:
            creds = Path(td) / ".credentials.json"
            creds.write_text(jsonlib.dumps(
                {"claudeAiOauth": {"accessToken": "tok", "expiresAt": 2e12}}))
            st = {"limits": LIMITS, "limits_fetched_at": 400.0}
            failing = mock.MagicMock(side_effect=urllib.error.URLError("down"))
            cu.refresh_limits(st, creds, True, 1000.0, urlopen=failing)
            self.assertEqual(failing.call_count, 1)
            boom = mock.MagicMock(side_effect=AssertionError("must not fetch"))
            cu.refresh_limits(st, creds, False, 1001.0, urlopen=boom)
            boom.assert_not_called()
            # Once the attempt backoff (FORCE_DEBOUNCE) passes, retries resume.
            cu.refresh_limits(st, creds, False, 1035.0,
                              urlopen=fake_urlopen({"limits": LIMITS}))
            self.assertIsNone(st["limits_error"])


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

    @staticmethod
    def set_tz(name):
        os.environ["TZ"] = name
        time.tzset()

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

    def test_id_less_record_counted_once_across_a_rescan(self):
        # A record missing message.id or requestId has no natural dedup key,
        # and the byte offset is no protection: truncating the file resets it
        # to 0, so the same in-window line is read a second time. Its tokens
        # must still be counted exactly once, off the content-hash fallback.
        f = self.proj / "a.jsonl"
        rec = jsonlib.loads(
            usage_line("2026-08-22T10:00:00.000Z", "claude-fable-5", "m1", "r1"))
        del rec["requestId"]
        idless = jsonlib.dumps(rec) + "\n"
        keyed = usage_line("2026-08-22T10:00:00.000Z", "claude-opus-5", "m2", "r2")
        f.write_text(idless + keyed)
        st = self.scan({})
        self.assertEqual(st["days"]["2026-08-22"],
                         {"claude-fable-5": 100, "claude-opus-5": 100})
        # Rewrite shorter than before: size shrank, so the offset resets to 0
        # and the id-less line is re-read from the top of the file.
        f.write_text(idless)
        self.scan(st)
        self.assertEqual(st["days"]["2026-08-22"]["claude-fable-5"], 100)

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

    def test_malformed_line_does_not_poison_dedup(self):
        # A malformed line must not record its (id, requestId) as seen, or a
        # later well-formed duplicate would be silently dropped.
        f = self.proj / "a.jsonl"
        good = usage_line("2026-08-22T10:00:00.000Z", "claude-fable-5", "m1", "r1")
        bad = good.replace('"input_tokens": 100', '"input_tokens": "oops"')
        f.write_text(bad + good)
        st = self.scan({})
        self.assertEqual(st["days"]["2026-08-22"]["claude-fable-5"], 100)

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

    def test_day_buckets_follow_the_local_zone_not_utc(self):
        # TZ is pinned to UTC at import, so nothing else here exercises the
        # `dt.astimezone().date()` bucketing under a real offset. Auckland is
        # UTC+12 in August, so 22:00Z is already 10:00 the NEXT day locally and
        # the token bar must land on the local day the user was working.
        f = self.proj / "a.jsonl"
        f.write_text(usage_line("2026-08-21T22:00:00.000Z", "claude-fable-5", "m1", "r1"))
        self.assertEqual(sorted(self.scan({})["days"]), ["2026-08-21"])  # UTC control
        # tzset() is process-global and the suite shares one process: restore
        # the pin on the way out, registered BEFORE the switch so a failed
        # assertion below cannot leak Auckland into every later test.
        self.addCleanup(self.set_tz, "UTC")
        self.set_tz("Pacific/Auckland")
        st = self.scan({})  # fresh state: rescan from offset 0, empty seen-set
        self.assertEqual(sorted(st["days"]), ["2026-08-22"])
        self.assertEqual(st["days"]["2026-08-22"]["claude-fable-5"], 100)

    def test_wrong_shape_lines_skipped_offset_advances(self):
        # Wrong-shape lines that pass json.loads but not the expected shape
        # must be skipped (not crash the whole tick), and the offset must
        # still advance past them so the widget doesn't get stuck retrying
        # the same poisoned line forever.
        f = self.proj / "a.jsonl"
        ts = "2026-08-22T10:00:00.000Z"
        array_line = jsonlib.dumps(["usage", "oops"]) + "\n"  # top-level array
        list_usage_line = jsonlib.dumps({
            "parentUuid": "x",
            "message": {"id": "m-list", "model": "claude-fable-5",
                        "usage": [1, 2, 3]},  # list-valued usage
            "requestId": "r-list", "timestamp": ts,
        }) + "\n"
        string_tokens_line = jsonlib.dumps({
            "parentUuid": "x",
            "message": {"id": "m-str", "model": "claude-fable-5",
                        "usage": {"input_tokens": "100", "output_tokens": "0",
                                  "cache_creation_input_tokens": "0",
                                  "cache_read_input_tokens": "0"}},  # string tokens
            "requestId": "r-str", "timestamp": ts,
        }) + "\n"
        good_line = usage_line(ts, "claude-fable-5", "m-good", "r-good")
        f.write_text(array_line + list_usage_line + string_tokens_line + good_line)
        st = self.scan({})
        self.assertEqual(st["days"]["2026-08-22"]["claude-fable-5"], 100)
        self.assertEqual(st["files"][str(f)]["offset"], f.stat().st_size)

    def test_unreadable_file_costs_only_that_file(self):
        # ~/.claude is foreign, read-only territory (§9.23): the widget does
        # not own what is in there and cannot stop a file becoming unopenable.
        # os.stat is guarded, open() was not, so ONE bad file aborted the tick
        # and every other transcript's tokens went with it.
        good = self.proj / "good.jsonl"
        good.write_text(
            usage_line("2026-08-22T10:00:00.000Z", "claude-fable-5", "m1", "r1"))
        # Named to sort ahead of good.jsonl on any walk order, so the failure
        # lands BEFORE the file whose tokens must still be counted.
        locked = self.proj / "aaa-locked.jsonl"
        locked.write_text(
            usage_line("2026-08-22T10:00:00.000Z", "claude-opus-5", "m2", "r2"))
        os.chmod(locked, 0o000)
        with contextlib.redirect_stderr(io.StringIO()):
            st = self.scan({})
        os.chmod(locked, 0o600)
        self.assertEqual(st["days"]["2026-08-22"], {"claude-fable-5": 100})
        self.assertIn(str(good), st["files"])
        self.assertNotIn(str(locked), st["files"])

    def test_unreadable_file_keeps_its_offset_for_later(self):
        # The record must survive the failure, or a file that goes unreadable
        # for one tick would rescan from byte 0 when it comes back — and with
        # `seen` pruned at the 8-day horizon that is a real double-count risk.
        f = self.proj / "a.jsonl"
        f.write_text(
            usage_line("2026-08-22T10:00:00.000Z", "claude-fable-5", "m1", "r1"))
        st = self.scan({})
        before = dict(st["files"][str(f)])
        with f.open("a") as fh:  # grow it, so the next tick would want to read
            fh.write(usage_line("2026-08-22T11:00:00.000Z", "claude-opus-5",
                                "m2", "r2"))
        os.chmod(f, 0o000)
        with contextlib.redirect_stderr(io.StringIO()):
            self.scan(st)
        os.chmod(f, 0o600)
        self.assertEqual(st["files"][str(f)], before)
        self.scan(st)
        self.assertEqual(st["days"]["2026-08-22"],
                         {"claude-fable-5": 100, "claude-opus-5": 100})


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
        for percent, want in ((95, "critical"), (90, "critical"), (89, "warning"),
                              (70, "warning"), (69, "normal"), (10, "normal")):
            st["limits"] = [dict(LIMITS[0], percent=percent)]
            self.assertEqual(cu.render(st, cu.FALLBACK_THEME, NOW)["class"], want,
                             msg=f"percent={percent}")

    def test_thresholds_follow_the_rounded_number_not_the_float(self):
        # The bar shows int(round(percent)), so the class and the tooltip
        # colour must be decided on that same integer. Judging the raw float
        # printed "70%" in the normal colour and "90%" in warning.
        st = self.fresh_state()
        for percent, want_cls, want_color in (
                (69.6, "warning", cu.FALLBACK_THEME["warning"]),
                (89.6, "critical", cu.FALLBACK_THEME["critical"]),
                (69.4, "normal", cu.FALLBACK_THEME["indicator"]),
                (89.4, "warning", cu.FALLBACK_THEME["warning"])):
            st["limits"] = [dict(LIMITS[0], percent=percent)]
            out = cu.render(st, cu.FALLBACK_THEME, NOW)
            shown = str(int(round(percent)))
            self.assertEqual(out["text"], f"{cu.ICON}\n{shown}", msg=f"{percent}")
            self.assertEqual(out["class"], want_cls, msg=f"percent={percent}")
            # The bar's colour, on the exact bar — cells() still uses the float.
            self.assertIn(f'<span color="{want_color}">{cu.cells(percent)}</span>',
                          out["tooltip"], msg=f"percent={percent}")
            self.assertIn(f"<b>{shown:>3}%</b>", out["tooltip"], msg=f"{percent}")

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

    def test_naive_reset_timestamp_still_renders(self):
        # The user-visible half of the countdown fix: one limit row carrying a
        # timestamp with no zone must not take the whole widget with it. Before
        # the fix this raised out of render(), out of main(), and printed
        # nothing at all — waybar's module simply disappeared.
        st = self.fresh_state()
        st["limits"] = [dict(LIMITS[0], percent=44,
                             resets_at="2026-08-22T15:13:00")]
        out = cu.render(st, cu.FALLBACK_THEME, NOW)
        self.assertEqual(out["text"], f"{cu.ICON}\n44")
        self.assertIn("3h 13m", out["tooltip"])

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


class MainTest(unittest.TestCase):
    def test_end_to_end_against_fake_home(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            claude = home / ".claude" / "projects" / "p"
            claude.mkdir(parents=True)
            (home / ".claude" / ".credentials.json").write_text(jsonlib.dumps(
                {"claudeAiOauth": {"accessToken": "tok", "expiresAt": 2e12,
                                   "rateLimitTier": "max_20x"}}))
            (claude / "s.jsonl").write_text(
                usage_line(NOW.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                           "claude-fable-5", "m1", "r1"))
            env = {"HOME": str(home), "XDG_CACHE_HOME": str(home / ".cache")}
            buf = io.StringIO()
            with mock.patch.dict(os.environ, env), \
                 mock.patch.object(cu.urllib.request, "urlopen",
                                   fake_urlopen({"limits": LIMITS})), \
                 contextlib.redirect_stdout(buf):
                cu.main([])
            out = jsonlib.loads(buf.getvalue())
            self.assertEqual(out["text"], f"{cu.ICON}\n44\n41\n70")
            state = jsonlib.loads(
                (home / ".cache" / "claude-usage" / "state.json").read_text())
            self.assertEqual(state["limits"], LIMITS)
            self.assertIn("2026-08-22", state["days"])

    def test_non_dict_state_file_rebuilds(self):
        # state.json holding valid JSON that isn't an object must rebuild,
        # not crash the tick.
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / ".claude" / "projects").mkdir(parents=True)
            (home / ".claude" / ".credentials.json").write_text(jsonlib.dumps(
                {"claudeAiOauth": {"accessToken": "tok", "expiresAt": 2e12}}))
            cache = home / ".cache" / "claude-usage"
            cache.mkdir(parents=True)
            (cache / "state.json").write_text("[]")
            env = {"HOME": str(home), "XDG_CACHE_HOME": str(home / ".cache")}
            buf = io.StringIO()
            with mock.patch.dict(os.environ, env), \
                 mock.patch.object(cu.urllib.request, "urlopen",
                                   fake_urlopen({"limits": LIMITS})), \
                 contextlib.redirect_stdout(buf):
                cu.main([])
            out = jsonlib.loads(buf.getvalue())
            self.assertEqual(out["text"], f"{cu.ICON}\n44\n41\n70")


if __name__ == "__main__":
    unittest.main(verbosity=2)
