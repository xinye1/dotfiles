#!/usr/bin/env python3
"""Tests for the herdr attention plugin and the waybar custom/herdr module.

Both scripts only talk to the outside through commands on PATH (notify-send,
makoctl, swaymsg, pkill, herdr) and /proc, so every test runs them as real
subprocesses against stubs that log their argv. Nothing here reaches the live
desktop: no real notification, no signal to the running bar, no herdr socket.
PLAYBOOK §9.30.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ATTENTION = REPO / "herdr/.config/herdr/local-plugins/attention/attention.py"
MODULE = REPO / "waybar/.config/waybar/scripts/herdr_blocked.py"

# Every stub appends "<name> <argv…>" to $STUB_LOG. The two that must answer
# something read it from a file the test writes.
STUB = """#!/bin/sh
printf '%s' "$(basename "$0")" >> "$STUB_LOG"
for a in "$@"; do printf ' %s' "$a" >> "$STUB_LOG"; done
printf '\\n' >> "$STUB_LOG"
"""
STUBS = {
    "notify-send": STUB + 'echo "${NOTIFY_ID:-41}"\n',
    "makoctl": STUB,
    "pkill": STUB,
    "swaymsg": STUB + 'cat "$SWAY_TREE"\n',
    # herdr: print the canned reply for "<group> <verb>", or fail if none.
    "herdr": STUB + textwrap.dedent("""\
        f="$HERDR_REPLIES/$1-$2.json"
        [ -f "$f" ] || exit 1
        cat "$f"
        """),
}


class Sandbox:
    def __init__(self, test):
        self.root = Path(tempfile.mkdtemp(prefix="herdr-test-"))
        test.addCleanup(shutil.rmtree, self.root, True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name, body in STUBS.items():
            path = self.bin / name
            path.write_text(body)
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        self.log = self.root / "log"
        self.log.touch()
        self.tree = self.root / "tree.json"
        self.set_focused_pid(1)  # a pid no herdr client descends from
        self.replies = self.root / "replies"
        self.replies.mkdir()
        self.state = self.root / "state"

    def set_focused_pid(self, pid):
        self.tree.write_text(json.dumps({"nodes": [
            {"id": 7, "type": "con", "focused": True, "pid": pid,
             "nodes": [], "floating_nodes": []}], "floating_nodes": []}))

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith("HERDR")}
        env.update(PATH=f"{self.bin}:/usr/bin:/bin", STUB_LOG=str(self.log),
                   SWAY_TREE=str(self.tree), HERDR_REPLIES=str(self.replies),
                   HOME=str(self.root))
        env.update(extra)
        return env

    def calls(self, name=None):
        lines = self.log.read_text().splitlines()
        return [l for l in lines if name is None or l.split()[0] == name]


class AttentionTest(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(self)

    def fire(self, status, pane="w1:p2", focused="w9:p9", **data):
        event = {"event": "pane_agent_status_changed",
                 "data": {"type": "pane_agent_status_changed", "pane_id": pane,
                          "workspace_id": "w1", "agent_status": status,
                          "agent": "claude", **data}}
        context = {"workspace_id": "w1", "workspace_label": "TP Core",
                   "focused_pane_id": focused}
        r = subprocess.run(
            [sys.executable, str(ATTENTION)], capture_output=True, text=True,
            timeout=10, env=self.sb.env(
                HERDR_PLUGIN_EVENT_JSON=json.dumps(event),
                HERDR_PLUGIN_CONTEXT_JSON=json.dumps(context),
                HERDR_PLUGIN_STATE_DIR=str(self.sb.state)))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")
        return r

    def marker(self, pane="w1:p2"):
        return self.sb.state / "notified" / pane.replace(":", "_")

    def test_blocked_sends_one_labelled_critical_notification(self):
        self.fire("blocked", title="Refactor the parser")
        (call,) = self.sb.calls("notify-send")
        self.assertIn("--app-name=herdr", call)
        self.assertIn("--urgency=critical", call)
        self.assertIn("--print-id", call)
        self.assertIn("claude is waiting for you", call)
        self.assertIn("TP Core · Refactor the parser", call)
        self.assertNotIn("--replace-id", call)
        self.assertEqual(self.marker().read_text(), "41")

    def test_reblocking_replaces_rather_than_stacks(self):
        self.fire("blocked")
        self.fire("blocked")
        second = self.sb.calls("notify-send")[1]
        self.assertIn("--replace-id=41", second)

    def test_leaving_blocked_withdraws_the_notification(self):
        self.fire("blocked")
        self.fire("working")
        self.assertEqual(self.sb.calls("makoctl"), ["makoctl dismiss -n 41"])
        self.assertFalse(self.marker().exists())
        # …and the next block is a fresh notification, not a replacement.
        self.fire("blocked")
        self.assertNotIn("--replace-id", self.sb.calls("notify-send")[-1])

    def test_non_blocked_without_a_notification_touches_nothing(self):
        for status in ("idle", "working", "done", "unknown"):
            self.fire(status)
        self.assertEqual(self.sb.calls("notify-send"), [])
        self.assertEqual(self.sb.calls("makoctl"), [])

    def test_panes_are_tracked_independently(self):
        self.fire("blocked", pane="w1:p2")
        self.fire("idle", pane="w1:p3")
        self.assertEqual(self.sb.calls("makoctl"), [])
        self.assertTrue(self.marker("w1:p2").exists())

    def test_every_event_pokes_only_the_bar_by_exact_name(self):
        # `-x` is load-bearing: without it `waybar` also matches the
        # supervisor waybar_run.sh, which an untrapped RT signal kills.
        self.fire("blocked")
        self.fire("idle")
        self.assertEqual(self.sb.calls("pkill"),
                         ["pkill -RTMIN+9 -x waybar"] * 2)

    def test_no_notification_while_the_user_is_looking_at_that_pane(self):
        # A process whose comm is "herdr", descended from the "focused window".
        fake = self.sb.root / "herdr"
        shutil.copy("/usr/bin/sleep", fake)
        child = subprocess.Popen([str(fake), "30"])
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        deadline = time.time() + 5
        while Path(f"/proc/{child.pid}/comm").read_text().strip() != "herdr":
            self.assertLess(time.time(), deadline)
            time.sleep(0.05)
        self.sb.set_focused_pid(os.getpid())
        self.fire("blocked", pane="w1:p2", focused="w1:p2")
        self.assertEqual(self.sb.calls("notify-send"), [])
        # Same pane focused inside herdr, but herdr's window is not the focused
        # one: the user is elsewhere, so notify.
        self.sb.set_focused_pid(1)
        self.fire("blocked", pane="w1:p2", focused="w1:p2")
        self.assertEqual(len(self.sb.calls("notify-send")), 1)

    def test_malformed_input_is_silent(self):
        for raw in ("", "not json", json.dumps({"data": {}})):
            r = subprocess.run(
                [sys.executable, str(ATTENTION)], capture_output=True, text=True,
                timeout=10, env=self.sb.env(HERDR_PLUGIN_EVENT_JSON=raw,
                                            HERDR_PLUGIN_STATE_DIR=str(self.sb.state)))
            self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(self.sb.calls(), [])

    def test_a_failing_notifier_leaves_no_marker(self):
        (self.sb.bin / "notify-send").write_text(STUB + "exit 1\n")
        self.fire("blocked")
        self.assertFalse(self.marker().exists())


class ModuleTest(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(self)

    def reply(self, group, verb, result):
        (self.sb.replies / f"{group}-{verb}.json").write_text(
            json.dumps({"id": "x", "result": result}))

    def run_module(self, *args):
        r = subprocess.run([sys.executable, str(MODULE), *args],
                           capture_output=True, text=True, timeout=10,
                           env=self.sb.env())
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return r.stdout

    def agents(self, *statuses):
        self.reply("agent", "list", {"agents": [
            {"pane_id": f"w1:p{i}", "workspace_id": "w1", "agent": "claude",
             "agent_status": s, "terminal_title_stripped": f"task {i}"}
            for i, s in enumerate(statuses, 1)]})
        self.reply("workspace", "list", {"workspaces": [
            {"workspace_id": "w1", "label": "TP Core"}]})

    def test_herdr_not_running_hides_the_module(self):
        self.assertEqual(json.loads(self.run_module()), {"text": ""})

    def test_nothing_blocked_shows_a_quiet_working_count(self):
        # Always visible while herdr runs, so a glance proves the module is
        # alive — but dim, and counting only the agents actually working. No
        # `blocked`/`done` here: either now outranks `quiet` (see the
        # dedicated tests below), so this fixture is deliberately just
        # `working`.
        self.agents("working", "working")
        out = json.loads(self.run_module())
        self.assertEqual(out["text"].split("\n")[1], "2")
        self.assertEqual(out["class"], "quiet")
        self.assertIn("2 agents working", out["tooltip"])
        self.assertIn("TP Core · claude — task 1", out["tooltip"])
        self.assertIn("TP Core · claude — task 2", out["tooltip"])

    def test_idle_agents_are_listed_but_do_not_change_number_or_class(self):
        # idle sessions show up in the tooltip as "seen, not answered yet"
        # but never move the count or the state class away from `quiet`.
        self.agents("idle", "working")
        out = json.loads(self.run_module())
        self.assertEqual(out["text"].split("\n")[1], "1")
        self.assertEqual(out["class"], "quiet")
        self.assertIn("1 agent seen, not answered yet", out["tooltip"])
        self.assertIn("TP Core · claude — task 1", out["tooltip"])

    def test_done_only_is_amber_waiting(self):
        # done = finished while you weren't looking at that tab: an answer is
        # waiting for you, distinct from a plain working count.
        self.agents("working", "done", "done")
        out = json.loads(self.run_module())
        self.assertEqual(out["text"].split("\n")[1], "2")
        self.assertEqual(out["class"], "waiting")
        self.assertIn("2 sessions waiting for your answer", out["tooltip"])
        self.assertIn("TP Core · claude — task 2", out["tooltip"])
        self.assertIn("TP Core · claude — task 3", out["tooltip"])
        self.assertIn("Click: go to the first waiting", out["tooltip"])

    def test_blocked_and_done_blocked_wins(self):
        # A decision needed outranks an answer merely waiting.
        self.agents("done", "blocked", "working")
        out = json.loads(self.run_module())
        self.assertEqual(out["text"].split("\n")[1], "1")
        self.assertEqual(out["class"], "blocked")
        self.assertIn("1 session", out["tooltip"])  # the done section still lists
        self.assertIn("waiting for your answer", out["tooltip"])
        self.assertIn("Click: go to the first blocked", out["tooltip"])

    def test_done_and_working_is_waiting(self):
        self.agents("done", "working", "working")
        out = json.loads(self.run_module())
        self.assertEqual(out["text"].split("\n")[1], "1")
        self.assertEqual(out["class"], "waiting")
        self.assertIn("2 agents working", out["tooltip"])

    def test_no_agents_at_all_still_shows_zero(self):
        self.agents()
        out = json.loads(self.run_module())
        self.assertEqual((out["text"].split("\n")[1], out["class"]), ("0", "quiet"))

    def test_counts_only_blocked_agents(self):
        self.agents("blocked", "working", "blocked")
        out = json.loads(self.run_module())
        # The blocked count, not the working one (1) and not the total (3).
        self.assertEqual(out["text"].split("\n")[1], "2")
        self.assertEqual(out["class"], "blocked")
        self.assertIn("2 agents blocked — needs a decision", out["tooltip"])
        self.assertIn("TP Core · claude — task 1", out["tooltip"])
        self.assertIn("TP Core · claude — task 3", out["tooltip"])
        self.assertIn("TP Core · claude — task 2", out["tooltip"])  # working, its own section

    def test_output_is_utf8_not_escaped_surrogates(self):
        # Surrogate-pair escapes for the nerd-font glyph are legal JSON but not
        # what the other modules emit; keep the glyph literal.
        self.agents("blocked")
        self.assertNotIn("\\ud", self.run_module())

    def test_click_focuses_the_first_blocked_agent(self):
        self.agents("working", "blocked", "blocked")
        self.run_module("--focus")
        self.assertIn("herdr agent focus w1:p2", self.sb.calls("herdr"))

    def test_click_with_done_only_focuses_the_done_agent(self):
        self.agents("working", "done", "idle")
        self.run_module("--focus")
        self.assertIn("herdr agent focus w1:p2", self.sb.calls("herdr"))

    def test_click_with_blocked_and_done_focuses_the_blocked_agent(self):
        # blocked outranks done for the click target too.
        self.agents("done", "blocked")
        self.run_module("--focus")
        self.assertIn("herdr agent focus w1:p2", self.sb.calls("herdr"))
        self.assertEqual(
            [c for c in self.sb.calls("herdr") if "focus" in c],
            ["herdr agent focus w1:p2"])

    def test_click_with_only_idle_or_working_does_nothing(self):
        self.agents("idle", "working")
        self.run_module("--focus")
        self.assertEqual([c for c in self.sb.calls("herdr") if "focus" in c], [])
        self.assertEqual(self.sb.calls("swaymsg"), [])


BACKUP = REPO / "bin/.local/bin/herdr-session-backup"


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="herdr-backup-test-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.session = self.root / "config/herdr/session.json"
        self.session.parent.mkdir(parents=True)
        self.copies_dir = self.root / "state/herdr-backup"

    def write(self, workspaces):
        self.session.write_text(json.dumps(
            {"version": 3, "workspaces": [{"id": w} for w in workspaces]}))

    def run_backup(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
        env.update(XDG_CONFIG_HOME=str(self.root / "config"),
                   XDG_STATE_HOME=str(self.root / "state"),
                   HOME=str(self.root))
        return subprocess.run([sys.executable, str(BACKUP)], capture_output=True,
                              text=True, timeout=10, env=env)

    def copies(self):
        return sorted(self.copies_dir.glob("session-*.json"))

    def test_no_session_is_not_an_error(self):
        self.session.parent.rmdir()
        self.assertEqual(self.run_backup().returncode, 0)
        self.assertEqual(self.copies(), [])

    def test_copies_a_changed_session_and_skips_an_unchanged_one(self):
        # The existing copy has an old timestamp, so a second copy would get a
        # new name — two runs in the same second would hide a missing check.
        self.write(["wK", "wM"])
        self.copies_dir.mkdir(parents=True)
        old = self.copies_dir / "session-20260101T000000.json"
        old.write_bytes(self.session.read_bytes())
        self.assertEqual(self.run_backup().returncode, 0)
        self.assertEqual(self.copies(), [old])
        self.write(["wK", "wM", "wN"])
        self.assertEqual(self.run_backup().returncode, 0)
        self.assertEqual(len(self.copies()), 2)
        self.assertEqual(self.copies()[-1].read_bytes(), self.session.read_bytes())

    def test_an_emptied_session_never_displaces_the_good_copies(self):
        # herdr #4320: the session file rewritten valid but with nothing in it.
        self.write(["wK"])
        self.run_backup()
        good = self.copies()
        self.write([])
        r = self.run_backup()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no workspaces", r.stderr)
        self.assertEqual(self.copies(), good)

    def test_unparseable_session_fails_loudly(self):
        self.session.write_text("{truncated")
        r = self.run_backup()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.copies(), [])

    def test_rotation_keeps_the_newest(self):
        self.copies_dir.mkdir(parents=True)
        for i in range(60):
            (self.copies_dir / f"session-20260101T0000{i:02d}.json").write_text("{}")
        self.write(["wK"])
        self.run_backup()
        kept = self.copies()
        self.assertEqual(len(kept), 48)
        self.assertEqual(kept[-1].read_bytes(), self.session.read_bytes())
        self.assertNotIn("session-20260101T000000.json", [k.name for k in kept])


if __name__ == "__main__":
    unittest.main(verbosity=1)
