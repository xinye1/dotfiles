#!/usr/bin/env python3
"""Claude Code usage widget for waybar: limits, reset countdowns, token charts.

Design: docs/specs/2026-08-22-claude-usage-widget-design.md. Read-only on
~/.claude; all state in ~/.cache/claude-usage/. Stdlib only.
"""
import fcntl
import hashlib
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
PACE_MARK = "│"        # U+2502: an ordinary box-drawing char, not a PUA glyph

# Pango named colours only: tests/check_hex.py scans this file for hex literals.
FALLBACK_THEME = {
    "bg": "black", "surface": "black", "sel": "gray", "muted": "gray",
    "dim": "silver", "fg": "white", "fg_bright": "white", "accent": "yellow",
    "accent2": "orange", "indicator": "lightgreen", "critical": "red",
    "warning": "orange", "success": "green", "desktop": "black",
}

MODEL_NAMES = (
    ("claude-fable-5", "Fable 5"),
    ("claude-opus-5", "Opus 5"),
    ("claude-sonnet-5", "Sonnet 5"),
    ("claude-haiku-4-5", "Haiku 4.5"),
)


def pango_escape(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def plain_len(s):
    """Visible width of a marked-up fragment: tags contribute nothing, and the
    only entities that can occur are pango_escape's three. Module level rather
    than nested in render() so the tests can hold the bar to it directly — its
    exact BAR_CELLS width is what every column in the tooltip rests on."""
    return len(re.sub(r"<[^>]+>", "", s)
               .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))


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
    if not isinstance(resets_at, str):
        # fetch_limits() always coerces resets_at to str-or-None, so a fresh
        # API response can't reach here with the wrong type. The only way in
        # is state.json: main() only checks that the top-level object is a
        # dict (`if not isinstance(st, dict)`), never the shape of what's
        # nested inside it, so a corrupted or hand-edited cache file can still
        # hand this a truthy int/dict/list. Without this guard that reaches
        # `.replace` below and raises AttributeError, which the except clause
        # doesn't catch -- same no-self-heal failure as the naive-timestamp
        # case documented there: it escapes render() and main() before the
        # state write, so the TTL never starts and every tick re-crashes.
        return ""
    try:
        dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        # A NAIVE timestamp is the one shape that used to blank the whole
        # widget. The endpoint is undocumented (§9.23), so it is free to drop
        # the trailing "Z" at any time; fromisoformat then parses happily and
        # the subtraction below raises TypeError against a tz-aware `now`.
        # That escaped render() and main() before the state write, so
        # limits_fetched_at never advanced, the TTL never started, and every
        # tick re-fetched and re-crashed: waybar showed nothing, for good.
        # The endpoint speaks UTC, so read a bare timestamp as UTC. The widened
        # except is belt and braces for whatever the next shape drift is.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        mins = int((dt - now).total_seconds() // 60)
    except (ValueError, TypeError):
        return ""
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


# Words `.title()` mangles. Deliberately a two-entry set rather than a general
# scheme: `subscriptionType` is a short closed vocabulary ("pro", "max") and
# `rateLimitTier` is the constant `default_claude_ai` today, so "ai" -> "Ai" is
# the only mangling that has ever reached the tooltip. Add to it when a value
# actually appears that needs it, not in anticipation.
ACRONYMS = {"ai", "api"}


def title_case(s):
    """`default_claude_ai` -> `Default Claude AI`; `pro` -> `Pro`.

    str.title() alone gives "Default Claude Ai", which reads as a typo in a
    header. Splitting on whitespace after the underscores also collapses any
    doubled separator, so `a__b` cannot produce an empty word.
    """
    return " ".join(w.upper() if w.lower() in ACRONYMS else w.capitalize()
                    for w in str(s).replace("_", " ").split())


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
    expires_at = oauth.get("expiresAt")
    if not isinstance(expires_at, (int, float)):
        expires_at = 0  # missing/drifted shape: treat as already expired
    if expires_at / 1000 <= now_epoch:
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
    cleaned = []
    for entry in limits:
        if not isinstance(entry, dict):
            continue  # API/shape drift: drop, don't crash the render
        entry = dict(entry)
        try:
            entry["percent"] = float(entry.get("percent") or 0)
        except (TypeError, ValueError):
            entry["percent"] = 0.0
        resets_at = entry.get("resets_at")
        entry["resets_at"] = resets_at if isinstance(resets_at, str) else None
        cleaned.append(entry)
    return cleaned


def refresh_limits(st, creds_path, force, now_epoch, urlopen=None):
    token, err, meta = read_credentials(creds_path, now_epoch)
    if meta:
        # Merge, don't replace: read_credentials only reports keys it actually
        # found, so a read that turns up subscriptionType but not rateLimitTier
        # would otherwise drop a tier label we already knew. Display-only (the
        # tooltip header), which is why last-known beats blank.
        prev = st.get("creds_meta")
        st["creds_meta"] = {**prev, **meta} if isinstance(prev, dict) else meta
    if err:
        st["limits_error"] = err
        return
    if force:
        if now_epoch - st.get("limits_forced_at", 0) < FORCE_DEBOUNCE:
            return
        st["limits_forced_at"] = now_epoch
    elif now_epoch - st.get("limits_fetched_at", 0) < API_TTL:
        # limits_fetched_at only moves on success, so landing here means the
        # data on screen is inside the TTL — current by policy. A transient
        # failure since then is water under the bridge; leaving its error set
        # would fly "⚠ stale" over minutes-old data for the rest of the TTL.
        st["limits_error"] = None
        return
    elif now_epoch - st.get("limits_attempt_at", 0) < FORCE_DEBOUNCE:
        # A fetch just ran and failed (e.g. a forced one whose signal re-exec
        # lands here); without this gate every click during an outage would
        # make one API attempt, bypassing the debounce entirely.
        return
    st["limits_attempt_at"] = now_epoch
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
            # Wrong-shape lines (top-level array, list-valued usage, string
            # token counts, ...) must never survive past this offset bump —
            # once offset has advanced the line is gone for good, so any
            # parse/shape surprise below just skips it rather than crashing
            # the whole tick (spec §5: "Malformed JSONL line -> Skip line").
            try:
                obj = json.loads(raw)
                msg = obj.get("message") or {}
                usage, model, ts = msg.get("usage"), msg.get("model"), obj.get("timestamp")
                if not usage or not model or not ts or model == "<synthetic>":
                    continue
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                ts_epoch = dt.timestamp()
                # Token total before the dedup-record: a shape surprise here
                # must not leave the key marked seen with nothing counted,
                # or a later well-formed duplicate would be dropped.
                tokens = sum(usage.get(k) or 0 for k in _USAGE_KEYS)
                mid, rid = msg.get("id"), obj.get("requestId")
                # Every counted line must land in `seen`, because the byte
                # offset is not a durable guarantee that these bytes are read
                # once: scan_jsonl resets to 0 whenever a file did not simply
                # grow (truncate/rewrite) or its record aged out of the mtime
                # window, and an un-keyed line would then be counted twice.
                # So a line missing either id falls back to a hash of its own
                # bytes, namespaced by a prefix a real "mid|rid" cannot wear
                # (the digest carries no "|"). Content is a sound identity
                # here rather than a lossy one: two byte-identical records
                # agree on timestamp and on every token count, so nothing
                # downstream could tell them apart even in principle, and
                # collapsing them costs the chart nothing it could show.
                key = (f"{mid}|{rid}" if mid and rid else
                       "raw:" + hashlib.blake2b(raw, digest_size=16).hexdigest())
                if key in seen:
                    continue
                seen[key] = ts_epoch
                if ts_epoch < cutoff_epoch:
                    continue
                day = dt.astimezone().date().isoformat()
                per_day = days.setdefault(day, {})
                per_day[model] = per_day.get(model, 0) + tokens
            except (AttributeError, TypeError, ValueError):
                continue
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
            # Reset to 0 unless the file only grew (truncate/rewrite invalidates
            # the offset). This also catches a subtler path: a file that goes
            # quiet ages past the mtime cutoff above, so it never joins `alive`
            # and the prune below drops its record — resume it a month later and
            # it rescans from byte 0. Acceptable because these files are
            # append-only in timestamp order, so everything before the new tail
            # is older than cutoff_epoch and the per-line cutoff drops it (the
            # cutoff_iso prescreen makes that pass cheap); anything genuinely
            # in-window is still covered by `seen`.
            offset = rec["offset"] if rec and fst.st_size > rec["size"] else 0
            # ~/.claude is foreign, read-only territory (§9.23): its files are
            # written by another process and this widget gets no say in what is
            # there. The stat above is guarded but open() has its own ways to
            # fail — mode 000, the file removed between the stat and the open,
            # EIO on a failing disk, the process out of file descriptors — and
            # one of them used to abort the whole tick, losing every OTHER
            # transcript's tokens with it. One unreadable file must cost
            # exactly that one file. `continue` leaves files[path] as it was,
            # so the byte offset survives to be resumed once the file is
            # readable again rather than rescanning it from zero.
            try:
                offset = _scan_file(path, offset, cutoff_epoch, cutoff_iso,
                                    seen, days)
            except OSError as e:
                print(f"claude_usage: {path}: {e}", file=sys.stderr)
                continue
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


# How long each limit's window is, in seconds. The payload gives `resets_at`
# — the window's END — and nothing else: no start, no duration. So the length
# can only come from the kind, and the design spec fixes all three by name
# (§1: `session` is the 5-hour rolling window, both weeklies are 7-day).
# Hardcoded rather than derived because deriving it would mean watching a
# window reset and remembering when — persistent state, and a whole class of
# wrong-after-a-cache-wipe bugs — for a number that belongs to the plan rather
# than to the response. A kind that is not in here gets no marker at all
# (pace_mark), which is why an added fourth limit type costs these three
# nothing.
LIMIT_WINDOWS = {
    "session": 5 * 3600,
    "weekly_all": 7 * 86400,
    "weekly_scoped": 7 * 86400,
}


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


def pace_mark(kind, resets_at, now):
    """Which bar cell the pace marker replaces: how far through its OWN window
    this limit is, as an index in 0..BAR_CELLS-1. None whenever that cannot be
    established, and None is the only fallback there is — a bar without a
    marker still reads perfectly, a bar of the wrong width shifts every column
    in the tooltip (see cells()).

    Timestamp handling is countdown()'s, for countdown()'s reasons: the
    endpoint is undocumented (§9.23), so `resets_at` may lose its zone at any
    time and is read as UTC when it does, and a corrupted or hand-edited
    state.json can hand over a non-string entirely. `kind` gets an isinstance
    of its own because it is raw JSON too: a drift to a list or dict is
    unhashable and would raise straight out of the dict lookup below.
    """
    window = LIMIT_WINDOWS.get(kind) if isinstance(kind, str) else None
    if not window or not isinstance(resets_at, str):
        return None
    try:
        dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        elapsed = 1 - (dt - now).total_seconds() / window
    except (ValueError, TypeError):
        return None
    # Clamp the fraction before scaling: a window already past its reset, or a
    # skewed clock, must still land on a real cell rather than off either end.
    cell = int(min(max(elapsed, 0.0), 1.0) * BAR_CELLS)
    return min(cell, BAR_CELLS - 1)  # a full window scales to 16, one past 15


def cells(pct, mark=None, mark_color=None, fill_color=None):
    """The usage bar: exactly BAR_CELLS *visible* characters, always.

    `mark` (from pace_mark) REPLACES a cell rather than inserting one. Every
    tooltip row is column-aligned by plain_len() over the whole block, so a
    17th visible character would push this one row's percent and countdown out
    of line with its neighbours. Markup costs nothing there — plain_len strips
    tags before counting — so the marker takes its own colour by nesting a
    span inside the fill-coloured one render() wraps around this.

    That nested span also carries a BACKGROUND built from `fill_color`, because
    PACE_MARK is a thin stroke on an otherwise empty cell: without one the
    tooltip's own background shows through either side and the rule reads as a
    notch bitten out of the bar rather than a line drawn across it. The bright
    stroke is already distinct from every threshold colour, so that gap was
    never what made it legible.

    The background reproduces the DENSITY of the glyph it replaced, which is
    what makes the cell disappear into its neighbours in both halves of the
    bar: opaque over a █, and 25% over a ░, U+2591 being the 25%-density
    shade. Rendering the two side by side and measuring puts the light-shade
    track at ~28% of the way from the tooltip background to the fill colour,
    so the nominal 25% lands within a few percent of it by eye. Tinting rather
    than filling is also what keeps the cell honest past the fill — an opaque
    cell out there would colour unused capacity as used, which is the one lie
    this bar must never tell.
    """
    filled = round(min(max(pct, 0), 100) * BAR_CELLS / 100)
    bar = ["█"] * filled + ["░"] * (BAR_CELLS - filled)
    if mark is not None and 0 <= mark < BAR_CELLS:
        if mark_color:
            bg = ""
            if fill_color:
                bg = f' bgcolor="{fill_color}"'
                if mark >= filled:
                    bg += ' bgalpha="25%"'      # match ░, never read as used
            bar[mark] = f'<span color="{mark_color}"{bg}>{PACE_MARK}</span>'
        else:
            bar[mark] = PACE_MARK
    return "".join(bar)


def shown_pct(limit):
    """The integer percent the user actually sees — and the only value the
    70/90 thresholds may compare. Deciding on the raw float instead painted
    69.6 as "70%" in the normal colour and 89.6 as "90%" in warning: the number
    and its colour disagreed, which reads as a bug in the thresholds. Rounding
    first makes the two agree by construction. `cells()` stays on the float —
    it is a proportional bar, not a threshold."""
    return int(round(limit.get("percent") or 0))


def _pct_color(pct, theme):  # pct is the rounded, displayed integer
    if pct >= 90:
        return theme["critical"]
    if pct >= 70:
        return theme["warning"]
    return theme["indicator"]


def render(st, theme, now):
    limits = st.get("limits") or []
    err = st.get("limits_error")

    shown = [shown_pct(l) for l in limits]
    text = ICON + ("\n" + "\n".join(str(p) for p in shown) if shown else "\n–")
    if err:
        cls = "stale"
    else:
        worst = max(shown, default=0)
        cls = "critical" if worst >= 90 else "warning" if worst >= 70 else "normal"

    meta = st.get("creds_meta") or {}
    # subscriptionType first, per the design doc's `<subscriptionType/
    # rateLimitTier>`; the code had the two the wrong way round. It matters
    # because `rateLimitTier` is currently `default_claude_ai` for everyone —
    # a constant, and so no information — while `subscriptionType` is `pro`,
    # which is the thing a header subtitle is for. The tier stays as the
    # fallback for an account that somehow reports no subscription.
    tier = (meta.get("subscriptionType") or meta.get("rateLimitTier") or "")
    tier = pango_escape(title_case(tier))
    # `dim`, not `muted`: this is secondary *text* on the GTK tooltip's own
    # background, which the theme paints darker than the bar. `muted` measures
    # 1.87:1 there under nord — below the 3:1 large-text floor, which is what
    # made these lines unreadable rather than merely quiet (§3.1, §9.28).
    dim, sect = theme["dim"], theme["accent"]
    lines = [f'<b>{ICON} Claude Code</b>'
             + (f' <span color="{dim}">· {tier}</span>' if tier else "")]

    if err:
        fetched = st.get("limits_fetched_at")
        age = (datetime.fromtimestamp(fetched).astimezone().strftime("%H:%M")
               if fetched else "never")
        lines += ["", f'<span color="{theme["warning"]}">⚠ stale — '
                      f'{pango_escape(err)}, data from {age}</span>']

    if limits:
        lines += ["", f'<span color="{sect}"><b>LIMITS</b></span>']
        width = max(len(limit_label(l)) for l in limits)
        marked = False
        for l in limits:
            pct, disp = l.get("percent") or 0, shown_pct(l)
            label = pango_escape(limit_label(l))
            pad = " " * (width - len(limit_label(l)))
            # fg_bright, deliberately not a status colour: the marker is a
            # neutral reference line, and the signal is the COMPARISON between
            # it and the fill, not the line. Colouring it by severity would put
            # two competing verdicts inside one 16-cell bar, and it also has to
            # stay legible against both regions it can land in — the
            # threshold-coloured █ and the muted ░.
            mark = pace_mark(l.get("kind"), l.get("resets_at"), now)
            marked = marked or mark is not None
            fill = _pct_color(disp, theme)
            bar = (f'<span color="{fill}">'
                   f'{cells(pct, mark, theme["fg_bright"], fill)}</span>')
            reset = countdown(l.get("resets_at"), now)
            reset = (f'  <span color="{dim}">{ICON_RESET} {reset}</span>'
                     if reset else "")
            lines.append(f"{label}{pad}  {bar}  <b>{disp:>3}%</b>{reset}")
        if marked:
            # One muted line, and only when a marker was actually drawn: this
            # is a key the user needs once, on a tooltip that is already dense.
            lines.append(f'<span color="{theme["fg_bright"]}">{PACE_MARK}</span>'
                         f'<span color="{dim}"> = now · fill past it'
                         f' = ahead of pace</span>')
    elif not err:
        lines += ["", f'<span color="{dim}">no limit data yet</span>']

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
                     else f'<span color="{dim}">{name}</span>')
            n = totals[d]
            bar = "█" * round(n / peak * BAR_CELLS) or "▏"  # hairline for ~zero days
            # (prefix, value) tuple: the value is pushed flush with the
            # tooltip's right edge once the full width is known (see below).
            lines.append((f'{label}{pad}  '
                          f'<span color="{theme["indicator"]}">{bar}</span>',
                          humanize(n)))
        by_model = {}
        for d in window:
            for model, n in (days.get(d.isoformat()) or {}).items():
                by_model[model] = by_model.get(model, 0) + n
        if by_model:
            lines += ["", f'<span color="{sect}"><b>TOKENS BY MODEL</b></span>'
                          f' <span color="{dim}">(7d)</span>']
            mpeak = max(by_model.values()) or 1
            mwidth = max(len(model_display(m)) for m in by_model)
            for model, n in sorted(by_model.items(), key=lambda kv: -kv[1]):
                mname = pango_escape(model_display(model))
                pad = " " * (mwidth - len(model_display(model)))
                bar = "█" * max(1, round(n / mpeak * BAR_CELLS))
                lines.append((f'{mname}{pad}  '
                              f'<span color="{theme["indicator"]}">{bar}</span>',
                              humanize(n)))

    stamp = st.get("limits_fetched_at")
    when = (datetime.fromtimestamp(stamp).astimezone().strftime("%H:%M")
            if stamp else "–")
    lines += ["", f'<span color="{dim}">updated {when} · click {ICON}'
                  f' to refresh</span>']

    # Chart rows are (prefix, value) tuples; every value ends flush with the
    # tooltip's right edge, i.e. the plain-text width of its longest line.
    total = max(plain_len(l) if isinstance(l, str)
                else plain_len(l[0]) + 1 + len(l[1]) for l in lines)
    resolved = [l if isinstance(l, str)
                else l[0] + " " * (total - plain_len(l[0]) - len(l[1])) + l[1]
                for l in lines]
    tooltip = f'<span face="{FACE}">' + "\n".join(resolved) + "</span>"
    return {"text": text, "tooltip": tooltip, "class": cls}


def main(argv=None):
    force = "--refresh" in (argv if argv is not None else sys.argv[1:])
    home = Path(os.environ.get("HOME", str(Path.home())))
    cache_dir = Path(os.environ.get("XDG_CACHE_HOME",
                                    home / ".cache")) / "claude-usage"
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Single writer: --refresh runs, signal re-execs, and interval runs must
    # not interleave read-modify-write (spec §2). Lock file, not state.json —
    # the atomic rename below would swap the locked inode out.
    # "w" truncates on every run, deliberately: the file is never anything but
    # an flock handle, nothing ever reads its (always empty) contents, and the
    # lock lives on the inode rather than the bytes. No reason to open it "a".
    with open(cache_dir / "lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state_path = cache_dir / "state.json"
        try:
            st = json.loads(state_path.read_text())
        except (OSError, ValueError):
            st = {}  # first run or corrupt: silent rebuild
        if not isinstance(st, dict):
            st = {}  # valid JSON but not an object: rebuild too
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
