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
    "success": "green", "desktop": "black",
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


def load_theme(path):
    theme = dict(FALLBACK_THEME)
    try:
        text = Path(path).read_text()
    except (OSError, UnicodeDecodeError):
        return theme
    for line in text.splitlines():
        m = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(\S+)", line.strip())
        if m and m.group(1).lower() in theme:
            theme[m.group(1).lower()] = m.group(2)
    return theme


def read_credentials(path, now_epoch):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None, "not logged in", {}
    if not isinstance(data, dict):
        return None, "not logged in", {}
    oauth = data.get("claudeAiOauth") or {}
    if not isinstance(oauth, dict):
        return None, "not logged in", {}
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
        st["limits_forced_at"] = now_epoch
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
        st["limits_error"] = None


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
