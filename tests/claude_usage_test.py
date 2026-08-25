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
from datetime import datetime, timedelta, timezone
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


def set_tz(name):
    """Switch the process zone, or clear it when `name` is None.

    tzset() is process-global and the whole suite shares one process, so a test
    that switches zone registers an addCleanup with the AMBIENT value before
    switching — never with the literal "UTC". The two happen to be the same
    today because of the pin above; capturing keeps that a fact about the pin
    rather than something each call site has to restate correctly.
    """
    if name is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = name
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

    def test_countdown_non_string_resets_at_from_corrupted_state(self):
        # fetch_limits() always coerces resets_at to str-or-None, so this
        # shape can only reach countdown() via a corrupted or hand-edited
        # state.json -- main() only checks the top-level object is a dict,
        # never what's nested inside it. A truthy non-string used to fail
        # even earlier than the naive-timestamp case above: `resets_at
        # .replace(...)` raised AttributeError, which the ValueError/
        # TypeError except did not catch, so it escaped render() and main()
        # the same way and for the same reason -- the crash precedes the
        # state write, so the TTL never starts and every tick re-crashes.
        self.assertEqual(cu.countdown(1750000000, NOW), "")

    def test_countdown_dict_or_list_resets_at_from_corrupted_state(self):
        self.assertEqual(cu.countdown({"x": 1}, NOW), "")
        self.assertEqual(cu.countdown(["a"], NOW), "")

    def test_model_display(self):
        self.assertEqual(cu.model_display("claude-fable-5"), "Fable 5")
        self.assertEqual(cu.model_display("claude-opus-5"), "Opus 5")
        self.assertEqual(cu.model_display("claude-sonnet-5"), "Sonnet 5")
        self.assertEqual(cu.model_display("claude-haiku-4-5-20251001"), "Haiku 4.5")
        # Unknown ids prettified, date suffix dropped, version dotted.
        self.assertEqual(cu.model_display("claude-opus-4-1-20250805"), "Opus 4.1")

    def test_title_case_rescues_acronyms_from_str_title(self):
        # str.title() renders this "Default Claude Ai", which reads as a typo
        # in the tooltip header.
        self.assertEqual(cu.title_case("default_claude_ai"), "Default Claude AI")
        self.assertEqual(cu.title_case("pro"), "Pro")
        # "Max 20x", not str.title()'s "Max 20X": .title() capitalises the
        # first letter of every alphanumeric run, so it was already mangling
        # the multiplier, which Anthropic writes lowercase. Per-word
        # .capitalize() leaves a word starting with a digit alone.
        self.assertEqual(cu.title_case("max_20x"), "Max 20x")
        # Splitting on whitespace, not on "_", so a doubled separator cannot
        # produce an empty word (and "".capitalize() cannot leak a stray space).
        self.assertEqual(cu.title_case("a__b"), "A B")
        self.assertEqual(cu.title_case(""), "")


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
        self.assertEqual(len(theme), 14)

    def test_dim_is_a_role_the_env_file_can_set(self):
        # `dim` is the newest role and the one the tooltip's secondary text
        # hangs on; if theme.gen.env.tmpl ever stops emitting DIM this falls
        # back to a named colour rather than a palette one, silently.
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "theme.gen.env"
            p.write_text("DIM=#a0a8b6\n")
            theme = cu.load_theme(p)
        self.assertEqual(theme["dim"], "#a0a8b6")
        self.assertNotEqual(theme["dim"], theme["muted"])


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
        # the ambient zone on the way out, captured BEFORE the switch so a
        # failed assertion below cannot leak Auckland into every later test.
        self.addCleanup(set_tz, os.environ.get("TZ"))
        set_tz("Pacific/Auckland")
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

    @staticmethod
    def _break_scan_file(bad_path):
        # chmod 000 does nothing to open() as root -- the locked transcript
        # reads successfully and these tests would fail even though
        # scan_jsonl() is correct. Patching _scan_file to raise for exactly
        # one path exercises the same OSError boundary without depending on
        # filesystem permissions (or who the test process runs as), and the
        # side_effect still calls the real implementation for every other
        # path so its behaviour isn't otherwise faked.
        real_scan_file = cu._scan_file

        def side_effect(path, *args, **kwargs):
            if path == str(bad_path):
                raise PermissionError(13, "Permission denied", path)
            return real_scan_file(path, *args, **kwargs)
        return mock.patch.object(cu, "_scan_file", side_effect=side_effect)

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
        with contextlib.redirect_stderr(io.StringIO()), \
             self._break_scan_file(locked):
            st = self.scan({})
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
        with contextlib.redirect_stderr(io.StringIO()), \
             self._break_scan_file(f):
            self.scan(st)
        self.assertEqual(st["files"][str(f)], before)
        self.scan(st)
        self.assertEqual(st["days"]["2026-08-22"],
                         {"claude-fable-5": 100, "claude-opus-5": 100})


class PaceMarkTest(unittest.TestCase):
    """Where `now` sits inside each limit's OWN window, as a bar cell index."""

    @staticmethod
    def resets_in(seconds):
        return (NOW + timedelta(seconds=seconds)).isoformat()

    def test_marker_walks_the_five_hour_session_window(self):
        # NOW is fixed, so the marker is a pure function of what is left of the
        # window — the payload carries no start time, only `resets_at`.
        cases = {5 * 3600: 0,                # nothing elapsed yet: first cell
                 2.5 * 3600: 8,              # halfway: ninth of sixteen
                 3600: 12,                   # 4h of the 5h gone
                 0: cu.BAR_CELLS - 1}        # fully elapsed: last cell, not past
        for remaining, want in cases.items():
            with self.subTest(remaining=remaining):
                self.assertEqual(
                    cu.pace_mark("session", self.resets_in(remaining), NOW), want)

    def test_both_weekly_kinds_use_a_seven_day_window(self):
        cases = {7 * 86400: 0, 3.5 * 86400: 8, 0: cu.BAR_CELLS - 1}
        for kind in ("weekly_all", "weekly_scoped"):
            for remaining, want in cases.items():
                with self.subTest(kind=kind, remaining=remaining):
                    self.assertEqual(
                        cu.pace_mark(kind, self.resets_in(remaining), NOW), want)

    def test_fraction_clamped_at_both_ends(self):
        # A reset already in the past, and one further out than the window is
        # long (clock skew, or the API quietly changing a window's length):
        # both must still land on a real cell rather than off either end.
        self.assertEqual(cu.pace_mark("session", self.resets_in(-99999), NOW),
                         cu.BAR_CELLS - 1)
        self.assertEqual(cu.pace_mark("session", self.resets_in(99999), NOW), 0)

    def test_naive_timestamp_read_as_utc(self):
        # countdown()'s discipline, for countdown()'s reason: the endpoint is
        # undocumented and free to drop the zone, and it speaks UTC.
        self.assertEqual(cu.pace_mark("session", "2026-08-22T14:30:00", NOW), 8)
        self.assertEqual(cu.pace_mark("weekly_all", "2026-08-26T00:00:00", NOW), 8)

    def test_trailing_z_timestamp_parses_the_same_as_an_offset(self):
        # "Z" is the shape the endpoint actually sends; countdown() handles it
        # by turning it into "+00:00" before fromisoformat, and pace_mark()
        # shares that path. It must land on exactly the same cell as the
        # naive form above and the explicit-offset form -- three spellings of
        # the same instant, one answer.
        aware = cu.pace_mark("session", "2026-08-22T14:30:00+00:00", NOW)
        self.assertEqual(cu.pace_mark("session", "2026-08-22T14:30:00Z", NOW), aware)
        self.assertEqual(aware, 8)

    def test_no_marker_when_resets_at_is_unusable(self):
        # Missing, empty, unparseable, or the wrong type entirely (only a
        # corrupted state.json can produce the last — fetch_limits coerces to
        # str-or-None). Every one of them means no marker, never a crash.
        for resets_at in (None, "", "garbage", 1750000000, {"x": 1}, ["a"],
                          b"2026-08-22T14:30:00Z"):
            with self.subTest(resets_at=resets_at):
                self.assertIsNone(cu.pace_mark("session", resets_at, NOW))

    def test_no_marker_for_a_window_of_unknown_length(self):
        # An API that adds a fourth limit type must cost the three that work
        # nothing. The unhashable kinds are the drifted-JSON case: a bare
        # LIMIT_WINDOWS.get(kind) would raise TypeError on them.
        for kind in ("mystery_window", "", None, 7, ["session"], {"k": "v"}):
            with self.subTest(kind=kind):
                self.assertIsNone(cu.pace_mark(kind, self.resets_in(600), NOW))

    def test_marker_does_not_move_with_the_local_zone(self):
        # Unlike the day buckets, this arithmetic is entirely in aware UTC: a
        # user in Auckland must see the marker in the same cell as one in
        # London. tzset() is process-global and the suite shares one process,
        # so the ambient zone is captured BEFORE the switch, not after the
        # assert.
        self.addCleanup(set_tz, os.environ.get("TZ"))
        set_tz("Pacific/Auckland")
        self.assertEqual(
            cu.pace_mark("session", self.resets_in(2.5 * 3600), NOW), 8)


class BarWidthTest(unittest.TestCase):
    """The bar is exactly BAR_CELLS *visible* characters, in every case there is.

    plain_len() column-aligns the entire tooltip, so a bar that renders 15 or
    17 visible cells silently shifts that one row's percent and countdown out
    of line with its neighbours. It is the failure the marker invites most
    easily, because a marker that INSERTS rather than replaces looks perfectly
    correct on its own row.
    """
    COLOR = cu.FALLBACK_THEME["fg_bright"]

    def marks(self):
        live = [cu.pace_mark("session", (NOW + timedelta(hours=h)).isoformat(),
                             NOW) for h in (0, 1, 2, 3, 4, 5)]
        # Every fallback path, each of which yields None:
        fallbacks = [cu.pace_mark(*a, NOW) for a in (
            ("mystery_window", (NOW + timedelta(hours=1)).isoformat()),
            (["session"], (NOW + timedelta(hours=1)).isoformat()),
            ("session", None), ("session", "garbage"), ("session", 17))]
        self.assertEqual(fallbacks, [None] * 5)
        # ...plus positions off either end of the bar, which cells() must
        # refuse even though pace_mark() cannot currently produce them.
        return live + fallbacks + [None, -1, 16, 99]

    def test_every_percent_and_marker_combination(self):
        for pct in (-5, 0, 0.4, 3.1, 12.5, 40, 50, 64, 69.6, 70, 89, 89.6,
                    99.9, 100, 250):
            for mark in self.marks():
                with self.subTest(pct=pct, mark=mark):
                    bar = cu.cells(pct, mark, self.COLOR)
                    self.assertEqual(cu.plain_len(bar), cu.BAR_CELLS)
                    self.assertEqual(
                        cu.PACE_MARK in bar,
                        mark is not None and 0 <= mark < cu.BAR_CELLS)
                    # Uncoloured is the same bar minus the nested span.
                    self.assertEqual(cu.plain_len(cu.cells(pct, mark)),
                                     cu.BAR_CELLS)

    def test_width_invariant_for_every_cell_index(self):
        # The sweep above only exercises the handful of cells pace_mark()
        # actually lands on for those inputs. The invariant cells() promises
        # is unconditional -- every one of the sixteen real cell indices, not
        # just the ones a particular resets_at happens to produce -- so cover
        # 0..BAR_CELLS-1 explicitly, on top of None and the out-of-range marks.
        pcts = (0, 0.4, 12.5, 40, 50, 69.6, 70, 89.6, 99.9, 100)
        marks = list(range(cu.BAR_CELLS)) + [None, -1, 16, 99]
        for pct in pcts:
            for mark in marks:
                with self.subTest(pct=pct, mark=mark):
                    self.assertEqual(
                        cu.plain_len(cu.cells(pct, mark, self.COLOR)), cu.BAR_CELLS)

    def test_marker_count_invariant_holds_for_every_cell(self):
        # Generic form of "replaces, never inserts": one PACE_MARK exactly,
        # and the fill/empty/marker counts always sum to BAR_CELLS -- whether
        # the marker lands inside the filled run or the empty track.
        for pct in (0, 25, 50, 75, 100):
            for mark in range(cu.BAR_CELLS):
                with self.subTest(pct=pct, mark=mark):
                    bar = cu.cells(pct, mark, self.COLOR)
                    self.assertEqual(bar.count(cu.PACE_MARK), 1)
                    self.assertEqual(
                        bar.count("█") + bar.count("░") + bar.count(cu.PACE_MARK),
                        cu.BAR_CELLS)

    def test_marker_inside_the_fill_takes_the_bar_colour_as_background(self):
        # PACE_MARK is a thin stroke on an otherwise empty cell. Landing it in
        # the middle of a run of solid blocks would let the tooltip background
        # show through either side, reading as a notch bitten out of the bar
        # instead of a line drawn across it, so that one cell is painted in the
        # fill colour behind the stroke.
        fill = cu.FALLBACK_THEME["success"]
        bar = cu.cells(80, 6, self.COLOR, fill)          # 80% = 13 filled
        self.assertIn(f'bgcolor="{fill}"', bar)
        self.assertEqual(cu.plain_len(bar), cu.BAR_CELLS)

    def test_marker_past_the_fill_is_tinted_not_filled(self):
        # The ░ track is still textured bar colour, so an unpainted cell notches
        # it exactly as it notches the █ run. It gets the fill colour too, but
        # at ░'s own density — opaque out here would colour unused capacity as
        # used, which is the one lie this bar must not tell.
        fill = cu.FALLBACK_THEME["success"]
        bar = cu.cells(20, 12, self.COLOR, fill)         # 20% = 3 filled
        self.assertIn(f'bgcolor="{fill}"', bar)
        self.assertIn('bgalpha="25%"', bar)
        self.assertEqual(cu.plain_len(bar), cu.BAR_CELLS)

    def test_the_fill_edge_decides_opaque_versus_tinted(self):
        # The marker at index == filled is the FIRST unfilled cell, so it is
        # already past the fill and must be tinted; index filled-1 is the last
        # block and must be opaque. Off-by-one here either notches the bar or
        # overstates usage by a cell.
        fill = cu.FALLBACK_THEME["success"]
        for pct in (25, 50, 75):
            filled = round(pct * cu.BAR_CELLS / 100)
            with self.subTest(pct=pct):
                self.assertNotIn("bgalpha",
                                 cu.cells(pct, filled - 1, self.COLOR, fill))
                self.assertIn("bgalpha",
                              cu.cells(pct, filled, self.COLOR, fill))

    def test_every_marked_cell_carries_a_background(self):
        # The gap is the bug, so no reachable cell may be left unpainted —
        # neither half of the bar, at any percentage.
        fill = cu.FALLBACK_THEME["success"]
        for pct in (0, 20, 53, 65, 89, 100):
            for mark in range(cu.BAR_CELLS):
                with self.subTest(pct=pct, mark=mark):
                    self.assertIn(f'bgcolor="{fill}"',
                                  cu.cells(pct, mark, self.COLOR, fill))

    def test_width_invariant_survives_the_background(self):
        # bgcolor rides inside the span tag, which plain_len() strips whole, so
        # it must not cost a visible cell anywhere on the bar.
        fill = cu.FALLBACK_THEME["success"]
        for pct in (0, 0.4, 12.5, 40, 50, 69.6, 70, 89.6, 99.9, 100):
            for mark in list(range(cu.BAR_CELLS)) + [None, -1, 16, 99]:
                with self.subTest(pct=pct, mark=mark):
                    self.assertEqual(
                        cu.plain_len(cu.cells(pct, mark, self.COLOR, fill)),
                        cu.BAR_CELLS)

    def test_omitting_the_fill_colour_leaves_the_markup_unpainted(self):
        # render() is the only caller that passes one; the default has to stay
        # a plain coloured span so every other caller and test is unaffected.
        self.assertNotIn("bgcolor", cu.cells(80, 6, self.COLOR))
        self.assertIn(cu.PACE_MARK, cu.cells(80, 6, self.COLOR))

    def test_marker_replaces_the_cell_it_lands_on(self):
        # 40% used is 6 filled cells; the rule at cell 5 takes over the last of
        # them, so the fill still reaches past it — usage ahead of the clock.
        self.assertEqual(cu.cells(40.0, 5), "█████│░░░░░░░░░░")
        # Behind the clock: same rule, now sitting in the empty track.
        self.assertEqual(cu.cells(40.0, 12), "██████░░░░░░│░░░")


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
            # The expectation has to ask for the same pace marker render()
            # drew (LIMITS[0] is a session limit with a live resets_at), and
            # for the same fill colour behind it, since a marker inside the
            # filled run is painted with it. What this asserts is the FILL
            # colour tracking the rounded percent, and the marker riding along
            # inside that span without disturbing it.
            mark = cu.pace_mark("session", LIMITS[0]["resets_at"], NOW)
            bar = cu.cells(percent, mark, cu.FALLBACK_THEME["fg_bright"],
                           want_color)
            self.assertIn(f'<span color="{want_color}">{bar}</span>',
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
        self.assertIn("Max", tip)                     # plan from creds_meta
        self.assertNotIn("<synthetic>", tip)

    def test_header_prefers_the_subscription_over_the_rate_limit_tier(self):
        # The design doc says `<subscriptionType/rateLimitTier>` and the code
        # had the two the wrong way round. It matters because rateLimitTier is
        # the constant `default_claude_ai` for everyone right now — no
        # information at all — while subscriptionType is the plan name.
        st = self.fresh_state(creds_meta={"subscriptionType": "pro",
                                          "rateLimitTier": "default_claude_ai"})
        tip = cu.render(st, cu.FALLBACK_THEME, NOW)["tooltip"]
        self.assertIn("· Pro", tip)
        self.assertNotIn("Default Claude", tip)

    def test_header_falls_back_to_the_tier_when_no_subscription(self):
        st = self.fresh_state(creds_meta={"rateLimitTier": "default_claude_ai"})
        tip = cu.render(st, cu.FALLBACK_THEME, NOW)["tooltip"]
        self.assertIn("· Default Claude AI", tip)     # not "Ai"

    def test_header_has_no_separator_without_creds_meta(self):
        st = self.fresh_state(creds_meta={})
        self.assertIn(f"<b>{cu.ICON} Claude Code</b>",
                      cu.render(st, cu.FALLBACK_THEME, NOW)["tooltip"])
        self.assertNotIn("·", cu.render(st, cu.FALLBACK_THEME,
                                        NOW)["tooltip"].split("\n")[0])

    def test_secondary_text_uses_dim_and_never_muted(self):
        """The whole role, across every branch that draws de-emphasised text.

        `muted` is a structural colour: it measures 1.87:1 against the GTK
        tooltip's own background under nord, below even the 3:1 large-text
        floor, which is what made the reset countdowns, day names and header
        subtitle unreadable rather than merely quiet. Asserting the invariant
        over the whole tooltip rather than the lines I happened to think of —
        a new `dim` line added later is covered without touching this test,
        and a `muted` one fails it immediately.
        """
        theme = dict(cu.FALLBACK_THEME, muted="MUTEDROLE", dim="DIMROLE")
        for name, st in (("populated", self.fresh_state()),
                         ("no limits", self.fresh_state(limits=[])),
                         ("stale", self.fresh_state(limits_error="HTTP 429")),
                         ("no days", self.fresh_state(days={}))):
            tip = cu.render(st, theme, NOW)["tooltip"]
            self.assertNotIn("MUTEDROLE", tip, msg=name)
            self.assertIn("DIMROLE", tip, msg=name)

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

    def test_non_string_reset_timestamp_still_renders(self):
        # The other half of the countdown() hardening: a corrupted state.json
        # can hand render() an int/dict/list where resets_at should be a str.
        # Before the isinstance guard this raised AttributeError out of
        # countdown(), out of render(), out of main() -- the same
        # no-self-heal failure as the naive-timestamp case above, from a
        # different shape.
        st = self.fresh_state()
        st["limits"] = [dict(LIMITS[0], percent=44, resets_at=1750000000)]
        out = cu.render(st, cu.FALLBACK_THEME, NOW)
        self.assertEqual(out["text"], f"{cu.ICON}\n44")

    def test_cells(self):
        self.assertEqual(cu.cells(0), "░" * 16)
        self.assertEqual(cu.cells(100), "█" * 16)
        self.assertEqual(cu.cells(50).count("█"), 8)

    def test_limit_rows_stay_column_aligned_around_the_marker(self):
        # One shared reset time and one shared label width, so every row must
        # come out at exactly the same plain width — including the unknown-kind
        # row, which gets no marker at all. A marker that inserted a 17th cell
        # instead of replacing one would make the three known kinds wider.
        resets = "2026-08-22T15:13:00+00:00"
        st = self.fresh_state(limits=[
            {"kind": "session", "percent": 40, "resets_at": resets},
            {"kind": "weekly_all", "percent": 64, "resets_at": resets},
            {"kind": "weekly_scoped", "percent": 89, "resets_at": resets,
             "scope": {"model": {"display_name": "Fable"}}},
            {"kind": "mystery_window", "percent": 12, "resets_at": resets},
        ])
        tip = cu.render(st, cu.FALLBACK_THEME, NOW)["tooltip"]
        rows = [ln for ln in tip.split("\n") if "%</b>" in ln]
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({cu.plain_len(r) for r in rows}), 1)
        self.assertEqual([r.count(cu.PACE_MARK) for r in rows], [1, 1, 1, 0])

    def test_marker_is_neutral_coloured_inside_the_fill_span(self):
        # fg_bright, never a status colour: the signal is the comparison
        # between rule and fill, so the rule must not carry a verdict of its
        # own — and it has to stay visible on both █ and ░.
        st = self.fresh_state(limits=[dict(LIMITS[0], percent=40.0)])
        tip = cu.render(st, cu.FALLBACK_THEME, NOW)["tooltip"]
        mark = cu.pace_mark("session", LIMITS[0]["resets_at"], NOW)
        self.assertEqual(mark, 5)          # 3h13m left of 5h ⇒ 35.7% elapsed
        fill = cu.FALLBACK_THEME["indicator"]
        bar = cu.cells(40.0, mark, cu.FALLBACK_THEME["fg_bright"], fill)
        self.assertIn(f'<span color="{fill}">{bar}</span>', tip)

    def test_legend_appears_only_when_a_marker_was_drawn(self):
        self.assertIn("ahead of pace",
                      cu.render(self.fresh_state(), cu.FALLBACK_THEME, NOW)["tooltip"])
        # Unknown kinds only: no markers on any row, so no key to explain.
        st = self.fresh_state(limits=[{"kind": "mystery_window", "percent": 12,
                                       "resets_at": "2026-08-22T15:13:00+00:00"}])
        tip = cu.render(st, cu.FALLBACK_THEME, NOW)["tooltip"]
        self.assertNotIn("ahead of pace", tip)
        self.assertNotIn(cu.PACE_MARK, tip)

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
