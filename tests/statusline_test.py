"""Tests for claude/.claude/statusline.py (stdlib unittest).

The context segment is the one worth testing: Claude Code does not always have
a measurement to give it, and says so with zeros rather than nulls. Each
payload below copies the shape a real render received on 2.1.296, captured by
teeing the status line's stdin — synthetic values, real structure:

- after `/compact`, until the next API call: every `context_window` count is
  0, `used_percentage` included (the docs say `current_usage` is null here;
  the real payload is an all-zero object). The session's cost is not reset,
  so the line read `0% | $42.45`.
- before a session's first API call: the documented null form.

STATUSLINE_BIN points the suite at another copy (the mutation check).
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = Path(os.environ.get("STATUSLINE_BIN", REPO / "claude/.claude/statusline.py"))
# Importing would write claude/.claude/__pycache__ into the stow package, and
# the next `stow -R claude` would link it to ~/.claude/__pycache__.
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("statusline", SCRIPT)
sl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sl)

ANSI = re.compile(r"\033\[[0-9;]*m")

MEASURED = {
    "total_input_tokens": 86161, "total_output_tokens": 5,
    "context_window_size": 1000000,
    "current_usage": {"input_tokens": 2, "output_tokens": 5,
                      "cache_creation_input_tokens": 1514,
                      "cache_read_input_tokens": 84645},
    "used_percentage": 9, "remaining_percentage": 91,
}
COMPACTED = {
    "total_input_tokens": 0, "total_output_tokens": 0,
    "context_window_size": 1000000,
    "current_usage": {"input_tokens": 0, "output_tokens": 0,
                      "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0},
    "used_percentage": 0, "remaining_percentage": 100,
}
UNSTARTED = {
    "total_input_tokens": 0, "total_output_tokens": 0,
    "context_window_size": 1000000, "current_usage": None,
    "used_percentage": None, "remaining_percentage": None,
}


class ContextSegmentTest(unittest.TestCase):
    def setUp(self):
        # Outside any git repo, so the line carries no branch segment.
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def render(self, context_window, cost=42.45):
        payload = {
            "workspace": {"current_dir": self.tmp.name},
            "model": {"display_name": "Opus 5.5"},
            "cost": {"total_cost_usd": cost},
        }
        if context_window is not ...:
            payload["context_window"] = context_window
        env = {k: v for k, v in os.environ.items()
               if k != "CLAUDE_CODE_BRIDGE_SESSION_ID"}
        env["COLUMNS"] = "200"
        out = subprocess.run(
            ["python3", str(SCRIPT)], input=json.dumps(payload),
            capture_output=True, text=True, env=env, cwd=self.tmp.name,
            timeout=10, check=True,
        ).stdout
        # dir | model | context | cost | ...
        return ANSI.sub("", out).rstrip("\n").split(" | ")

    def context(self, context_window):
        return self.render(context_window)[2]

    def test_measured_context_shows_its_percentage(self):
        self.assertEqual(self.context(MEASURED), f"{sl.ICON_CONTEXT} 9%")

    def test_after_compact_is_unknown_not_zero(self):
        # The bug: an all-zero placeholder painted as a confident green 0%.
        line = self.render(COMPACTED)
        self.assertEqual(line[2], f"{sl.ICON_CONTEXT} ?")
        self.assertEqual(line[3], "$42.45")  # cost still shown beside it

    def test_before_first_call_is_unknown(self):
        self.assertEqual(self.context(UNSTARTED), f"{sl.ICON_CONTEXT} ?")

    def test_no_context_window_is_unknown(self):
        self.assertEqual(self.context(...), f"{sl.ICON_CONTEXT} ?")

    def test_small_real_measurement_still_reads_zero(self):
        # 3k tokens of a 1M window rounds to 0 — a real reading, not a
        # placeholder. Keying "unknown" off the percentage alone would hide it.
        small = dict(MEASURED, used_percentage=0, remaining_percentage=100,
                     current_usage=dict(MEASURED["current_usage"],
                                        cache_read_input_tokens=3000))
        self.assertEqual(self.context(small), f"{sl.ICON_CONTEXT} 0%")


class PeerNameTest(unittest.TestCase):
    """`@name` comes from the session registry of the ancestor Claude process.

    The script is run directly by this test process, so its parent PID is
    ours: the fake registry file is `<our pid>.json` under a throwaway
    CLAUDE_CONFIG_DIR. Run inside a live session, the walk would otherwise
    reach the real registry — the sessionId match is what keeps it out.
    """
    SID = "00000000-0000-4000-8000-000000000001"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Path(self.tmp.name) / "config"
        (self.config / "sessions").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def register(self, **entry):
        (self.config / "sessions" / f"{os.getpid()}.json").write_text(
            json.dumps(entry))

    def line(self, session_id=SID):
        payload = {"workspace": {"current_dir": self.tmp.name},
                   "model": {"display_name": "Opus 5.5"}}
        if session_id:
            payload["session_id"] = session_id
        env = {k: v for k, v in os.environ.items()
               if k != "CLAUDE_CODE_BRIDGE_SESSION_ID"}
        env.update(COLUMNS="200", CLAUDE_CONFIG_DIR=str(self.config))
        out = subprocess.run(
            ["python3", str(SCRIPT)], input=json.dumps(payload),
            capture_output=True, text=True, env=env, cwd=self.tmp.name,
            timeout=10, check=True,
        ).stdout
        return ANSI.sub("", out).rstrip("\n").split(" | ")

    def test_registered_name_is_shown(self):
        self.register(sessionId=self.SID, name="dotfiles-c2")
        self.assertEqual(self.line()[-1], "@dotfiles-c2")

    def test_other_sessions_entry_is_ignored(self):
        self.register(sessionId="someone-else", name="intruder")
        self.assertFalse(any("@" in s for s in self.line()))

    def test_no_session_id_shows_nothing(self):
        self.register(sessionId=self.SID, name="dotfiles-c2")
        self.assertFalse(any("@" in s for s in self.line(session_id=None)))

    def test_no_registry_shows_nothing(self):
        self.assertFalse(any("@" in s for s in self.line()))

    def test_control_characters_are_neutralised(self):
        self.register(sessionId=self.SID, name="a\x1b[2Jb")
        self.assertEqual(self.line()[-1], "@a?[2Jb")


if __name__ == "__main__":
    unittest.main()
