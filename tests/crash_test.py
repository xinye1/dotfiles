#!/usr/bin/env python3
"""Tests for bin/.local/bin/crash-diagnose (stdlib unittest). PLAYBOOK §9.33.

Design: docs/specs/2026-10-08-crash-diagnose-design.md (§6 is this file's table,
D1-D8). Every tool crash-diagnose runs -- journalctl, coredumpctl, notify-send,
herdr, kitty, claude, pacman, systemctl -- is a logging stub, and PATH holds
ONLY the stub directory, so nothing here can reach the live herdr server (which
runs every Claude pane), mako, the journal or systemd. HOME and XDG_STATE_HOME
are throwaway and every HERDR_* variable is dropped.

The journal fixtures are synthetic, built from the field names a real
coredump entry carries (the plan's Task 1 probe). Never paste a real entry in:
a real one carries the real process environment. COREDUMP_ENVIRON is present
here with marker values so D4 can prove none of it reaches the report.

CRASH_DIAGNOSE_BIN points the suite at another copy (the mutation check).
"""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = Path(os.environ.get("CRASH_DIAGNOSE_BIN", REPO / "bin/.local/bin/crash-diagnose"))
SPEC = REPO / "docs/specs/2026-10-08-crash-diagnose-design.md"
MID = "fc2e22bc6ee647b6b90729ab34a250b1"
ME = os.getuid()
OTHER = ME + 1
T0 = 1790977910000000              # 2026-10-02 21:51:50 UTC, in microseconds
MIN = 60 * 1_000_000

# Marker values: none of them may ever appear in a report (D4).
ENVIRON = {
    "ANTHROPIC_API_KEY": "sk-ant-fixture-environ-0001",
    "GH_TOKEN": "ghp_fixtureEnvironToken0002",
    "LANG": "xx_FIXTURE.environ-0003",
    "HOME": "/fixture/environ/home-0004",
}

STUB = r'''#!@PYTHON@
# A logging stand-in for one tool crash-diagnose runs. STUB_* env vars script it;
# canned output comes from $STUB_FIXTURES.
import json, os, subprocess, sys, time
name = os.path.basename(sys.argv[0]); args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps({"name": name, "argv": args, "t": time.time(),
        "env": {k: os.environ.get(k) for k in ("PATH", "WAYLAND_DISPLAY", "DEBUGINFOD_URLS",
                                               "LC_ALL", "HERDR_SOCKET_PATH")}}) + "\n")
fx = os.environ["STUB_FIXTURES"]
def mode(): return os.environ.get("STUB_" + name.upper().replace("-", "_"), "")
def emit(fname):
    path = os.path.join(fx, fname)
    if os.path.exists(path):
        sys.stdout.write(open(path).read())
        return True
    return False
if name == "journalctl":
    if "-f" in args:
        emit("follow.jsonl"); sys.stdout.flush()
        time.sleep(float(os.environ.get("STUB_FOLLOW_HOLD", "0.5")))
    elif any(a.startswith("COREDUMP_PID=") for a in args):
        emit("entry.jsonl")
    else:
        emit("journal.txt")
elif name == "coredumpctl":
    verb = next(a for a in args if a in ("list", "info", "debug"))
    if verb == "list":
        if not emit("list.json"):
            sys.stderr.write("No coredumps found.\n"); sys.exit(1)
    elif verb == "info":
        if os.environ.get("STUB_INFO") == "timeout":
            time.sleep(60)
        if os.environ.get("STUB_INFO") == "daemon":
            # A CLI that auto-starts a daemon: a grandchild in its own session keeps
            # the inherited stdout/stderr pipes open after this process exits.
            kid = os.fork()
            if kid == 0:
                os.setsid()
                time.sleep(30)
                os._exit(0)
            open(os.path.join(fx, "daemon.pid"), "w").write(str(kid))
            sys.stdout.flush()
            sys.exit(0)
        emit("info.txt")
    else:
        gdb = os.environ.get("STUB_GDB", "")
        if gdb == "timeout":
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            open(os.path.join(fx, "gdb-child.pid"), "w").write(str(child.pid))
            time.sleep(60)
        elif gdb == "fail":
            sys.stderr.write("Cannot find gdb\n"); sys.exit(1)
        elif gdb == "mismatch":
            print("warning: Build-id of /usr/lib/libc.so.6 does not match core file.")
            emit("gdb.txt")
        else:
            emit("gdb.txt")
elif name == "notify-send":
    if "-p" in args:
        counter = os.path.join(fx, "notify-id")
        if "-r" in args:
            nid = args[args.index("-r") + 1]
        else:
            nid = str(int(open(counter).read()) + 1 if os.path.exists(counter) else 41)
            open(counter, "w").write(nid)
        print(nid, flush=True)
    m = mode()
    if "--wait" in args and m in ("click", "click-late"):
        time.sleep(0.8 if m == "click-late" else 0.1)
        print("default", flush=True)
elif name == "herdr":
    m = mode()
    if args[:2] == ["tab", "create"]:
        pane = {"pane_id": "w1:p9", "tab_id": "w1:t9", "focused": True}
        shapes = {"": {"id": "1", "result": {"type": "tab_created", "tab": {"tab_id": "w1:t9"},
                                             "root_pane": pane}},
                  "bare": {"type": "tab_created", "tab": {"tab_id": "w1:t9"}, "root_pane": pane},
                  "pane": {"id": "1", "result": {"pane": pane}}}
        if m == "fail":
            sys.stderr.write('{"error":{"code":"server_unavailable"}}\n'); sys.exit(1)
        print("not json" if m == "garbage" else json.dumps(shapes[m]))
    elif args[:2] == ["pane", "run"] and m == "run-fail":
        sys.exit(1)
elif name == "kitty":
    sys.exit(1 if mode() == "fail" else 0)
elif name == "pacman":
    if mode() == "unowned":
        sys.stderr.write(f"error: No package owns {args[-1]}\n"); sys.exit(1)
    print(f"{args[-1]} is owned by waybar 0.15.0-3")
elif name == "systemctl":
    print("HOME=/x\nWAYLAND_DISPLAY=wayland-from-manager\nSWAYSOCK=/run/user/x/sway.sock")
'''

TOOLS = ("journalctl", "coredumpctl", "notify-send", "herdr", "kitty", "claude", "pacman",
         "systemctl")


def entry(pid=222, uid=ME, exe="/usr/bin/waybar", comm="waybar", ts=T0, sig=("6", "SIGABRT"),
          package='{"elfType":"coredump","elfArchitecture":"AMD x86-64"}'):
    """A coredump journal entry as `journalctl -o json --all` prints one."""
    return {
        "MESSAGE_ID": MID, "PRIORITY": "2", "SYSLOG_IDENTIFIER": "systemd-coredump",
        "COREDUMP_PID": str(pid), "COREDUMP_UID": str(uid), "COREDUMP_GID": "1001",
        "COREDUMP_COMM": comm, "COREDUMP_EXE": exe, "COREDUMP_CMDLINE": comm,
        "COREDUMP_SIGNAL": sig[0], "COREDUMP_SIGNAL_NAME": sig[1],
        "COREDUMP_TIMESTAMP": str(ts), "__REALTIME_TIMESTAMP": str(ts + 900_000),
        "COREDUMP_UNIT": "session-2.scope", "COREDUMP_SLICE": f"user-{uid}.slice",
        "COREDUMP_PACKAGE_JSON": package,
        "COREDUMP_FILENAME": f"/var/lib/systemd/coredump/core.{comm}.{uid}.x.{pid}.{ts}.zst",
        "COREDUMP_ENVIRON": "\n".join(f"{k}={v}" for k, v in ENVIRON.items()),
        "COREDUMP_PROC_STATUS": list(f"Name:\t{comm}\nPPid:\t4242\n".encode()),  # binary: a byte list
        "COREDUMP_PROC_MAPS": None,  # what journalctl prints for a field it will not show
        "MESSAGE": f"Process {pid} ({comm}) of user {uid} dumped core.\n\n"
                   f"Stack trace of thread {pid}:\n#0  0x00007f81bfa9a17c n/a (libc.so.6 + 0x9a17c)\n",
    }


def row(pid=222, uid=ME, ts=T0, exe="/usr/bin/waybar", sig=6, core="present"):
    """A `coredumpctl --json=short list` row."""
    return {"time": ts, "pid": pid, "uid": uid, "gid": 1001, "sig": sig, "corefile": core,
            "exe": exe, "size": 1234 if core == "present" else None}


class Sandbox:
    def __init__(self, test, tools=TOOLS):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home, self.bin, self.fx = self.root / "home", self.root / "bin", self.root / "fx"
        self.state, self.urls = self.root / "state", self.root / "debuginfod"
        for d in (self.home, self.bin, self.fx, self.state, self.urls):
            d.mkdir()
        for name in tools:
            self.stub(self.bin / name)
        self.log = self.root / "log.jsonl"
        self.log.write_text("")
        self.fixture("entry.jsonl", json.dumps(entry()) + "\n")
        self.fixture("list.json", json.dumps([row(pid=111, ts=T0 - 60 * MIN), row()]))
        self.fixture("info.txt", "           PID: 222 (waybar)\n        Signal: 6 (ABRT)\n"
                                 "Stack trace of thread 222:\n#0  0x00007f81bfa9a17c n/a (libc.so.6 + 0x9a17c)\n")
        self.fixture("gdb.txt", "Thread 1 (LWP 222):\n#0  0x00007f81bfa9a17c in __pthread_kill_implementation () at pthread_kill.c:44\n")
        self.fixture("journal.txt", "2026-10-02T21:51:49+00:00 host waybar[222]: [error] bar went away\n")

    @staticmethod
    def stub(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(STUB.replace("@PYTHON@", sys.executable))
        path.chmod(0o755)

    def fixture(self, name, content):
        (self.fx / name).write_text(content)

    def env(self, **extra):
        env = {"HOME": str(self.home), "PATH": str(self.bin), "TZ": "UTC",
               "XDG_STATE_HOME": str(self.state), "WAYLAND_DISPLAY": "wayland-test",
               "DEBUGINFOD_URLS": "https://debuginfod.invalid",
               "CRASH_DIAGNOSE_DEBUGINFOD_DIR": str(self.urls),
               "HERDR_SOCKET_PATH": "/nonexistent/crash-test.sock",
               "STUB_LOG": str(self.log), "STUB_FIXTURES": str(self.fx)}
        env.update(extra)
        return {k: v for k, v in env.items() if v is not None}

    def tool(self, *args, timeout=60, **extra):
        self.log.write_text("")
        return subprocess.run([sys.executable, str(TOOL), *args], env=self.env(**extra),
                              capture_output=True, text=True, timeout=timeout)

    def calls(self, name=None):
        rows = [json.loads(l) for l in self.log.read_text().splitlines()]
        return [r for r in rows if name is None or r["name"] == name]

    def toasts(self):
        return [c for c in self.calls("notify-send") if "--wait" in c["argv"]]

    def diagnosed_pids(self):
        return [a.split("=", 1)[1] for c in self.calls("journalctl") for a in c["argv"]
                if a.startswith("COREDUMP_PID=")]

    def reports(self):
        root = self.state / "crash-reports"
        return sorted(root.glob("*/report.md")) if root.exists() else []

    def report(self):
        [path] = self.reports()
        return path.read_text()


def spec_prompt():
    """The PROMPT blockquote of spec §3, joined into one line."""
    text = SPEC.read_text()
    block = text.split("**PROMPT**", 1)[1]
    lines = []
    for line in block.splitlines()[1:]:
        if line.startswith(">"):
            lines.append(line.lstrip("> ").strip())
        elif lines:
            break
    return " ".join(lines)


class SandboxTest(unittest.TestCase):
    def test_path_holds_only_the_stub_dir_and_no_herdr_identity_leaks(self):
        sb = Sandbox(self)
        env = sb.env()
        self.assertEqual(env["PATH"], str(sb.bin))
        self.assertFalse([k for k in env if k.startswith("HERDR_") and k != "HERDR_SOCKET_PATH"])
        self.assertTrue(env["HERDR_SOCKET_PATH"].startswith("/nonexistent/"))


class ReportTest(unittest.TestCase):  # D4
    def setUp(self):
        self.sb = Sandbox(self)

    def diagnose(self, **extra):
        r = self.sb.tool("diagnose", "222", **extra)
        self.assertNotEqual(r.returncode, 2, r.stderr)
        return self.sb.report()

    def test_sections_and_summary(self):
        text = self.diagnose()
        for heading in ("## Summary", "## History", "## Backtrace", "## Journal entry", "## Journal"):
            self.assertIn(f"\n{heading}\n", text)
        for line in ("- Executable: /usr/bin/waybar", "- Signal: SIGABRT", "- PID: 222",
                     "- Package: waybar 0.15.0-3", "- Core file: present",
                     "- Time: 2026-10-02 21:51:50"):
            self.assertIn(line, text)
        self.assertIn("2 crash(es) of /usr/bin/waybar", text)
        self.assertIn("n/a (libc.so.6 + 0x9a17c)", text)            # coredumpctl info
        self.assertIn("__pthread_kill_implementation", text)        # gdb
        self.assertIn("bar went away", text)                        # journal
        self.assertIn("PPid:\t4242", text)                          # a byte-list field, decoded
        self.assertNotIn("missing:", text)
        self.assertEqual(self.sb.calls("notify-send")[0]["argv"][-2], "Preparing crash report for waybar…")

    def test_the_environment_never_reaches_the_report(self):
        text = self.diagnose()
        self.assertNotIn("COREDUMP_ENVIRON", text)
        for value in ENVIRON.values():
            self.assertNotIn(value, text)

    def test_a_secret_in_a_journal_line_is_redacted(self):
        self.sb.fixture("journal.txt", f"waybar[222]: token={ENVIRON['GH_TOKEN']}\n")
        text = self.diagnose()
        self.assertNotIn(ENVIRON["GH_TOKEN"], text)
        self.assertIn("token=[redacted]", text)

    def test_the_entry_is_read_with_all_fields(self):
        self.diagnose()
        [query] = [c for c in self.sb.calls("journalctl") if f"COREDUMP_PID=222" in c["argv"]]
        self.assertIn("--all", query["argv"])
        self.assertIn(f"COREDUMP_UID={ME}", query["argv"])

    def test_gdb_gets_debuginfod_and_runs_batch(self):
        self.diagnose()
        [gdb] = [c for c in self.sb.calls("coredumpctl") if "debug" in c["argv"]]
        self.assertIn("-batch", next(a for a in gdb["argv"] if a.startswith("--debugger-arguments=")))
        self.assertEqual(gdb["env"]["DEBUGINFOD_URLS"], "https://debuginfod.invalid")

    def test_info_timeout_is_a_missing_line_and_claude_still_starts(self):
        text = self.diagnose(STUB_INFO="timeout", CRASH_DIAGNOSE_INFO_TIMEOUT="1")
        self.assertIn("missing: coredumpctl info -- it did not finish in 1 s", text)
        self.assertTrue([c for c in self.sb.calls("herdr") if c["argv"][:2] == ["pane", "run"]])

    def test_a_pipe_held_by_a_detached_grandchild_cannot_hang_run(self):  # PLAYBOOK §9.32
        import signal

        def reap():
            try:
                os.kill(int((self.sb.fx / "daemon.pid").read_text()), signal.SIGKILL)
            except (OSError, ValueError):
                pass
        self.addCleanup(reap)
        start = time.monotonic()
        try:
            self.sb.tool("diagnose", "222", timeout=15, STUB_INFO="daemon",
                         CRASH_DIAGNOSE_INFO_TIMEOUT="1")
            text = self.sb.report()
        except subprocess.TimeoutExpired:
            self.fail("diagnose hung on a pipe a detached grandchild still holds")
        self.assertLess(time.monotonic() - start, 10)
        self.assertIn("missing: coredumpctl info -- it did not finish in 1 s", text)

    def test_gdb_timeout_kills_gdb_and_says_no_symbolised_backtrace(self):
        start = time.monotonic()
        text = self.diagnose(STUB_GDB="timeout", CRASH_DIAGNOSE_GDB_TIMEOUT="1")
        self.assertLess(time.monotonic() - start, 20)
        self.assertIn("no symbolised backtrace: gdb did not finish in 1 s", text)
        self.assertIn("n/a (libc.so.6 + 0x9a17c)", text)   # the raw stack is still there
        child = int((self.sb.fx / "gdb-child.pid").read_text())
        time.sleep(0.2)
        self.assertFalse(Path(f"/proc/{child}").exists() and
                         "Z" not in Path(f"/proc/{child}/stat").read_text().split()[2],
                         "gdb's child outlived the timeout")

    def test_gdb_failure_is_a_missing_line(self):
        text = self.diagnose(STUB_GDB="fail")
        self.assertIn("missing: symbolised backtrace -- no symbolised backtrace: Cannot find gdb", text)

    def test_a_gone_core_skips_gdb_and_keeps_the_journal_entry(self):
        self.sb.fixture("list.json", json.dumps([row(core="missing")]))
        text = self.diagnose()
        self.assertEqual([c for c in self.sb.calls("coredumpctl") if "debug" in c["argv"]], [])
        self.assertIn("missing: symbolised backtrace -- the core file is missing", text)
        self.assertIn("- COREDUMP_FILENAME: /var/lib/systemd/coredump/core.waybar", text)

    def test_libraries_changed_since_the_crash_is_called_out(self):  # Review Focus 4
        text = self.diagnose(STUB_GDB="mismatch")
        self.assertIn("**Libraries changed since the crash**", text)
        self.assertLess(text.index("### Crash-time stack"), text.index("### Symbolised"))

    def test_package_json_name_wins_over_pacman(self):
        self.sb.fixture("entry.jsonl", json.dumps(entry(package='{"name":"waybar","version":"9.9"}')) + "\n")
        text = self.diagnose()
        self.assertIn("- Package: waybar 9.9", text)
        self.assertEqual(self.sb.calls("pacman"), [])

    def test_an_unowned_exe_is_a_missing_line(self):
        text = self.diagnose(STUB_PACMAN="unowned")
        self.assertIn("missing: package -- error: No package owns /usr/bin/waybar", text)
        [pac] = self.sb.calls("pacman")
        self.assertEqual(pac["env"]["LC_ALL"], "C")

    def test_no_such_crash_notifies_and_writes_nothing(self):
        self.sb.fixture("entry.jsonl", "")
        r = self.sb.tool("diagnose", "999")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no crash of yours with pid 999", self.sb.calls("notify-send")[0]["argv"][-2])
        self.assertEqual(self.sb.reports(), [])

    def test_another_users_entry_is_refused(self):
        self.sb.fixture("entry.jsonl", json.dumps(entry(uid=OTHER)) + "\n")
        self.assertEqual(self.sb.tool("diagnose", "222").returncode, 1)
        self.assertEqual(self.sb.reports(), [])


class LaunchTest(unittest.TestCase):  # D5
    def setUp(self):
        self.sb = Sandbox(self)

    def rdir(self):
        [path] = self.sb.reports()
        return str(path.parent)

    def test_herdr_tab_then_pane_run(self):
        r = self.sb.tool("diagnose", "222")
        self.assertEqual(r.returncode, 0, r.stderr)
        create, run = [c["argv"] for c in self.sb.calls("herdr")]
        self.assertEqual(create, ["tab", "create", "--label", "crash: waybar", "--cwd", self.rdir(),
                                  "--focus"])
        self.assertEqual(run[:3], ["pane", "run", "w1:p9"])
        self.assertEqual(self.sb.calls("kitty"), [])

    def test_every_tab_create_shape_yields_the_pane(self):
        for shape in ("", "bare", "pane"):
            with self.subTest(shape or "envelope"):
                self.sb.tool("diagnose", "222", STUB_HERDR=shape)
                runs = [c["argv"] for c in self.sb.calls("herdr") if c["argv"][:2] == ["pane", "run"]]
                self.assertEqual([r[2] for r in runs], ["w1:p9"])
                self.assertEqual(self.sb.calls("kitty"), [])

    def test_kitty_when_herdr_fails_or_answers_garbage(self):
        for mode in ("fail", "garbage", "run-fail"):
            with self.subTest(mode):
                r = self.sb.tool("diagnose", "222", STUB_HERDR=mode)
                self.assertEqual(r.returncode, 0, r.stderr)
                [kitty] = self.sb.calls("kitty")
                self.assertEqual(kitty["argv"][:3], ["--directory", self.rdir(), "claude"])

    def test_kitty_when_herdr_is_not_installed(self):
        sb = Sandbox(self, tools=[t for t in TOOLS if t != "herdr"])
        sb.tool("diagnose", "222")
        self.assertEqual(len(sb.calls("kitty")), 1)

    def test_both_failing_is_a_critical_toast_with_the_report_path(self):
        r = self.sb.tool("diagnose", "222", STUB_HERDR="fail", STUB_KITTY="fail")
        self.assertEqual(r.returncode, 1)
        last = self.sb.calls("notify-send")[-1]["argv"]
        self.assertEqual(last[last.index("-u") + 1], "critical")
        self.assertIn(f"{self.rdir()}/report.md", last[-1])

    def test_claude_missing_names_it_and_keeps_the_report(self):
        sb = Sandbox(self, tools=[t for t in TOOLS if t != "claude"])
        r = sb.tool("diagnose", "222")
        self.assertEqual(r.returncode, 1)
        last = sb.calls("notify-send")[-1]["argv"]
        self.assertEqual(last[-2], "Crash report: claude not found")
        self.assertEqual(len(sb.reports()), 1)
        self.assertIn(str(sb.reports()[0]), last[-1])
        self.assertEqual((sb.calls("herdr"), sb.calls("kitty")), ([], []))


class ServiceEnvTest(unittest.TestCase):  # Review Focus 1: started by systemd, not a shell
    def test_claude_and_herdr_in_local_bin_are_found(self):
        sb = Sandbox(self, tools=[t for t in TOOLS if t not in ("claude", "herdr")])
        for name in ("claude", "herdr"):
            sb.stub(sb.home / ".local/bin" / name)
        r = sb.tool("diagnose", "222")
        self.assertEqual(r.returncode, 0, r.stderr)
        [create, _] = sb.calls("herdr")
        self.assertTrue(create["env"]["PATH"].startswith(f"{sb.home}/.local/bin:"))

    def test_a_missing_display_comes_from_the_user_manager(self):
        sb = Sandbox(self)
        sb.tool("diagnose", "222", WAYLAND_DISPLAY=None, STUB_HERDR="fail")
        [kitty] = sb.calls("kitty")
        self.assertEqual(kitty["env"]["WAYLAND_DISPLAY"], "wayland-from-manager")

    def test_a_missing_debuginfod_url_comes_from_etc(self):
        sb = Sandbox(self)
        (sb.urls / "archlinux.urls").write_text("https://debuginfod.example\n")
        sb.tool("diagnose", "222", DEBUGINFOD_URLS=None)
        [gdb] = [c for c in sb.calls("coredumpctl") if "debug" in c["argv"]]
        self.assertEqual(gdb["env"]["DEBUGINFOD_URLS"], "https://debuginfod.example")


class PromptTest(unittest.TestCase):  # D6
    def test_the_prompt_is_the_spec_text(self):
        want = spec_prompt()
        self.assertTrue(want.startswith("Read report.md in this directory") and
                        want.endswith("without asking me first."), want)
        sb = Sandbox(self)
        sb.tool("diagnose", "222")
        [run] = [c["argv"] for c in sb.calls("herdr") if c["argv"][:2] == ["pane", "run"]]
        self.assertEqual(shlex.split(run[3]), ["claude", want])
        sb.tool("diagnose", "222", STUB_HERDR="fail")
        [kitty] = sb.calls("kitty")
        self.assertEqual(kitty["argv"][3:], [want])


class ListTest(unittest.TestCase):  # D7
    def setUp(self):
        self.sb = Sandbox(self)

    def test_own_crashes_newest_first_at_most_20(self):
        rows = [row(pid=1000 + i, ts=T0 + i * MIN) for i in range(25)]
        rows += [row(pid=5, uid=0, ts=T0 + 99 * MIN, exe="/opt/chrome", sig=11)]
        self.sb.fixture("list.json", json.dumps(rows))
        r = self.sb.tool("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 20)
        self.assertEqual(lines[0], "1024  10-02 22:15  waybar  SIGABRT")
        self.assertEqual(lines[-1].split()[0], "1005")
        for line in lines:
            self.assertRegex(line, r"^\d+  \d\d-\d\d \d\d:\d\d  \S+  SIG[A-Z0-9]+$")

    def test_a_crash_the_journal_holds_twice_is_listed_once(self):  # Review Focus 5
        self.sb.fixture("list.json", json.dumps([row(), row(), row(pid=7, ts=T0 + MIN)]))
        self.assertEqual(len(self.sb.tool("list").stdout.splitlines()), 2)
        self.sb.tool("diagnose", "222")
        self.assertIn("2 crash(es) of /usr/bin/waybar", self.sb.report())

    def test_no_coredumps_is_an_empty_list(self):
        (self.sb.fx / "list.json").unlink()
        r = self.sb.tool("list")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_diagnose_takes_a_whole_list_line(self):
        self.sb.fixture("list.json", json.dumps([row()]))
        line = self.sb.tool("list").stdout.splitlines()[0]
        r = self.sb.tool("diagnose", line)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.sb.diagnosed_pids(), ["222"])

    def test_diagnose_without_a_pid_is_a_usage_error(self):
        for arg in ("waybar", "", "12ab"):
            with self.subTest(arg):
                self.assertEqual(self.sb.tool("diagnose", arg).returncode, 2)


class RetentionTest(unittest.TestCase):  # D8
    def test_keeps_the_newest_20_and_always_this_one(self):
        sb = Sandbox(self)
        root = sb.state / "crash-reports"
        now = time.time()
        for i in range(22):  # mtime runs against the name order: retention is by mtime
            d = root / f"2027-01-01_00-00-{i:02d}_old"
            d.mkdir(parents=True)
            (d / "report.md").write_text("old")
            os.utime(d, (now - 1000 - i, now - 1000 - i))
        (root / "notes.txt").write_text("mine")
        sb.tool("diagnose", "222")
        left = sorted(d.name for d in root.iterdir() if d.is_dir())
        self.assertEqual(len(left), 20)
        self.assertIn("2026-10-02_21-51-50_waybar", left)
        self.assertNotIn("2027-01-01_00-00-19_old", left)   # the three oldest by mtime
        self.assertIn("2027-01-01_00-00-18_old", left)
        self.assertIn("2027-01-01_00-00-00_old", left)
        self.assertTrue((root / "notes.txt").exists())

    def test_rediagnosing_rewrites_the_same_report(self):
        sb = Sandbox(self)
        sb.tool("diagnose", "222")
        sb.tool("diagnose", "222")
        self.assertEqual(len(sb.reports()), 1)

class WatchUidTest(unittest.TestCase):  # D1
    def test_another_users_crash_is_ignored(self):
        sb = Sandbox(self)
        sb.fixture("follow.jsonl", json.dumps(entry(pid=111, uid=OTHER, comm="chrome")) + "\n"
                   + json.dumps(entry(pid=222)) + "\n")
        sb.tool("watch")
        toasts = sb.toasts()
        self.assertEqual(len(toasts), 1, toasts)
        self.assertEqual(toasts[0]["argv"][-2], "Crash: waybar (SIGABRT)")
        self.assertTrue(toasts[0]["argv"][-1].startswith("pid 222 · 1st since 10-02 21:51"))

    def test_root_crash_is_ignored(self):
        sb = Sandbox(self)
        sb.fixture("follow.jsonl", json.dumps(entry(pid=111, uid=0)) + "\n")
        self.assertEqual(sb.tool("watch").returncode, 1)
        self.assertEqual(sb.toasts(), [])

    def test_journal_is_followed_from_now_without_the_environment(self):
        sb = Sandbox(self)
        sb.fixture("follow.jsonl", "")
        r = sb.tool("watch")
        self.assertEqual(r.returncode, 1, "journalctl exiting must be a failure (Restart=on-failure)")
        [jc] = sb.calls("journalctl")
        for arg in ("-f", "-n", "0", "-o", "json", f"MESSAGE_ID={MID}"):
            self.assertIn(arg, jc["argv"])
        [fields] = [a for a in jc["argv"] if a.startswith("--output-fields=")]
        self.assertIn("COREDUMP_UID", fields)
        self.assertNotIn("ENVIRON", fields)

    def test_a_malformed_line_does_not_stop_the_watcher(self):
        sb = Sandbox(self)
        sb.fixture("follow.jsonl", "not json\n[1]\n" + json.dumps(entry()) + "\n")
        sb.tool("watch")
        self.assertEqual(len(sb.toasts()), 1)


class CoalesceTest(unittest.TestCase):  # D2
    def test_a_repeat_within_30_min_replaces_the_toast_and_after_is_new(self):
        sb = Sandbox(self)
        sb.fixture("follow.jsonl", "".join(json.dumps(e) + "\n" for e in (
            entry(pid=1, ts=T0),
            entry(pid=9, ts=T0 + 1 * MIN, exe="/usr/bin/foot", comm="foot"),
            entry(pid=2, ts=T0 + 10 * MIN),
            entry(pid=3, ts=T0 + 31 * MIN))))
        sb.tool("watch")
        t = [c["argv"] for c in sb.toasts()]
        self.assertEqual(len(t), 4, t)
        self.assertNotIn("-r", t[0])
        self.assertTrue(t[0][-1].startswith("pid 1 · 1st since 10-02 21:51"), t[0])
        self.assertNotIn("-r", t[1])                       # another exe: its own toast
        self.assertEqual(t[2][t[2].index("-r") + 1], "41")  # toast 1's id, from -p
        self.assertTrue(t[2][-1].startswith("pid 2 · 2nd since 10-02 21:51"), t[2])
        self.assertNotIn("-r", t[3])                       # 31 min after the first: new toast
        self.assertTrue(t[3][-1].startswith("pid 3 · 1st since 10-02 22:22"), t[3])

    def test_toast_shape(self):
        sb = Sandbox(self)
        sb.fixture("follow.jsonl", json.dumps(entry()) + "\n")
        sb.tool("watch")
        [t] = sb.toasts()
        a = t["argv"]
        # -t 0: a crash toast stays until dismissed (Xinye, 2026-10-09); mako's 8 s default hid it
        for flag, value in (("-u", "normal"), ("-a", "crash"), ("-t", "0"),
                            ("-A", "default=Diagnose with Claude")):
            self.assertEqual(a[a.index(flag) + 1], value)
        self.assertIn("-p", a)


class ClickTest(unittest.TestCase):  # D3
    def setUp(self):
        self.sb = Sandbox(self)

    def test_a_click_spawns_diagnose_for_that_pid(self):
        self.sb.fixture("follow.jsonl", json.dumps(entry(pid=222)) + "\n")
        self.sb.tool("watch", STUB_NOTIFY_SEND="click")
        self.assertEqual(self.sb.diagnosed_pids(), ["222"])
        self.assertTrue(self.sb.calls("herdr"))

    def test_a_dismissed_toast_starts_nothing(self):
        self.sb.fixture("follow.jsonl", json.dumps(entry(pid=222)) + "\n")
        self.assertEqual(self.sb.tool("watch", STUB_NOTIFY_SEND="").returncode, 1)
        self.assertEqual(len(self.sb.toasts()), 1)
        self.assertEqual(self.sb.diagnosed_pids(), [])
        self.assertEqual(self.sb.calls("herdr"), [])

    def test_a_click_on_a_replaced_toast_diagnoses_once_the_newest(self):  # Review Focus 2
        self.sb.fixture("follow.jsonl", json.dumps(entry(pid=1, ts=T0)) + "\n"
                        + json.dumps(entry(pid=2, ts=T0 + MIN)) + "\n")
        self.sb.tool("watch", STUB_NOTIFY_SEND="click-late", STUB_FOLLOW_HOLD="1.5")
        self.assertEqual(self.sb.diagnosed_pids(), ["2"])


class UnitFileTest(unittest.TestCase):
    """crash-watch.service, read as systemd would: one key=value per line, by section."""

    def unit(self):
        sections, current = {}, None
        path = REPO / "systemd/.config/systemd/user/crash-watch.service"
        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current = sections.setdefault(line[1:-1], {})
            elif line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                current[key.strip()] = value.strip()
        return sections

    def test_the_unit_runs_the_watcher_and_restarts_it(self):
        u = self.unit()
        self.assertEqual(u["Service"]["ExecStart"], "%h/.local/bin/crash-diagnose watch")
        self.assertEqual(u["Service"]["Restart"], "on-failure")
        self.assertEqual(u["Install"]["WantedBy"], "default.target")

    def test_a_restart_does_not_close_what_a_click_opened(self):  # Review Focus 3
        self.assertEqual(self.unit()["Service"]["KillMode"], "process")


if __name__ == "__main__":
    unittest.main()
