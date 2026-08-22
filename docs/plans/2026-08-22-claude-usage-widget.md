# Claude Usage Waybar Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `custom/claude` waybar module showing Claude Code limit percentages on the vertical bar, with a Quattro-style Pango tooltip (limits + reset countdowns, tokens by day, tokens by model) and click-to-force-refresh.

**Architecture:** One Python 3 stdlib-only script run by waybar every 300s (and on signal 8 after a click). It fetches the undocumented OAuth usage API (read-only credentials, TTL-guarded), incrementally aggregates `~/.claude/projects/**/*.jsonl` token usage via a persistent state file under an exclusive flock, and emits `{text, tooltip, class}` JSON.

**Tech Stack:** Python 3 stdlib (`urllib`, `fcntl`, `json`, `datetime`), waybar custom module, GTK CSS, GNU Stow repo conventions.

**Spec:** `docs/specs/2026-08-22-claude-usage-widget-design.md` (read it first; its review log `…-design.review.md` explains the sharp edges). Mockup: `docs/specs/2026-08-22-claude-usage-widget-mockup.html`.

## Global Constraints

- Python **stdlib only**; no third-party imports anywhere.
- **No hex colour literals** in any tracked file outside `tests/`, `docs/`, `*.md`, `*.tmpl`, `palettes.toml` — `tests/check_hex.py` (run by `tests/theme_test.sh`) scans everything else, including `.py`. Fallback colours must be Pango **named** colours.
- **Never write** to anything under `~/.claude/` — credentials are read-only; state lives in `~/.cache/claude-usage/`.
- Cadences (exact values): API cache TTL **300s**; `--refresh` debounce **30s**; HTTP timeout **5s**; scan/prune horizon **8 days**; charts show **7 days**.
- Icons (verified in the installed font's cmap 2026-08-22): `` U+EC82 = cod-claude, `` U+F0E2 = fa-undo (the pre-FA6 name of nf-fa-arrow_rotate_left, user-chosen reset icon); `⚠` U+26A0 also present. Tooltip body must be wrapped in `<span face="JetBrainsMono Nerd Font">`.
- Waybar module must be declared in `waybar/.config/waybar/config` **only** (never also in an included file — PLAYBOOK §9.12); `"exec-on-event": false` is mandatory; signal **8** (1 is taken).
- Thresholds: warning ≥ **70**, critical ≥ **90** — everywhere, including `statusline.py` (Task 7).
- Script filename is `claude_usage.py` (underscore — tests import it as a module).
- Commit style: `feat(waybar): …` / `fix(...): …` matching `git log`.
- All timestamps handled tz-aware; JSONL `timestamp` is UTC ISO (`…Z`); day bucketing is **local** midnight.

---

### Task 1: Script scaffold + formatting helpers

**Files:**
- Create: `waybar/.config/waybar/scripts/claude_usage.py`
- Create: `tests/claude_usage_test.py`

**Interfaces:**
- Produces: `pango_escape(s) -> str`, `humanize(n: int|float) -> str` (≤6 chars), `countdown(resets_at: str|None, now: datetime) -> str`, `model_display(model_id: str) -> str`, and module constants `ICON`, `ICON_RESET`, `API_TTL=300`, `FORCE_DEBOUNCE=30`, `FETCH_TIMEOUT=5`, `WINDOW_DAYS=8`, `BAR_CELLS=16`, `FACE`. Later tasks add functions to this same file; tests import it via `importlib`.

- [ ] **Step 1: Write the failing tests**

`tests/claude_usage_test.py`:

```python
#!/usr/bin/env python3
"""Tests for waybar/.config/waybar/scripts/claude_usage.py (stdlib unittest)."""
import importlib.util
import os
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 tests/claude_usage_test.py`
Expected: FAIL at import (`FileNotFoundError` — script doesn't exist yet).

- [ ] **Step 3: Write the scaffold + helpers**

`waybar/.config/waybar/scripts/claude_usage.py`:

```python
#!/usr/bin/env python3
"""Claude Code usage widget for waybar: limits, reset countdowns, token charts.

Design: docs/specs/2026-08-22-claude-usage-widget-design.md. Read-only on
~/.claude; all state in ~/.cache/claude-usage/. Stdlib only.
"""
import fcntl
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ICON = ""        # nf-cod-claude — verified against the installed font's cmap
ICON_RESET = ""  # nf-fa-arrow_rotate_left, named fa-undo in this build (⟳ absent)
FACE = "JetBrainsMono Nerd Font"
API_URL = "https://api.anthropic.com/api/oauth/usage"
API_TTL = 300          # the endpoint rate-limits aggressively; never poll faster
FORCE_DEBOUNCE = 30    # click-spam must not be able to 429 the widget stale
FETCH_TIMEOUT = 5
WINDOW_DAYS = 8        # scan/prune horizon; charts render 7 of these
BAR_CELLS = 16

# Pango named colours only: tests/check_hex.py scans this file for hex literals.
FALLBACK_THEME = {
    "bg": "black", "surface": "black", "sel": "gray", "muted": "gray",
    "fg": "white", "fg_bright": "white", "accent": "yellow", "accent2": "orange",
    "indicator": "lightgreen", "critical": "red", "warning": "orange",
    "success": "green",
}

MODEL_NAMES = (
    ("claude-fable-5", "Fable 5"),
    ("claude-opus-5", "Opus 5"),
    ("claude-sonnet-5", "Sonnet 5"),
    ("claude-haiku-4-5", "Haiku 4.5"),
)


def pango_escape(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def humanize(n):
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            v = n / div
            s = f"{v:.1f}{suf}"
            return s if len(s) <= 6 else f"{v:.0f}{suf}"
    return str(int(n))


def countdown(resets_at, now):
    if not resets_at:
        return ""
    try:
        dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
    except ValueError:
        return ""
    mins = int((dt - now).total_seconds() // 60)
    if mins <= 0:
        return "now"
    d, h, m = mins // 1440, mins % 1440 // 60, mins % 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def model_display(model_id):
    for prefix, name in MODEL_NAMES:
        if model_id.startswith(prefix):
            return name
    parts = [p for p in model_id.removeprefix("claude-").split("-")
             if not (len(p) == 8 and p.isdigit())]  # drop date suffixes
    words = [p.capitalize() for p in parts if p.isalpha()]
    nums = [p for p in parts if not p.isalpha()]
    return " ".join(words + ([".".join(nums)] if nums else [])) or model_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/claude_usage_test.py`
Expected: all PASS (the length-guarded `humanize` collapses `1000.0M` to `1000M` while keeping `999.9M`).

- [ ] **Step 5: Make the script executable and commit**

```bash
chmod +x waybar/.config/waybar/scripts/claude_usage.py
git add waybar/.config/waybar/scripts/claude_usage.py tests/claude_usage_test.py
git commit -m "feat(waybar): claude usage widget scaffold + formatters"
```

---

### Task 2: Theme loading with guard-safe fallback

**Files:**
- Modify: `waybar/.config/waybar/scripts/claude_usage.py` (append)
- Modify: `tests/claude_usage_test.py` (append)

**Interfaces:**
- Produces: `load_theme(path: Path|str) -> dict[str, str]` — keys are the 13 lowercase role names; values `#hex` from `theme.gen.env` or Pango named colours from `FALLBACK_THEME`.

- [ ] **Step 1: Write the failing tests** (append to `tests/claude_usage_test.py`)

```python
import tempfile


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 tests/claude_usage_test.py`
Expected: `AttributeError: … has no attribute 'load_theme'`.

- [ ] **Step 3: Implement** (append to `claude_usage.py`)

```python
def load_theme(path):
    theme = dict(FALLBACK_THEME)
    try:
        text = Path(path).read_text()
    except OSError:
        return theme
    for line in text.splitlines():
        m = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(\S+)", line.strip())
        if m:
            theme[m.group(1).lower()] = m.group(2)
    return theme
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/claude_usage_test.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -u && git commit -m "feat(waybar): claude widget theme roles with named-colour fallback"
```

---

### Task 3: Credentials, API fetch, refresh policy

**Files:**
- Modify: `waybar/.config/waybar/scripts/claude_usage.py` (append)
- Modify: `tests/claude_usage_test.py` (append)

**Interfaces:**
- Produces:
  - `read_credentials(path, now_epoch) -> tuple[str|None, str|None, dict]` — `(token, error_reason, meta)`; `meta` has `subscriptionType`/`rateLimitTier` when readable.
  - `fetch_limits(token, urlopen=None) -> list` — raises on any failure; `urlopen` resolved at call time so tests can patch `cu.urllib.request.urlopen`.
  - `refresh_limits(st: dict, creds_path, force: bool, now_epoch: float, urlopen=None) -> None` — mutates `st` keys `limits`, `limits_fetched_at`, `limits_forced_at`, `limits_error`, `creds_meta`. On failure keeps old `limits` and old `limits_fetched_at` (data age stays honest) and sets `limits_error`.

- [ ] **Step 1: Write the failing tests** (append to `tests/claude_usage_test.py`)

```python
import io
import json as jsonlib
import urllib.error
from unittest import mock

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 tests/claude_usage_test.py`
Expected: `AttributeError` on `read_credentials` / `refresh_limits`.

- [ ] **Step 3: Implement** (append to `claude_usage.py`)

```python
def read_credentials(path, now_epoch):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None, "not logged in", {}
    oauth = data.get("claudeAiOauth") or {}
    meta = {k: oauth[k] for k in ("subscriptionType", "rateLimitTier") if oauth.get(k)}
    token = oauth.get("accessToken")
    if not token:
        return None, "not logged in", meta
    if (oauth.get("expiresAt") or 0) / 1000 <= now_epoch:
        return None, "token expired", meta
    return token, None, meta


def fetch_limits(token, urlopen=None):
    urlopen = urlopen or urllib.request.urlopen  # resolved at call time: patchable
    req = urllib.request.Request(API_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
    })
    with urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        data = json.load(resp)
    limits = data.get("limits")
    if not isinstance(limits, list):
        raise ValueError("no limits[] in response")
    return limits


def refresh_limits(st, creds_path, force, now_epoch, urlopen=None):
    token, err, meta = read_credentials(creds_path, now_epoch)
    if meta:
        st["creds_meta"] = meta
    if err:
        st["limits_error"] = err
        return
    if force:
        if now_epoch - st.get("limits_forced_at", 0) < FORCE_DEBOUNCE:
            return
    elif now_epoch - st.get("limits_fetched_at", 0) < API_TTL:
        return
    try:
        st["limits"] = fetch_limits(token, urlopen)
    except urllib.error.HTTPError as e:
        st["limits_error"] = f"HTTP {e.code}"
        print(f"claude_usage: {e}", file=sys.stderr)
    except Exception as e:  # URLError, timeout, bad JSON, missing limits[]
        st["limits_error"] = "network error"
        print(f"claude_usage: {e}", file=sys.stderr)
    else:
        st["limits_fetched_at"] = now_epoch
        if force:
            st["limits_forced_at"] = now_epoch
        st["limits_error"] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/claude_usage_test.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -u && git commit -m "feat(waybar): claude widget limits fetch, TTL + debounce, stale-not-crash"
```

---

### Task 4: Incremental JSONL aggregator

**Files:**
- Modify: `waybar/.config/waybar/scripts/claude_usage.py` (append)
- Modify: `tests/claude_usage_test.py` (append)

**Interfaces:**
- Produces: `scan_jsonl(projects_dir, st: dict, now_epoch: float) -> None` — mutates `st` keys `files` (`{path: {size, mtime, offset}}`), `seen` (`{"msgid|reqid": ts_epoch}`), `days` (`{"YYYY-MM-DD": {model_id: tokens}}`). Internal helper `_scan_file(path, offset, cutoff_epoch, cutoff_iso, seen, days) -> int` (new offset).

- [ ] **Step 1: Write the failing tests** (append to `tests/claude_usage_test.py`)

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 tests/claude_usage_test.py`
Expected: `AttributeError` on `scan_jsonl`.

- [ ] **Step 3: Implement** (append to `claude_usage.py`)

```python
_TS_RE = re.compile(rb'"timestamp"\s*:\s*"([^"]+)"')
_USAGE_KEYS = ("input_tokens", "output_tokens",
               "cache_creation_input_tokens", "cache_read_input_tokens")


def _scan_file(path, offset, cutoff_epoch, cutoff_iso, seen, days):
    with open(path, "rb") as f:
        f.seek(offset)
        for raw in f:
            if not raw.endswith(b"\n"):
                break  # partial trailing line: picked up next tick
            if b'"usage"' not in raw:
                offset += len(raw)
                continue
            # Cheap prescreen: the timestamp field sits near the END of Claude
            # Code's lines (after the potentially huge message object), and
            # zulu-ISO strings compare lexically.
            m = _TS_RE.search(raw, max(0, raw.rfind(b'"timestamp"')))
            if m and m.group(1).decode("utf-8", "replace") < cutoff_iso:
                offset += len(raw)
                continue
            offset += len(raw)
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            msg = obj.get("message") or {}
            usage, model, ts = msg.get("usage"), msg.get("model"), obj.get("timestamp")
            if not usage or not model or not ts or model == "<synthetic>":
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            ts_epoch = dt.timestamp()
            mid, rid = msg.get("id"), obj.get("requestId")
            if mid and rid:
                key = f"{mid}|{rid}"
                if key in seen:
                    continue
                seen[key] = ts_epoch
            if ts_epoch < cutoff_epoch:
                continue
            day = dt.astimezone().date().isoformat()
            per_day = days.setdefault(day, {})
            per_day[model] = per_day.get(model, 0) + sum(
                usage.get(k) or 0 for k in _USAGE_KEYS)
    return offset


def scan_jsonl(projects_dir, st, now_epoch):
    cutoff_epoch = now_epoch - WINDOW_DAYS * 86400
    cutoff_iso = datetime.fromtimestamp(
        cutoff_epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    files = st.setdefault("files", {})
    seen = st.setdefault("seen", {})
    days = st.setdefault("days", {})
    alive = set()
    for root, _dirs, names in os.walk(projects_dir):
        for name in names:
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(root, name)
            try:
                fst = os.stat(path)
            except OSError:
                continue
            if fst.st_mtime < cutoff_epoch:
                continue  # nothing written inside the window
            alive.add(path)
            rec = files.get(path)
            if rec and rec["size"] == fst.st_size and rec["mtime"] == fst.st_mtime:
                continue
            offset = rec["offset"] if rec and fst.st_size >= rec["offset"] else 0
            offset = _scan_file(path, offset, cutoff_epoch, cutoff_iso, seen, days)
            files[path] = {"size": fst.st_size, "mtime": fst.st_mtime,
                           "offset": offset}
    for path in list(files):
        if path not in alive:
            del files[path]
    for key, ts in list(seen.items()):
        if ts < cutoff_epoch:
            del seen[key]
    cutoff_day = datetime.fromtimestamp(cutoff_epoch).astimezone().date().isoformat()
    for day in list(days):
        if day < cutoff_day:
            del days[day]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/claude_usage_test.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -u && git commit -m "feat(waybar): claude widget incremental jsonl aggregation with global dedup"
```

---

### Task 5: Renderer (bar text, class, tooltip)

**Files:**
- Modify: `waybar/.config/waybar/scripts/claude_usage.py` (append)
- Modify: `tests/claude_usage_test.py` (append)

**Interfaces:**
- Produces: `render(st: dict, theme: dict, now: datetime) -> dict` with keys `text`, `tooltip`, `class`; helpers `limit_label(l: dict) -> str`, `cells(pct: float) -> str` (16-cell bar string).

- [ ] **Step 1: Write the failing tests** (append to `tests/claude_usage_test.py`)

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 tests/claude_usage_test.py`
Expected: `AttributeError` on `render` / `cells`.

- [ ] **Step 3: Implement** (append to `claude_usage.py`)

```python
def limit_label(l):
    kind = l.get("kind")
    if kind == "session":
        return "Session"
    if kind == "weekly_all":
        return "Weekly"
    if kind == "weekly_scoped":
        name = ((l.get("scope") or {}).get("model") or {}).get("display_name")
        return f"{name or 'Scoped'} Wk"
    return str(kind)


def cells(pct):
    filled = round(min(max(pct, 0), 100) * BAR_CELLS / 100)
    return "█" * filled + "░" * (BAR_CELLS - filled)


def _pct_color(pct, theme):
    if pct >= 90:
        return theme["critical"]
    if pct >= 70:
        return theme["warning"]
    return theme["indicator"]


def render(st, theme, now):
    limits = st.get("limits") or []
    err = st.get("limits_error")

    nums = [str(int(round(l.get("percent") or 0))) for l in limits]
    text = ICON + ("\n" + "\n".join(nums) if nums else "\n–")
    if err:
        cls = "stale"
    else:
        worst = max((l.get("percent") or 0 for l in limits), default=0)
        cls = "critical" if worst >= 90 else "warning" if worst >= 70 else "normal"

    meta = st.get("creds_meta") or {}
    tier = (meta.get("rateLimitTier") or meta.get("subscriptionType") or "")
    tier = pango_escape(tier.replace("_", " ").title())
    mut, sect = theme["muted"], theme["accent"]
    lines = [f'<b>{ICON} Claude Code</b>'
             + (f' <span color="{mut}">· {tier}</span>' if tier else "")]

    if err:
        fetched = st.get("limits_fetched_at")
        age = (datetime.fromtimestamp(fetched).astimezone().strftime("%H:%M")
               if fetched else "never")
        lines += ["", f'<span color="{theme["warning"]}">⚠ stale — '
                      f'{pango_escape(err)}, data from {age}</span>']

    if limits:
        lines += ["", f'<span color="{sect}"><b>LIMITS</b></span>']
        width = max(len(limit_label(l)) for l in limits)
        for l in limits:
            pct = l.get("percent") or 0
            label = pango_escape(limit_label(l))
            pad = " " * (width - len(limit_label(l)))
            bar = f'<span color="{_pct_color(pct, theme)}">{cells(pct)}</span>'
            reset = countdown(l.get("resets_at"), now)
            reset = (f'  <span color="{mut}">{ICON_RESET} {reset}</span>'
                     if reset else "")
            lines.append(f"{label}{pad}  {bar}  <b>{int(round(pct)):>3}%</b>{reset}")
    elif not err:
        lines += ["", f'<span color="{mut}">no limit data yet</span>']

    days = st.get("days") or {}
    if days:
        today = now.astimezone().date()
        window = [today - timedelta(days=i) for i in range(6, -1, -1)]
        totals = {d: sum((days.get(d.isoformat()) or {}).values()) for d in window}
        peak = max(totals.values()) or 1
        lines += ["", f'<span color="{sect}"><b>TOKENS BY DAY</b></span>']
        for d in window:
            name = "Today" if d == today else d.strftime("%a")
            pad = " " * (5 - len(name))  # pad on the raw name: tags have no width
            label = (f"<b>{name}</b>" if d == today
                     else f'<span color="{mut}">{name}</span>')
            n = totals[d]
            bar = "█" * round(n / peak * BAR_CELLS) or "▏"  # hairline for ~zero days
            lines.append(f'{label}{pad}  '
                         f'<span color="{theme["indicator"]}">{bar}</span>'
                         f' {humanize(n):>6}')
        by_model = {}
        for per_day in days.values():
            for model, n in per_day.items():
                by_model[model] = by_model.get(model, 0) + n
        if by_model:
            lines += ["", f'<span color="{sect}"><b>TOKENS BY MODEL</b></span>'
                          f' <span color="{mut}">(7d)</span>']
            mpeak = max(by_model.values()) or 1
            mwidth = max(len(model_display(m)) for m in by_model)
            for model, n in sorted(by_model.items(), key=lambda kv: -kv[1]):
                mname = pango_escape(model_display(model))
                pad = " " * (mwidth - len(model_display(model)))
                bar = "█" * max(1, round(n / mpeak * BAR_CELLS))
                lines.append(f'{mname}{pad}  '
                             f'<span color="{theme["indicator"]}">{bar}</span>'
                             f' {humanize(n):>6}')

    stamp = st.get("limits_fetched_at")
    when = (datetime.fromtimestamp(stamp).astimezone().strftime("%H:%M")
            if stamp else "–")
    lines += ["", f'<span color="{mut}">updated {when} · click {ICON}'
                  f' to refresh</span>']
    tooltip = f'<span face="{FACE}">' + "\n".join(lines) + "</span>"
    return {"text": text, "tooltip": tooltip, "class": cls}
```

The tests assert content, not exact spacing — column-alignment tweaks are free.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/claude_usage_test.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -u && git commit -m "feat(waybar): claude widget renderer — bar, class, quattro-style tooltip"
```

---

### Task 6: main() wiring, waybar config, CSS

**Files:**
- Modify: `waybar/.config/waybar/scripts/claude_usage.py` (append)
- Modify: `tests/claude_usage_test.py` (append)
- Modify: `waybar/.config/waybar/config` (modules-right list + new module block)
- Modify: `waybar/.config/waybar/style.css` (shared module selector list + state colours)

**Interfaces:**
- Consumes: every function from Tasks 1–5.
- Produces: `main(argv=None) -> None` printing one JSON object to stdout; CLI flag `--refresh`.

- [ ] **Step 1: Write the failing test** (append to `tests/claude_usage_test.py`)

```python
import contextlib


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/claude_usage_test.py`
Expected: `AttributeError` on `main`.

- [ ] **Step 3: Implement main()** (append to `claude_usage.py`)

```python
def main(argv=None):
    force = "--refresh" in (argv if argv is not None else sys.argv[1:])
    home = Path(os.environ.get("HOME", str(Path.home())))
    cache_dir = Path(os.environ.get("XDG_CACHE_HOME",
                                    home / ".cache")) / "claude-usage"
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Single writer: --refresh runs, signal re-execs, and interval runs must
    # not interleave read-modify-write (spec §2). Lock file, not state.json —
    # the atomic rename below would swap the locked inode out.
    with open(cache_dir / "lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state_path = cache_dir / "state.json"
        try:
            st = json.loads(state_path.read_text())
        except (OSError, ValueError):
            st = {}  # first run or corrupt: silent rebuild
        now = datetime.now(timezone.utc)
        refresh_limits(st, home / ".claude" / ".credentials.json",
                       force, now.timestamp())
        scan_jsonl(home / ".claude" / "projects", st, now.timestamp())
        theme = load_theme(home / ".config" / "sway" / "theme.gen.env")
        out = render(st, theme, now)
        tmp = state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(st))
        tmp.replace(state_path)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 tests/claude_usage_test.py`
Expected: all PASS (whole file, all tasks).

- [ ] **Step 5: Wire the waybar module**

In `waybar/.config/waybar/config`, add to `modules-right` after `"custom/network",`:

```jsonc
        "custom/claude",
```

and add the block next to the other custom modules:

```jsonc
    "custom/claude": {
        "exec": "~/.config/waybar/scripts/claude_usage.py",
        "return-type": "json",
        "interval": 300,
        // Signal 1 is custom/keyboard-layout's; on-click refreshes then pokes us.
        "signal": 8,
        // Default true would re-exec on every click — racing the --refresh run.
        "exec-on-event": false,
        "format": "{}",
        "justify": "center",
        "on-click": "~/.config/waybar/scripts/claude_usage.py --refresh; pkill -RTMIN+8 waybar"
    },
```

- [ ] **Step 6: Style it**

In `waybar/.config/waybar/style.css`: add `#custom-claude,` to the shared module selector list (the block that already contains `#custom-network,` around line 78), then add state colours near the `#custom-network.disconnected` rule:

```css
#custom-claude          { color: @fg; }
#custom-claude.warning  { color: @warning; }
#custom-claude.critical { color: @critical; }
#custom-claude.stale    { color: @muted; }
```

- [ ] **Step 7: Verify live**

```bash
# Direct run first (this is also the one-time full-corpus rebuild — time it):
time ~/.config/waybar/scripts/claude_usage.py | jq .
# Second run must be fast (incremental) and must not hit the API (TTL):
time ~/.config/waybar/scripts/claude_usage.py | jq -r .class
# Then restart waybar the usual way and check: icon + three numbers on the
# bar, hover tooltip matches the mockup, click forces a refresh (bar updates,
# journal shows no errors).
```

Expected: first run seconds (corpus parse), second run well under a second, tooltip renders in JetBrainsMono with bars aligned.

- [ ] **Step 8: Commit**

```bash
git add -u && git commit -m "feat(waybar): claude usage module — config, css, end-to-end"
```

---

### Task 7: Align statusline thresholds (user ruling F10)

**Files:**
- Modify: `claude/.claude/statusline.py:224-231`

**Interfaces:** none (self-contained display change).

- [ ] **Step 1: Make the change**

Replace (currently at lines 224–231):

```python
    # Rate limits bite harder than context does — warn earlier.
    for icon, key in ((ICON_SESSION, "five_hour"), (ICON_WEEK, "seven_day")):
        window = limits.get(key)
        if window and window.get("used_percentage") is not None:
            rest.append(usage_segment(
                icon, float(window["used_percentage"]), 50, 80,
```

with:

```python
    # Rate limits cost delivery speed, not output quality — context (60/85
    # above) is what degrades quality, so it is the one that warns earlier.
    # 70/90 matches the waybar claude widget: one machine-wide definition.
    for icon, key in ((ICON_SESSION, "five_hour"), (ICON_WEEK, "seven_day")):
        window = limits.get(key)
        if window and window.get("used_percentage") is not None:
            rest.append(usage_segment(
                icon, float(window["used_percentage"]), 70, 90,
```

- [ ] **Step 2: Verify**

Run: `python3 -c "import ast; ast.parse(open('claude/.claude/statusline.py').read())"` (syntax), then confirm the statusline still renders in a Claude Code session.

- [ ] **Step 3: Commit**

```bash
git add claude/.claude/statusline.py
git commit -m "fix(claude): statusline rate-limit thresholds 70/90, reversed rationale"
```

---

### Task 8: Guard suite, docs, spec artifacts

**Files:**
- Modify: `tests/theme_test.sh` (append one line)
- Modify: `PLAYBOOK.md` (new §9 entry), `CLAUDE.md` (one gotcha line)
- Commit: `docs/specs/2026-08-22-claude-usage-widget-design.md`, `…-design.review.md`, `…-mockup.html`, `docs/plans/2026-08-22-claude-usage-widget.md`

- [ ] **Step 1: Hook the unittest into the suite**

Append to `tests/theme_test.sh` after the `check_hex.py` invocation (line ~146), matching its style:

```sh
python3 "$REPO/tests/claude_usage_test.py" >/dev/null
```

- [ ] **Step 2: Run the full suite**

Run: `sh tests/theme_test.sh`
Expected: PASS — in particular `check_hex.py` must not flag `claude_usage.py` (it contains no hex colour literals; the fallback palette is Pango named colours by design).

- [ ] **Step 3: Document**

`PLAYBOOK.md`: append a new §9 entry (next free number — check the current highest) covering, in the playbook's telegraphic style: data sources (OAuth usage API + `~/.claude/projects` JSONLs); **read-only** rule on `~/.claude` (the widget must never refresh the token — Claude Code's daemon owns rotation; claudebar's write-back approach is exactly what we rejected); cadences 300s/30s debounce/5s timeout and why (undocumented endpoint, aggressive rate limits); `exec-on-event: false` + flock single-writer reasoning; named-colour fallback (check_hex); state in `~/.cache/claude-usage/` (delete it to force a full rebuild).

`CLAUDE.md`: one gotcha line in the existing list, e.g.:

```markdown
- waybar's claude widget treats `~/.claude` as **read-only** — never add token
  refresh; state/cache lives in `~/.cache/claude-usage/` (safe to delete) (§9.N).
```

- [ ] **Step 4: Final commit**

```bash
git add tests/theme_test.sh PLAYBOOK.md CLAUDE.md docs/specs/2026-08-22-claude-usage-widget-design.md docs/specs/2026-08-22-claude-usage-widget-design.review.md docs/specs/2026-08-22-claude-usage-widget-mockup.html docs/plans/2026-08-22-claude-usage-widget.md
git commit -m "docs(waybar): claude usage widget spec, plan, playbook entry"
```
