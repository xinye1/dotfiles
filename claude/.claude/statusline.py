#!/usr/bin/env python3
"""Claude Code status line.

dir | model |  NN% | $N.NN |  NN% (Nh) |  NN% (Nd) |  branch(+dirty) |  level

Styled after starship: normal-weight coloured values, prefixed by a dimmed Nerd
Font icon wherever the value does not already name itself. Colours are the
terminal's own ANSI 16 so they track the active theme. Deliberately quiet — the
conversation above is what matters. Percentages are bare numbers rather than
bars so the whole line fits a half-width split.

The directory is the only elastic segment: everything else is measured first and
the leftover columns become its budget, so the values stay visible as the pane
narrows and the path re-expands when there is room.

Reads session JSON on stdin; see https://code.claude.com/docs/en/statusline
"""

import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata

RESET = "\033[0m"

# Nerd Font glyphs. Codepoints verified against the installed JetBrainsMono
# Nerd Font by reading its cmap and post tables — note that this build maps the
# Font Awesome 6 additions into ed00-efcf, not the f6xx range the upstream cheat
# sheet lists, so nf-fa-gauge_simple is eeb3 here rather than f629.
ICON_CONTEXT = ""  # nf-fa-gauge_simple (how full the context window is)
ICON_SESSION = ""  # nf-fa-clock_o      (the rolling 5h window)
ICON_WEEK = ""     # nf-fa-calendar_o   (the rolling 7d window)
ICON_GIT = ""      # nf-pl-branch
ICON_EFFORT = ""   # nf-fa-flash        (FA4's name for the bolt glyph)
# Directory and model carry no icon — a path and a model name label themselves.
# Cost carries none either: the `$` on its value is already the label.

DIM = "2"          # separators
LABEL = "2;37"     # icon prefixes
BLUE = "36"        # cwd            (starship directory)
MODEL = "33"       # model name     (starship toolchain)
VALUE = "37"       # cost value
BRANCH = "35"      # git branch     (starship git_branch)
DIRTY = "31"       # dirty count    (starship git_status)

# usage percentages, coloured by how much headroom is left
GREEN = "32"
YELLOW = "33"
RED = "31"

EFFORT_COLORS = {
    "low": "2;37",
    "medium": "36",
    "high": "32",
    "xhigh": "33",
    "max": "35",
}

# Directory budget: never shrink below MIN, never sprawl past MAX, and inside
# that band take whatever the other segments leave. MARGIN keeps the line off
# the right edge so a wrap never eats the last value.
PATH_MIN = 12
PATH_MAX = 40
# Slack for terminals that render Nerd Font glyphs double-width. cell_len
# counts a glyph as one column, so the line can draw one column wider per icon
# than the budget predicts — five of them (context, session, week, git, effort),
# hence five.
MARGIN = 5
# Claude Code exports COLUMNS, so this only falls back on an unusual client.
FALLBACK_COLUMNS = 100

ANSI_RE = re.compile(r"\033\[[0-9;]*m")
# A path component may legally contain any byte but / and NUL — including ESC
# and newline, which would otherwise be written to the terminal verbatim and
# could redraw the line. They also break the column budget, since they measure
# as one character and draw as none.
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def paint(color, text):
    return f"\033[{color}m{text}{RESET}"


def segment(icon, value):
    return f"{paint(LABEL, icon)} {value}"


def cell_len(text):
    """Printed width in terminal cells, ignoring the colour escapes.

    Characters are not columns: CJK and emoji occupy two cells, and combining
    marks none. Counting them as one apiece would hand the path a budget the
    line cannot honour. The Nerd Font icons are Private Use, which terminals
    render inconsistently — MARGIN, not this, is what covers them.
    """
    width = 0
    for ch in ANSI_RE.sub("", text):
        if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def short_path(path, limit):
    """Fit a path into `limit` columns, dropping leading components first."""
    home = os.path.expanduser("~")
    if path == home:
        display = "~"
    elif path.startswith(home + os.sep):
        display = "~" + path[len(home):]
    else:
        display = path
    display = CONTROL_RE.sub("?", display)
    if cell_len(display) <= limit:
        return display

    # Shed leading components one at a time — the tail is what identifies a repo.
    parts = [p for p in display.split(os.sep) if p]
    for keep in range(len(parts) - 1, 0, -1):
        candidate = "…/" + os.sep.join(parts[-keep:])
        if cell_len(candidate) <= limit:
            return candidate
    # Even the last component overflows; clip it from the left, one character
    # at a time so a wide one cannot straddle the limit.
    if limit <= 1:
        return "…"
    clipped = ""
    for ch in reversed(parts[-1]):
        if cell_len(clipped) + cell_len(ch) > limit - 1:
            break
        clipped = ch + clipped
    return "…" + clipped


def resets_in(epoch):
    """`4h` / `3d` — whole units left before a rate-limit window resets."""
    if not epoch:
        return None
    seconds = epoch - time.time()
    if seconds <= 0:
        return None
    # Promote when rounding up fills the unit, so 3599s reads `1h`, not `60m`.
    minutes = math.ceil(seconds / 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = math.ceil(seconds / 3600)
    if hours < 24:
        return f"{hours}h"
    return f"{math.ceil(seconds / 86400)}d"


def git_segment(cwd):
    """Return the branch segment, or None outside a repo."""
    def git(*args):
        try:
            out = subprocess.run(
                ("git", "-C", cwd) + args,
                capture_output=True, text=True, timeout=1,
                # Refs are bytes, so a branch name need not be valid UTF-8.
                # Strict decoding raises UnicodeDecodeError — a ValueError, which
                # the handler below would not catch, killing the whole line.
                errors="replace",
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    branch = git("symbolic-ref", "--short", "HEAD") or git("rev-parse", "--short", "HEAD")
    if not branch:
        return None
    # `--no-optional-locks`: this runs on every render, and a plain `git status`
    # opportunistically refreshes the index — taking `.git/index.lock` and
    # racing whatever the user is doing in that repo at the time.
    # `-c core.fsmonitor=false`: fsmonitor can be configured as an external
    # command, which `git status` would then execute out of whatever repo we
    # happen to be sitting in. Costs nothing where it isn't configured.
    status = git("--no-optional-locks", "-c", "core.fsmonitor=false",
                 "status", "--porcelain")
    value = paint(BRANCH, branch)
    if status is None:
        # The command failed or hit the timeout. Not the same as a clean tree —
        # say so, rather than showing a bare branch that reads as clean.
        value += paint(LABEL, "(?)")
    elif status:
        value += paint(DIRTY, f"(+{len(status.splitlines())})")
    return segment(ICON_GIT, value)


def usage_segment(icon, pct, warn, crit, resets=None):
    """An `<icon> NN% (Nh)` segment, greening down to red as the budget is spent."""
    shown = round(pct)  # one rounding, so a 84.6 never prints 85% in yellow
    color = GREEN if shown < warn else YELLOW if shown < crit else RED
    value = paint(color, f"{shown}%")
    if resets:
        value += " " + paint(LABEL, f"({resets})")
    return segment(icon, value)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        data = {}

    workspace = data.get("workspace") or {}
    cwd = workspace.get("current_dir") or data.get("cwd") or os.getcwd()
    model = (data.get("model") or {}).get("display_name") or "Claude"
    pct = (data.get("context_window") or {}).get("used_percentage") or 0
    cost = (data.get("cost") or {}).get("total_cost_usd") or 0.0
    level = (data.get("effort") or {}).get("level")
    limits = data.get("rate_limits") or {}

    # Everything but the directory, which is sized last from what is left over.
    rest = [
        paint(MODEL, model),
        usage_segment(ICON_CONTEXT, float(pct), 60, 85),
        paint(VALUE, f"${cost:.2f}"),
    ]
    # Rate limits cost delivery speed, not output quality — context (60/85
    # above) is what degrades quality, so it is the one that warns earlier.
    # 70/90 matches the waybar claude widget: one machine-wide definition.
    for icon, key in ((ICON_SESSION, "five_hour"), (ICON_WEEK, "seven_day")):
        window = limits.get(key)
        if window and window.get("used_percentage") is not None:
            rest.append(usage_segment(
                icon, float(window["used_percentage"]), 70, 90,
                resets_in(window.get("resets_at")),
            ))
    git = git_segment(cwd)
    if git:
        rest.append(git)
    if level:
        rest.append(segment(ICON_EFFORT, paint(EFFORT_COLORS.get(level, LABEL), level)))

    columns = shutil.get_terminal_size((FALLBACK_COLUMNS, 24)).columns
    # Each of `rest` is preceded by a " | ", so it costs its width plus 3.
    spent = sum(cell_len(s) + 3 for s in rest)
    budget = max(PATH_MIN, min(PATH_MAX, columns - spent - MARGIN))

    segments = [paint(BLUE, short_path(cwd, budget))] + rest
    sys.stdout.write(paint(DIM, " | ").join(segments) + "\n")


if __name__ == "__main__":
    main()
