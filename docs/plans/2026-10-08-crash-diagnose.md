# Crash → Claude Diagnosis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A toast for each crash of the user's own processes, and a palette row for any recent one;
a click or a pick builds an evidence report and opens Claude on it in a herdr tab, under the
user's normal permission settings.

**Architecture:** One stdlib Python tool, `bin/.local/bin/crash-diagnose`, with three
subcommands. `watch` (run by `crash-watch.service`) follows the coredump journal entries and
raises one toast per executable per 30 min. `list` feeds the palette. `diagnose <pid>` writes
`report.md` (summary, history, the crash-time stack, a gdb backtrace, the journal entry, nearby
journal lines; never the process environment), keeps the newest 20 reports, then opens Claude on
it in herdr, falling back to kitty.

**Tech Stack:** Python 3.14 stdlib; systemd-coredump / coredumpctl (systemd 262), journalctl,
gdb 18.1 + debuginfod, pacman, notify-send + mako, herdr 0.8.0, kitty, claude.

**Spec:** `docs/specs/2026-10-08-crash-diagnose-design.md` (approved). Repo rules: `CLAUDE.md`,
`PLAYBOOK.md` §5.2 (stow folding), §9.29 (waybar supervision), §9.30 (herdr).
Probe findings: the ledger, `.superpowers/sdd/2026-10-08-crash-diagnose/progress.md` in the live
checkout (`~/repos/dotfiles`, gitignored).

**Ordering.** Capture (`feat/capture`) merges before this is built, and `feat/crash-diagnose` is
rebased onto it. Every edit here to `sway/.config/sway/menu.toml`, `tests/theme_test.sh`,
`CLAUDE.md`, `PLAYBOOK.md` and `packages.txt` is written against **capture's** version of the
file (its `Capture` palette rows, its `capture_test.py` lines, its §9.32). So this feature's
PLAYBOOK entry is **§9.33**. Task 1 Step 1 checks the rebase happened.

**Who does what.** No step needs `sudo` (nothing is installed). An implementer subagent does
Tasks 2-6 inside the worktree. **Task 1 Step 3 and all of Task 7 belong to Xinye or the
orchestrator**: they need a human click, change the live desktop (`stow`, `systemctl --user
enable`), or make a real crash. A subagent never runs them.

## Global Constraints

- A **crash** is a journal entry with `MESSAGE_ID=fc2e22bc6ee647b6b90729ab34a250b1` whose `COREDUMP_UID` is `os.getuid()`. Every other uid is out of scope (spec §1, §8).
- Claude starts only on a click (`default` from `notify-send --wait`) or a palette pick (spec X1).
- The report **never** contains `COREDUMP_ENVIRON` (no field name, no value) or the core file (spec §3).
- PROMPT is the spec §3 blockquote, verbatim; `tests/crash_test.py` reads it from the spec.
- At most one toast per executable per 30 min (`COALESCE_US`); a repeat replaces it with `notify-send -r <id>` and a count (spec X3).
- gdb gets at most 90 s (`GDB_TIMEOUT`); keep the newest 20 reports (`KEEP`) (spec X3).
- Reports go in `${XDG_STATE_HOME:-~/.local/state}/crash-reports/<YYYY-MM-DD_HH-MM-SS>_<exe basename>/report.md`.
- Toasts: `notify-send -u normal -a crash`; failures: `-u critical -a crash`, naming what failed and the report path.
- Tests stub every external tool (journalctl, coredumpctl, notify-send, herdr, kitty, claude, pacman, systemctl) on a PATH holding **only** the stub directory. Stubs carry an absolute `#!<python>` shebang. No test may reach the live herdr server, mako, the journal or systemd. `CRASH_DIAGNOSE_BIN` points the suite at another copy for mutation checks.
- The tool reads `HOME` from the environment (never `pwd`), so a sandboxed `HOME` is the whole of `~`.
- Never `pkill` anything by name, never `herdr server stop`, never `setsid` (PLAYBOOK §9.29, §9.30).
- Commit trailer, on every commit:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```

## Where the probes changed the design

The §6 probes ran at planning time (2026-10-09, read-only; ledger "Planning probes"). Each of
these is a place where the spec was wrong or silent. The plan settles it, and the PLAYBOOK entry
(Task 6) records it.

1. **`coredumpctl info` gives no symbols, and it is instant.** It prints the stack systemd-coredump
   recorded *at crash time* (0.01 s, frames like `n/a (waybar + 0x3058b)`). Spec §3's "gdb +
   debuginfod give symbols" is true only of `coredumpctl debug`. So the report has both:
   `coredumpctl -1 info` (30 s cap) and a gdb batch backtrace via
   `coredumpctl -1 debug --debugger-arguments="-batch -iex 'set debuginfod enabled on' -ex 'thread apply all bt'"`
   (90 s cap, cold 19.0 s / warm 1.6 s on the probe core). gdb in batch mode does not use
   debuginfod unless told to (no gdbinit on this machine sets it). This matches spec §5's "no
   symbolised backtrace plus the raw coredumpctl info".
2. **gdb can be worse than the crash-time stack.** On the probe core, a dozen libraries had been
   upgraded since the crash (`warning: Build-id of /usr/lib/libc.so.6 does not match core file`),
   and the crashing thread came out as `?? ()`. The report calls this out and keeps the crash-time
   stack first (Review Focus 4).
3. **The service is not a shell.** The user manager's environment has no `~/.local/bin` on PATH
   (where `claude` and `herdr` live) and no `DEBUGINFOD_URLS`. `DISPLAY`/`WAYLAND_DISPLAY`/
   `SWAYSOCK` only reach the manager when sway runs `systemctl --user import-environment`, which is
   *after* a `default.target` service has started. `session_env()` fills the gaps at click time:
   it prepends `~/.local/bin`, reads the display variables from `systemctl --user
   show-environment`, and reads `/etc/debuginfod/*.urls`, the same as `/etc/profile.d/debuginfod.sh`
   (Review Focus 1).
4. **`KillMode=process` in the unit.** A clicked toast starts `diagnose`, and that can open a
   kitty window with Claude in it. All of those are in the service's cgroup, so with the default
   KillMode a watcher restart (`Restart=on-failure`, or a `stow`/daemon-reload) would close a
   window someone is reading. herdr panes live in herdr's own cgroup and are unaffected
   (Review Focus 3). `systemd-analyze --user verify` accepts the unit with no warning.
5. **journalctl JSON nulls large fields.** `MESSAGE` (it holds the stack), `COREDUMP_PROC_MAPS`
   and others come out as `null` without `--all`, and binary fields come out as lists of byte
   values. `diagnose` reads its entry with `--all` and decodes both shapes. The watcher asks only
   for small fields (`--output-fields=`), so it never even sees the environment.
6. **`COREDUMP_PACKAGE_JSON` has no package name on Arch** (only `elfType`/`elfArchitecture`), so
   the `pacman -Qo <exe>` fallback is the path that actually works. It runs with `LC_ALL=C`
   because it is parsed.
7. **`coredumpctl --json=short list` has no `comm`, and the journal can hold one crash twice**
   (pid 3382861 has two identical rows). `list` uses the basename of `exe`, and dedupes on
   `(pid, time)` (Review Focus 5).
8. **herdr's `tab create` reply.** The installed binary's own API schema (`herdr api schema
   --json`, protocol 19) gives `{"id", "result": {"type": "tab_created", "tab", "root_pane":
   {"pane_id", …}}}`, so the pane is `.result.root_pane.pane_id`. No real tab was created to
   confirm what the CLI prints, so `pane_id()` also accepts four fallback shapes, with a test per
   shape, and anything else falls back to kitty.
9. **"recorded journal JSON fixtures".** A recorded real entry carries the real process
   environment, so the fixtures are **synthetic**. They use the field names the probe recorded,
   with marker values in `COREDUMP_ENVIRON`.
10. **Toast body `<n>th since <first date>`.** `n` is the crash's place in the current 30-min
    group, with a correct ordinal (`1st`, `2nd`, `3rd`, `11th`). The first date is the group's
    first crash (`%m-%d %H:%M`). The window runs on `COREDUMP_TIMESTAMP` from the group's first
    crash, not the wall clock: deterministic in tests, and immune to journal delivery lag.
    `notify-send -p` prints the id that `-r` needs.
11. **A click on a replaced toast** may be reported by both the old and the new `notify-send`.
    It diagnoses once, the newest pid (Review Focus 2).
12. **Retention goes by directory mtime, not by name.** Names start with the *crash* time, so
    re-diagnosing an old crash would otherwise prune its own fresh report. Only directories that
    match the report-name pattern are ever deleted.
13. **Defence in depth on secrets.** Beyond the field allowlist, any environment value whose name
    looks like a secret (`TOKEN|SECRET|PASS|KEY|AUTH|CRED|COOKIE`, value ≥ 8 chars) is redacted
    wherever it turns up: a journal line, a command line, a gdb string argument. Spec §8's caveat
    ("a secret passed on a command line would be included") still holds for values that are not
    in the environment.
14. **`stow -R bin` as well as `stow -R systemd`.** `bin` is unfolded too (§5.2), so the new script
    is absent until restowed. Spec §7 named only systemd. And **§5.2 has no `systemd` row**,
    although the spec cites it, so Task 6 adds one: unfolded, because `systemctl --user enable`
    writes `*.wants/` symlinks into `~/.config/systemd/user`.
15. **gdb goes in `packages.txt`.** It is installed today only as a dependency of `debugedit`, so a
    cleanup could orphan it, and then reports would lose their backtrace without anyone noticing.
    Spec "No new packages" still holds: nothing needs installing.

## Review Focus

1. **Started by the service, not a shell.** With PATH lacking `~/.local/bin` and the environment
   lacking `WAYLAND_DISPLAY` and `DEBUGINFOD_URLS`, a click must still find `claude`/`herdr`, give
   kitty a display and give gdb debuginfod (`ServiceEnvTest`, three tests, Task 2).
2. **A click on a coalesced toast** must diagnose exactly once, for the newest pid, even when both
   the old and the new `notify-send` report it
   (`test_a_click_on_a_replaced_toast_diagnoses_once_the_newest`, Task 3).
3. **Restarting the watcher** must not close a kitty + Claude window a click opened
   (`test_a_restart_does_not_close_what_a_click_opened`: `KillMode=process`, Task 4).
4. **Libraries upgraded since the crash** (as on the probe core) make gdb's frames wrong. The report
   must say so and put the crash-time stack first
   (`test_libraries_changed_since_the_crash_is_called_out`, Task 2).
5. **One crash recorded twice in the journal** must be listed once and counted once in History
   (`test_a_crash_the_journal_holds_twice_is_listed_once`, Task 2).

---

## File structure

| Path | Task | Responsibility |
|---|---|---|
| `bin/.local/bin/crash-diagnose` | 2, 3 | the tool: `list`, `diagnose` (Task 2), `watch` (Task 3) |
| `tests/crash_test.py` | 2-5 | the suite: D1-D8 plus the Review Focus tests, unit and menu checks |
| `systemd/.config/systemd/user/crash-watch.service` | 4 | runs `crash-diagnose watch` |
| `tests/check_consumers.sh` | 4 | live check: `crash-watch.service` is active |
| `tests/theme_test.sh` | 4 | runs `crash_test.py` (after capture's line) |
| `sway/.config/sway/menu.toml` | 5 | `Dev › Diagnose a crash…` (after capture's Dev rows) |
| `PLAYBOOK.md`, `CLAUDE.md`, `systemd/.config/systemd/user/README.md`, `packages.txt` | 6 | docs |

---

### Task 1: Pre-flight and the deferred probe (`[needs-prototype]`)

**Files:** none committed. Findings go in the ledger.

- [ ] **Step 1: Confirm the rebase onto capture.**

Run: `test -f sway/.config/sway/scripts/capture.py && grep -q '^### 9.32 Capture' PLAYBOOK.md && grep -q 'capture_test.py' tests/theme_test.sh && echo rebased`
Expected: `rebased`. If not, STOP: capture has not merged, or the branch was not rebased onto it,
and Tasks 4-6 would edit the wrong versions of shared files.

- [ ] **Step 2: Re-check the planning probes (read-only).** The ledger's "Planning probes" section
has P1 (coredumpctl) and P2 (herdr). Confirm that nothing they rest on has moved:

```bash
herdr --version                                   # 0.8.0 at planning
herdr api schema --json | python3 -c 'import json,sys; s=json.load(sys.stdin); r=[o for o in s["schemas"]["success_response"]["$defs"]["ResponseResult"]["oneOf"] if o.get("properties",{}).get("type",{}).get("const")=="tab_created"]; print(sorted(r[0]["properties"]))'
coredumpctl --json=short --no-pager list | python3 -c 'import json,os,sys; print(sum(1 for r in json.load(sys.stdin) if r["uid"]==os.getuid()), "own crashes")'
```
Expected: `herdr 0.8.0`; `['root_pane', 'tab', 'type']`; a non-zero count. If herdr changed
version and the keys differ, ledger the new keys and add the new path to `pane_id()`'s list in
Task 2 (with its own `shapes` entry in the stub). If the count is 0, make one harmless crash of
your own process, `sleep 60 & kill -SEGV $!`, and wait 2 s. Never run `herdr tab create`,
`herdr pane run`, `herdr server stop` or `pkill herdr` here. A bare `herdr` reaches the live
server that runs every Claude pane.

- [x] **Step 3: The mako click probe — DONE 2026-10-09 by the orchestrator with Xinye (ledger
"P3").** A left click prints `default`; `-p` prints the id first, then `default`; a `-t 0` toast
outlives `default-timeout=8000`, so crash toasts carry `-t 0` and stay until dismissed. The
original instructions are kept below for reference.

- [ ] **Step 3 (reference): The mako click probe (Xinye; the orchestrator relays).** It needs a human click on a
real toast, so a subagent must not run it. Ask Xinye to run each command and click the toast's
body once:

```bash
notify-send -A default=Diagnose --wait "probe" "click me"; echo "exit $?"
notify-send -p -A default=Diagnose --wait "probe" "click me"; echo "exit $?"
id=$(notify-send -p "probe" "first"); sleep 10; notify-send -r "$id" "probe" "second (replaces an expired toast)"
```
Expected: the first prints `default`. The second prints a number and then, after the click,
`default`. The third shows the second toast after the first has expired (mako
`default-timeout=8000`). Ledger all three outputs.
  - No `default` on a left click: mako is not invoking the default action. STOP and ask, and do not
    guess a mako config change. Tasks 2-6 can still be built, because the suite stubs notify-send,
    but the toast path cannot work until this is settled.
  - The second prints `default` first, or no id: no code change. The watcher keeps the id only if
    the first line is all digits, and treats any line equal to `default` as the click. Without an
    id, a repeat raises a new toast that still carries the count. Ledger it.
  - The third shows nothing: ledger it. A repeat after expiry is then silent, but the crash is
    still in the palette list.

---

### Task 2: `crash-diagnose list` and `diagnose`, with the suite's first half

**Files:**
- Create: `bin/.local/bin/crash-diagnose` (executable)
- Create: `tests/crash_test.py`

**Interfaces:**
- Produces, for Task 3: `own(uid) -> bool`; `text(value) -> str` (decodes a journal field: str,
  null, byte list, repeated list); `signame(n) -> str` (`"SIGABRT"`); `stamp(us, fmt="%m-%d %H:%M")
  -> str`; `notify(summary, body="", urgency="normal", env=None)`; `MESSAGE_ID`; `main(argv)` with a
  dispatch Task 3 extends; `cmd_diagnose(arg) -> int`, which Task 3's click starts as
  `[sys.executable, <this file>, "diagnose", pid]`.
- Produces, for Task 5: `crash-diagnose list` prints lines `"<pid>  <MM-DD HH:MM>  <exe basename>  <SIGNAME>"`
  (two spaces between fields), newest first, at most 20, and exits 0 even when there are none.
  `crash-diagnose diagnose "<a whole list line>"` takes the leading pid.
- Exit codes: `diagnose` returns 0 when Claude started, 1 when it could not (after a critical toast),
  2 on a usage error.
- Test seams (env): `CRASH_DIAGNOSE_BIN` (suite), `CRASH_DIAGNOSE_GDB_TIMEOUT`,
  `CRASH_DIAGNOSE_INFO_TIMEOUT`, `CRASH_DIAGNOSE_DEBUGINFOD_DIR` (default `/etc/debuginfod`).

- [ ] **Step 1: Write the suite** as `tests/crash_test.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it and watch it fail.**

Run: `python3 tests/crash_test.py`
Expected: `Ran 32 tests`, `FAILED (failures=30, errors=4)` (subtests count separately), because
`crash-diagnose` does not exist yet. `SandboxTest` passes: the harness itself works.

- [ ] **Step 3: Write `bin/.local/bin/crash-diagnose`**, then `chmod +x` it:

```python
#!/usr/bin/env python3
"""crash-diagnose -- crashes of your own processes, diagnosed by Claude on request.

Design: docs/specs/2026-10-08-crash-diagnose-design.md. PLAYBOOK §9.33.

  crash-diagnose watch                      crash-watch.service: a toast per new crash
  crash-diagnose list                       recent crashes, newest first (palette choices)
  crash-diagnose diagnose <pid | list line> build report.md, open Claude on it

Claude never starts unless the user clicks a toast or picks a crash. It runs
under the user's normal permission settings and is told to change nothing
without asking. The report never holds the process environment
(COREDUMP_ENVIRON) or the core file.

`diagnose` is often started by the systemd user service, not a shell: PATH has
no ~/.local/bin, and WAYLAND_DISPLAY and DEBUGINFOD_URLS may be unset.
session_env() puts those back before anything else runs.
"""
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

MESSAGE_ID = "fc2e22bc6ee647b6b90729ab34a250b1"
KEEP = 20                           # reports kept, and rows `list` offers
GDB_TIMEOUT = float(os.environ.get("CRASH_DIAGNOSE_GDB_TIMEOUT", "90"))
INFO_TIMEOUT = float(os.environ.get("CRASH_DIAGNOSE_INFO_TIMEOUT", "30"))
JOURNAL_SPAN_S = 120
JOURNAL_MAX_LINES = 400
SESSION_VARS = ("WAYLAND_DISPLAY", "DISPLAY", "SWAYSOCK", "XDG_CURRENT_DESKTOP")
# The report's "Journal entry" section. An allowlist, so the process environment
# (COREDUMP_ENVIRON) and the core itself (COREDUMP) can never ride along.
ENTRY_FIELDS = ("COREDUMP_PID", "COREDUMP_UID", "COREDUMP_COMM", "COREDUMP_EXE",
                "COREDUMP_CMDLINE", "COREDUMP_SIGNAL_NAME", "COREDUMP_TIMESTAMP",
                "COREDUMP_UNIT", "COREDUMP_SLICE", "COREDUMP_CGROUP", "COREDUMP_CWD",
                "COREDUMP_THREAD_NAME", "COREDUMP_PACKAGE_JSON", "COREDUMP_FILENAME",
                "COREDUMP_PROC_STATUS")
# Second line of defence: an environment value under a secret-looking name is
# redacted wherever it turns up (a journal line, a command line, a gdb argument).
SECRETISH = re.compile(r"TOKEN|SECRET|PASS|KEY|AUTH|CRED|COOKIE", re.I)
GDB_ARGS = "-batch -iex 'set debuginfod enabled on' -ex 'thread apply all bt'"
REPORT_DIR = re.compile(r"^\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d_")

# Fixed text; tests/crash_test.py pins it to spec §3.
PROMPT = ("Read report.md in this directory: a crash on this machine. Find the most likely "
          "cause, say how confident you are and why, and propose a fix. This machine's "
          "configuration lives in ~/repos/dotfiles; read its CLAUDE.md first if the crash "
          "involves it. Do not change any file or run anything that changes system state "
          "without asking me first.")


# --- plumbing ---

def own(uid):
    """Whether a crash's uid is this user's. Root and system-service crashes are out of scope."""
    return str(uid) == str(os.getuid())


def text(value):
    """A journal field as text. journalctl -o json gives a binary field as a list
    of byte values, a repeated field as a list of strings, and null for a field
    it would not print."""
    if isinstance(value, list):
        if all(isinstance(x, int) for x in value):
            return bytes(value).decode("utf-8", "replace")
        return "\n".join(text(x) for x in value)
    return "" if value is None else str(value)


def signame(number):
    try:
        return signal.Signals(int(number)).name
    except (TypeError, ValueError):
        return f"signal {number}"


def stamp(us, fmt="%m-%d %H:%M"):
    return datetime.fromtimestamp(int(us) / 1e6).strftime(fmt)


def run(argv, timeout=INFO_TIMEOUT, env=None):
    """(returncode, stdout, stderr). returncode is None on a timeout and 127 when
    the tool is missing. The child leads its own process group and a timeout
    kills the group: `coredumpctl debug` runs gdb as its child."""
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=env, start_new_session=True)
    except OSError as e:
        return 127, "", str(e)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        return None, "", ""
    return proc.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def notify(summary, body="", urgency="normal", env=None):
    try:
        subprocess.run(["notify-send", "-u", urgency, "-a", "crash", summary, body],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=5, env=env)
    except (OSError, subprocess.TimeoutExpired):
        pass
    print(f"crash-diagnose: {summary}" + (f": {body}" if body else ""), file=sys.stderr)


def session_env(base):
    """The environment diagnose and everything it starts run with."""
    env = dict(base)
    local_bin = os.path.join(env["HOME"], ".local", "bin")
    if local_bin not in env.get("PATH", "").split(":"):
        env["PATH"] = f"{local_bin}:{env.get('PATH', '')}"
    if not env.get("WAYLAND_DISPLAY"):
        # The service started before sway imported its variables into the user
        # manager; the manager has them now.
        _, out, _ = run(["systemctl", "--user", "show-environment"], timeout=5, env=env)
        for line in out.splitlines():
            key, _, value = line.partition("=")
            if key in SESSION_VARS and value and not env.get(key):
                env[key] = value
    if not env.get("DEBUGINFOD_URLS"):
        # What /etc/profile.d/debuginfod.sh does for a login shell.
        conf = Path(env.get("CRASH_DIAGNOSE_DEBUGINFOD_DIR", "/etc/debuginfod"))
        try:
            urls = " ".join(p.read_text().strip() for p in sorted(conf.glob("*.urls")))
        except OSError:
            urls = ""
        if urls.strip():
            env["DEBUGINFOD_URLS"] = urls.strip()
    return env


def state_dir(env):
    base = env.get("XDG_STATE_HOME") or os.path.join(env["HOME"], ".local", "state")
    return Path(base) / "crash-reports"


# --- list ---

def crashes(match=(), env=None):
    """This user's crashes, newest first, one row per crash (the journal can hold
    the same entry twice)."""
    rc, out, _ = run(["coredumpctl", "--json=short", "--no-pager", "list", *match], env=env)
    try:
        rows = json.loads(out) if rc == 0 and out.strip() else []
    except ValueError:
        rows = []
    seen, mine = set(), []
    for row in rows:
        key = (row.get("pid"), row.get("time"))
        if not own(row.get("uid")) or key in seen:
            continue
        seen.add(key)
        mine.append(row)
    return sorted(mine, key=lambda r: r.get("time") or 0, reverse=True)


def list_line(row):
    return (f"{row['pid']}  {stamp(row['time'])}  {Path(row.get('exe') or '?').name}"
            f"  {signame(row.get('sig'))}")


def cmd_list():
    for row in crashes()[:KEEP]:
        print(list_line(row))
    return 0


# --- diagnose: the report ---

def entry_for(pid, env):
    """The newest coredump journal entry for this pid of this user, or None.
    --all: without it journalctl prints null for any field over 4 KiB, and
    MESSAGE (the crash-time stack) is always one."""
    _, out, _ = run(["journalctl", "-o", "json", "--all", "--no-pager", "-n", "1",
                     f"MESSAGE_ID={MESSAGE_ID}", f"COREDUMP_PID={pid}",
                     f"COREDUMP_UID={os.getuid()}"], env=env)
    lines = [l for l in out.splitlines() if l.strip()]
    try:
        entry = json.loads(lines[-1]) if lines else None
    except ValueError:
        return None
    return entry if isinstance(entry, dict) and own(entry.get("COREDUMP_UID")) else None


def package(entry, exe, env):
    """("name version", None) or (None, why it is unknown)."""
    try:
        meta = json.loads(text(entry.get("COREDUMP_PACKAGE_JSON")) or "{}")
    except ValueError:
        meta = {}
    if isinstance(meta, dict) and meta.get("name"):
        return " ".join(str(meta[k]) for k in ("name", "version") if meta.get(k)), None
    if not exe:
        return None, "the journal entry names no executable"
    rc, out, err = run(["pacman", "-Qo", exe], env=dict(env, LC_ALL="C"))
    found = re.search(r" is owned by (\S+) (\S+)", out)
    if rc == 0 and found:
        return f"{found[1]} {found[2]}", None
    return None, (err.strip() or out.strip() or f"pacman exited {rc}")[-200:]


def fenced(body):
    return "~~~text\n" + body.rstrip("\n") + "\n~~~"


def missing(what, why):
    return f"missing: {what} -- {why}"


def scrub(report, entry):
    for line in text(entry.get("COREDUMP_ENVIRON")).splitlines():
        key, _, value = line.partition("=")
        if SECRETISH.search(key) and len(value) >= 8:
            report = report.replace(value, "[redacted]")
    return report


def build_report(entry, env):
    pid = text(entry.get("COREDUMP_PID"))
    comm = text(entry.get("COREDUMP_COMM")) or "?"
    exe = text(entry.get("COREDUMP_EXE"))
    sig = text(entry.get("COREDUMP_SIGNAL_NAME")) or signame(text(entry.get("COREDUMP_SIGNAL")))
    ts = int(text(entry.get("COREDUMP_TIMESTAMP")) or text(entry.get("__REALTIME_TIMESTAMP")) or 0)
    history = crashes([exe], env) if exe else []
    this = next((r for r in history if str(r.get("pid")) == pid), None)
    core = this.get("corefile", "unknown") if this else "unknown"
    pkg, pkg_why = package(entry, exe, env)

    out = [f"# Crash: {comm} ({sig})", "", "## Summary", "",
           f"- Executable: {exe or '?'}", f"- Command: {comm}", f"- Signal: {sig}",
           f"- Time: {stamp(ts, '%Y-%m-%d %H:%M:%S') if ts else '?'}", f"- PID: {pid}",
           f"- Package: {pkg}" if pkg else f"- {missing('package', pkg_why)}",
           f"- Core file: {core}", ""]

    out += ["## History", ""]
    if history:
        out += [f"{len(history)} crash(es) of {exe} on record, newest first:", "",
                "| time | pid | signal | core |", "|---|---|---|---|"]
        out += [f"| {stamp(r['time'], '%Y-%m-%d %H:%M')} | {r['pid']} | {signame(r.get('sig'))}"
                f" | {r.get('corefile', '?')} |" for r in history[:30]]
    else:
        out.append(missing("history", "coredumpctl listed no crashes of this executable"))
    out.append("")

    out += ["## Backtrace", "", "### Crash-time stack (coredumpctl info)", "",
            "Recorded by systemd-coredump when the process died, so it matches the binaries",
            "that crashed. Frames are module + offset; only exported symbols are named.", ""]
    rc, info, err = run(["coredumpctl", "-1", "info", "--no-pager", pid],
                        timeout=INFO_TIMEOUT, env=env)
    if rc is None:
        out.append(missing("coredumpctl info", f"it did not finish in {INFO_TIMEOUT:g} s"))
    elif rc != 0 or not info.strip():
        out.append(missing("coredumpctl info", (err.strip() or f"exit {rc}")[-300:]))
    else:
        out.append(fenced(info))
    out += ["", "### Symbolised (gdb + debuginfod)", ""]
    if core != "present":
        out.append(missing("symbolised backtrace", f"the core file is {core} (rotated or "
                           "never stored); the crash-time stack above is what remains"))
    else:
        rc, bt, err = run(["coredumpctl", "-1", "debug", "--no-pager", pid,
                           f"--debugger-arguments={GDB_ARGS}"], timeout=GDB_TIMEOUT, env=env)
        if rc is None:
            out.append(missing("symbolised backtrace", f"no symbolised backtrace: gdb did not "
                               f"finish in {GDB_TIMEOUT:g} s"))
        elif rc != 0 or not bt.strip():
            out.append(missing("symbolised backtrace", "no symbolised backtrace: "
                               + (err.strip() or f"exit {rc}")[-300:]))
        else:
            if "does not match core file" in bt + err:
                out += ["**Libraries changed since the crash** (gdb: build-id does not match",
                        "the core). Frames in those libraries may be wrong; trust the",
                        "crash-time stack above where they disagree.", ""]
            out.append(fenced(bt))
    out.append("")

    out += ["## Journal entry", ""]
    for key in ENTRY_FIELDS:
        value = text(entry.get(key))
        if value:
            out.append(f"- {key}: " + (value if "\n" not in value else "\n" + fenced(value)))
    out.append("")

    out += ["## Journal", "", "This user's journal, 2 minutes either side of the crash.", ""]
    if ts:
        t = ts // 1_000_000
        rc, lines, err = run(["journalctl", "--no-pager", "-q", "-o", "short-iso",
                              f"_UID={os.getuid()}", f"--since=@{t - JOURNAL_SPAN_S}",
                              f"--until=@{t + JOURNAL_SPAN_S}"], timeout=INFO_TIMEOUT, env=env)
        if rc == 0 and lines.strip():
            out.append(fenced("\n".join(lines.splitlines()[-JOURNAL_MAX_LINES:])))
        else:
            out.append(missing("journal", (err.strip() or "no lines")[-300:] if rc is not None
                               else f"journalctl did not finish in {INFO_TIMEOUT:g} s"))
    else:
        out.append(missing("journal", "the entry has no timestamp"))
    return scrub("\n".join(out) + "\n", entry), ts, exe


def write_report(entry, env):
    report, ts, exe = build_report(entry, env)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(exe).name or text(entry.get("COREDUMP_COMM")) or "unknown")
    rdir = state_dir(env) / f"{stamp(ts or 0, '%Y-%m-%d_%H-%M-%S')}_{name}"
    rdir.mkdir(parents=True, exist_ok=True)
    tmp = rdir / ".report.md.tmp"
    tmp.write_text(report)
    os.replace(tmp, rdir / "report.md")
    os.utime(rdir)  # retention goes by this
    return rdir


def prune(root, keep):
    """Keep the newest KEEP report directories by mtime; `keep` (this run's) always."""
    dirs = [d for d in root.iterdir() if d.is_dir() and REPORT_DIR.match(d.name)]
    others = sorted((d for d in dirs if d != keep), key=lambda d: d.stat().st_mtime,
                    reverse=True)
    for old in others[KEEP - 1:]:
        shutil.rmtree(old, ignore_errors=True)


# --- diagnose: opening Claude ---

def pane_id(out):
    """The new tab's root pane from `herdr tab create`. herdr 0.8.0's API schema
    (protocol 19) says {"id", "result": {"type": "tab_created", "tab",
    "root_pane": {"pane_id"}}}; the other shapes are fallbacks in case the CLI
    unwraps the envelope or a release renames the key."""
    try:
        doc = json.loads(out)
    except ValueError:
        return None
    for path in (("result", "root_pane", "pane_id"), ("root_pane", "pane_id"),
                 ("result", "pane", "pane_id"), ("pane", "pane_id"), ("pane_id",)):
        node = doc
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, str) and node:
            return node
    return None


def launch(rdir, comm, env):
    """Claude on the report: a herdr tab, else kitty. True when one started."""
    report = rdir / "report.md"
    if not shutil.which("claude", path=env["PATH"]):
        notify("Crash report: claude not found", f"claude is not on PATH; the report is {report}",
               "critical", env)
        return False
    rc, out, _ = run(["herdr", "tab", "create", "--label", f"crash: {comm}", "--cwd", str(rdir),
                      "--focus"], timeout=15, env=env)
    pane = pane_id(out) if rc == 0 else None
    if pane:
        rc, _, _ = run(["herdr", "pane", "run", pane, f"claude {shlex.quote(PROMPT)}"],
                       timeout=15, env=env)
        if rc == 0:
            return True
    try:
        kitty = subprocess.Popen(["kitty", "--directory", str(rdir), "claude", PROMPT], env=env,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        if kitty.wait(timeout=2) == 0:
            return True
    except subprocess.TimeoutExpired:
        return True  # still running: the window is up
    except OSError:
        pass
    notify("Crash report: could not open Claude",
           f"neither herdr nor kitty started; the report is {report}", "critical", env)
    return False


def cmd_diagnose(arg):
    found = re.match(r"\s*(\d+)(?!\S)", arg)
    if not found:
        print(USAGE, file=sys.stderr)
        return 2
    pid = found[1]
    env = session_env(os.environ)
    entry = entry_for(pid, env)
    if not entry:
        notify(f"Crash report: no crash of yours with pid {pid}", "", "critical", env)
        return 1
    comm = text(entry.get("COREDUMP_COMM")) or "?"
    notify(f"Preparing crash report for {comm}…", "", "low", env)
    rdir = write_report(entry, env)
    prune(rdir.parent, rdir)
    return 0 if launch(rdir, comm, env) else 1


USAGE = "usage: crash-diagnose watch | list | diagnose <pid | a line from list>"


def main(argv):
    if argv == ["list"]:
        return cmd_list()
    if len(argv) >= 2 and argv[0] == "diagnose":
        try:
            return cmd_diagnose(" ".join(argv[1:]))
        except Exception as e:  # a click must never fail in silence
            notify("Crash report failed", f"{type(e).__name__}: {e}", "critical")
            return 1
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run it.**

Run: `python3 tests/crash_test.py -v`
Expected: `Ran 32 tests … OK` in about 12 s. Any failure is a code problem. Do not loosen a test.

- [ ] **Step 5: Commit** `bin/.local/bin/crash-diagnose` and `tests/crash_test.py` with
`feat(crash): crash-diagnose list and diagnose — report first, Claude in herdr` and the trailer.

---

### Task 3: `crash-diagnose watch`: toasts, coalescing, the click

**Files:**
- Modify: `bin/.local/bin/crash-diagnose` (five insertions, below)
- Modify: `tests/crash_test.py` (three classes before `if __name__ == "__main__":`)

**Interfaces:**
- Consumes (Task 2): `own`, `text`, `signame`, `stamp`, `MESSAGE_ID`, `main`, and the `diagnose`
  subcommand, started as `[sys.executable, os.path.abspath(__file__), "diagnose", pid]`.
- Produces, for Task 4: `crash-diagnose watch` runs until journalctl's stream ends and then exits
  **1**, so `Restart=on-failure` restarts it.

- [ ] **Step 1: Add the tests.** Insert before the final `if __name__ == "__main__":` of
`tests/crash_test.py`, after `class RetentionTest`, separated by two blank lines:

```python
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
```

- [ ] **Step 2: Run them and watch them fail.**

Run: `python3 tests/crash_test.py`
Expected: `Ran 41 tests`, `FAILED`. The nine new tests fail (each one runs `watch`, which is still a
usage error, exit 2), and Task 2's 32 still pass.

- [ ] **Step 3: Implement `watch`.** Five insertions in `bin/.local/bin/crash-diagnose`:

(a) after `import sys`:
```python
import threading
```

(b) directly after the `MESSAGE_ID = "fc2e22bc6ee647b6b90729ab34a250b1"` line:
```python
COALESCE_US = 30 * 60 * 1_000_000   # one toast per executable per 30 min
# What the watcher asks journalctl for: never the environment.
WATCH_FIELDS = ("COREDUMP_UID", "COREDUMP_PID", "COREDUMP_EXE", "COREDUMP_COMM",
                "COREDUMP_SIGNAL", "COREDUMP_SIGNAL_NAME", "COREDUMP_TIMESTAMP")
```

(c) after `def stamp(…)` and its two blank lines:
```python
def ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
```

(d) directly before the `USAGE = "usage: …"` line, followed by two blank lines:
```python
# --- watch ---

class Toasts:
    """One toast per executable per COALESCE_US; a repeat replaces it with a count."""

    def __init__(self):
        self.lock = threading.Lock()
        self.groups = {}
        self.threads = []

    def crash(self, e):
        exe = text(e.get("COREDUMP_EXE")) or text(e.get("COREDUMP_COMM")) or "?"
        pid = text(e.get("COREDUMP_PID"))
        comm = text(e.get("COREDUMP_COMM")) or Path(exe).name
        sig = text(e.get("COREDUMP_SIGNAL_NAME")) or signame(text(e.get("COREDUMP_SIGNAL")))
        ts = int(text(e.get("COREDUMP_TIMESTAMP")) or text(e.get("__REALTIME_TIMESTAMP")) or 0)
        with self.lock:
            group = self.groups.get(exe)
            if group and ts - group["first"] < COALESCE_US:
                group["count"] += 1
            else:
                group = self.groups[exe] = {"first": ts, "count": 1, "nid": None}
            group.update(pid=pid, diagnosed=False)
            body = f"pid {pid} · {ordinal(group['count'])} since {stamp(group['first'])}"
            argv = ["notify-send", "-u", "normal", "-a", "crash", "-t", "0", "-p",
                    "-A", "default=Diagnose with Claude", "--wait"]
            if group["nid"]:
                argv += ["-r", group["nid"]]
        argv += [f"Crash: {comm} ({sig})", body]
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True)
        except OSError:
            return
        # -p prints the id at once; read it here, before the next entry, so a
        # repeat a moment later can replace this toast.
        first = proc.stdout.readline().strip()
        if first.isdigit():
            with self.lock:
                group["nid"] = first
        thread = threading.Thread(target=self.await_click, args=(proc, group, first), daemon=True)
        thread.start()
        self.threads.append(thread)

    def await_click(self, proc, group, first):
        replies = [first] + [line.strip() for line in proc.stdout]
        proc.wait()
        if "default" not in replies:
            return  # dismissed or expired: the crash stays in the palette list
        with self.lock:
            # A replaced toast can report the click twice (its old and new
            # notify-send); diagnose once, the newest crash.
            if group["diagnosed"]:
                return
            group["diagnosed"] = True
            pid = group["pid"]
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "diagnose", pid],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         start_new_session=True)

    def join(self, timeout):
        for thread in self.threads:
            thread.join(timeout)


def watch():
    proc = subprocess.Popen(["journalctl", "-f", "-n", "0", "-o", "json", "--no-pager",
                             f"--output-fields={','.join(WATCH_FIELDS)}",
                             f"MESSAGE_ID={MESSAGE_ID}"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True)
    toasts = Toasts()
    for line in proc.stdout:
        try:
            entry = json.loads(line)
            if isinstance(entry, dict) and own(entry.get("COREDUMP_UID")):
                toasts.crash(entry)
        except Exception as e:  # one bad entry must not stop the watcher
            print(f"crash-diagnose: skipped an entry: {type(e).__name__}: {e}", file=sys.stderr)
    proc.wait()
    toasts.join(5)
    print(f"crash-diagnose: journalctl exited ({proc.returncode})", file=sys.stderr)
    return 1  # Restart=on-failure brings the watcher back
```

(e) as the first two lines of `main(argv)`:
```python
    if argv == ["watch"]:
        return watch()
```

- [ ] **Step 4: Run it.**

Run: `python3 tests/crash_test.py -v`
Expected: `Ran 41 tests … OK` in about 18 s.

- [ ] **Step 5: Commit** both files with
`feat(crash): crash-diagnose watch — one toast per executable per 30 min, click to diagnose` and the trailer.

---

### Task 4: `crash-watch.service`, the live check, and theme_test

**Files:**
- Create: `systemd/.config/systemd/user/crash-watch.service`
- Modify: `tests/crash_test.py` (one class before `if __name__ == "__main__":`)
- Modify: `tests/check_consumers.sh` (a new block between `# --- herdr ---`'s `fi` and `# --- yazi ---`)
- Modify: `tests/theme_test.sh` (after capture's `python3 "$REPO/tests/capture_test.py" 2>/dev/null` line)

- [ ] **Step 1: Add the unit test.** Insert before `if __name__ == "__main__":` of `tests/crash_test.py`:

```python
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
```

- [ ] **Step 2: Run it.** `python3 tests/crash_test.py UnitFileTest` → 2 errors (no unit file).

- [ ] **Step 3: Write `systemd/.config/systemd/user/crash-watch.service`:**

```ini
[Unit]
Description=crash-diagnose: a toast for each crash of your own processes (PLAYBOOK §9.33)

[Service]
ExecStart=%h/.local/bin/crash-diagnose watch
Restart=on-failure
RestartSec=5
# A click starts `crash-diagnose diagnose`, which can open a kitty window with
# Claude in it; all of them are children of this service. KillMode=process
# stops only the watcher, so restarting it never closes a window being read.
KillMode=process

[Install]
WantedBy=default.target
```

- [ ] **Step 4: Verify the unit** against a throwaway `HOME`, so that `%h` resolves to a copy of the
script and the live `~` is not involved. This only parses the file; it loads nothing into the
user manager:

```bash
h=$(mktemp -d) && mkdir -p "$h/.local/bin" && cp bin/.local/bin/crash-diagnose "$h/.local/bin/"
HOME=$h systemd-analyze --user verify systemd/.config/systemd/user/crash-watch.service; echo "rc=$?"
rm -rf "$h"
```
Expected: no output and `rc=0`. A warning about `KillMode` here means systemd changed its mind about
`process`. Ledger it and ask; do not drop the line.

- [ ] **Step 5: The live check.** In `tests/check_consumers.sh`, insert between the herdr block's
final `fi` and `# --- yazi ---`:

```sh
# --- crash-watch (crash-diagnose's watcher, PLAYBOOK §9.33) ---
# A dead watcher looks exactly like a machine with no crashes: no toast either
# way. Restart=on-failure covers journalctl exiting; this covers the unit never
# having been linked or enabled. systemd/ is unfolded, so a new unit file is
# absent until `stow -R systemd` (§5.2).
if have systemctl && systemctl --user show-environment >/dev/null 2>&1; then
    if [ ! -f "$HOME/.config/systemd/user/crash-watch.service" ]; then
        no "crash-watch.service is active" "not installed: \`stow -R systemd\` (the package is unfolded)"
    elif state=$(systemctl --user is-active crash-watch.service 2>&1); then
        ok "crash-watch.service is active"
    else
        no "crash-watch.service is active" "$state: systemctl --user enable --now crash-watch.service"
    fi
else
    sk "crash-watch.service is active" "no systemd user manager to ask"
fi
```

- [ ] **Step 6: Hook the suite into theme_test.sh.** After capture's
`python3 "$REPO/tests/capture_test.py" 2>/dev/null` line, add:

```sh

# crash-diagnose (PLAYBOOK §9.33): every tool is a stub on a PATH holding only
# the stub dir, so it never reaches herdr, mako, the journal or systemd. A
# failure aborts.
python3 "$REPO/tests/crash_test.py" 2>/dev/null
```

- [ ] **Step 7: Run everything.**

Run: `python3 tests/crash_test.py && sh tests/theme_test.sh && sh -n tests/check_consumers.sh && sh tests/check_consumers.sh`
Expected: crash 43 OK; theme_test PASS. check_consumers: every earlier check as before, plus
**exactly one** new FAIL, `crash-watch.service is active`, with the hint `not installed: stow -R
systemd`. That FAIL is correct until Task 7 deploys the unit. Ledger it as expected-red, and do not
stow or enable anything here: that is Task 7, and it is not a subagent's job.

- [ ] **Step 8: Commit** the unit, `tests/crash_test.py`, `tests/check_consumers.sh` and
`tests/theme_test.sh` with `feat(crash): crash-watch.service; consumers check; theme_test runs crash_test`
and the trailer.

---

### Task 5: The palette row `Dev › Diagnose a crash…`

**Files:**
- Modify: `sway/.config/sway/menu.toml` (capture's version, after the `herdr: back up sessions now` row, the last `Dev` row)
- Modify: `tests/crash_test.py` (one class before `if __name__ == "__main__":`)

**Interfaces:** Consumes (Task 2) `crash-diagnose list` and `crash-diagnose diagnose <list line>`.
`menu.py` runs `choices` and `run` with its fixed action PATH (`~/.local/bin` first). It
`shlex.quote`s the picked line into `{choice}`, so `diagnose` receives the whole line as one
argument. It runs `run` synchronously and raises its own failure toast on a non-zero exit.

- [ ] **Step 1: Add the test.** Insert before `if __name__ == "__main__":` of `tests/crash_test.py`:

```python
class MenuRowTest(unittest.TestCase):
    def test_dev_diagnose_a_crash_row(self):
        import tomllib
        rows = tomllib.loads((REPO / "sway/.config/sway/menu.toml").read_text())["action"]
        [r] = [r for r in rows if (r["group"], r["label"]) == ("Dev", "Diagnose a crash…")]
        self.assertEqual(r["choices"], "crash-diagnose list")
        self.assertEqual(r["run"], "crash-diagnose diagnose {choice}")
```

- [ ] **Step 2: Run it.** `python3 tests/crash_test.py MenuRowTest` → 1 error (unpacking finds no row).

- [ ] **Step 3: Add the row.** After the block that ends `run = "herdr-session-backup"`, and before
`# --- Sway ---`, insert:

```toml

# Pick a recent crash of your own processes: crash-diagnose builds report.md
# and opens Claude on it in a herdr tab (PLAYBOOK §9.33). The pick is a whole
# `crash-diagnose list` line; diagnose takes its leading pid.
[[action]]
group = "Dev"
label = "Diagnose a crash…"
icon = "tools-report-bug"
keywords = ["coredump", "segfault", "abort", "claude"]
choices = "crash-diagnose list"
run = "crash-diagnose diagnose {choice}"
```
(`tools-report-bug` exists in Papirus-Dark's `actions`.)

- [ ] **Step 4: Run the suites.**

Run: `python3 tests/crash_test.py && python3 tests/menu_test.py && sh tests/theme_test.sh`
Expected: crash 44 OK. menu_test OK, including `RepoMenuTest`, the rot guard: it links the
sandbox `~/.local/bin` to the repo's `bin/.local/bin`, so `crash-diagnose` resolves. theme_test PASS.

- [ ] **Step 5: Commit** `sway/.config/sway/menu.toml` and `tests/crash_test.py` with
`feat(crash): palette row Dev › Diagnose a crash…` and the trailer.

---

### Task 6: Docs, the package line, and the mutation proof

**Files:** `PLAYBOOK.md`, `CLAUDE.md`, `systemd/.config/systemd/user/README.md`, `packages.txt`

- [ ] **Step 1: packages.txt.** Add `gdb` between `fzf` and `git`, keeping the alphabetical order.
In PLAYBOOK §4.2's table, add a row after `kanshi`:
`| \`gdb\` | repo | crash-diagnose's symbolised backtrace (§9.33). Installed today only as a dependency of \`debugedit\`, so a cleanup could orphan it, and a report then just says "no symbolised backtrace" |`.

- [ ] **Step 2: PLAYBOOK §5.2.** Add a row to the fold table, after `bin`:
`| \`systemd\` | **No** | \`systemctl --user enable\` writes \`*.wants/\` symlinks into \`~/.config/systemd/user\` (\`default.target.wants\`, \`timers.target.wants\`): untracked content inside the package directory. A new unit file is therefore absent until \`stow -R systemd\`, and \`systemctl --user daemon-reload\` comes after that. |`

- [ ] **Step 3: PLAYBOOK §9.33.** Append after §9.32, before `## 10. Troubleshooting`, a section
`### 9.33 Crash → Claude: a toast, a report, and Claude under normal permissions`. It holds, in
this order:
  1. What it is: spec §0 in two sentences. It is Omarchy's `omarchy-agent-crash` minus the permission
     bypass. It is not sway-specific and is meant to survive the Omarchy migration.
  2. The flow: `crash-watch.service` → toast "Crash: <comm> (<signal>)" with the action "Diagnose with
     Claude" → click → `crash-diagnose diagnose <pid>` → `report.md` → herdr tab `crash: <comm>`
     running `claude "<PROMPT>"`. Or the palette's `Dev › Diagnose a crash…`. Claude never starts
     without a click or a pick.
  3. What the report holds, and what it never holds (`COREDUMP_ENVIRON`, the core). The secret
     redaction (item 13 of "Where the probes changed the design"), and spec §8's honest caveats
     verbatim: the report goes to Anthropic's API; command lines and journal lines are included;
     debuginfod is network access at click time; root and system crashes are out of scope; the
     30-min coalescing can hide a storm, and the count in the replaced toast is the signal.
  4. The probe facts that shaped it: items 1-8 and 14 of that list, one short paragraph each,
     with the numbers (0.01 s info, 19.0 s / 1.6 s gdb, the build-id warning, `MESSAGE` null
     without `--all`, `PACKAGE_JSON` without a name, the duplicate pid). That covers the service
     environment gaps and `KillMode=process`.
  5. Operating it: `systemctl --user status crash-watch`; the watcher's own log is
     `journalctl --user -u crash-watch` (the clicked `diagnose` inherits its stderr). Reports live
     in `~/.local/state/crash-reports/`, newest 20 kept by mtime. A palette pick that fails shows
     two toasts, crash-diagnose's own plus menu.py's generic one (menu.py §7 behaviour; harmless).
  6. The suite: `python3 tests/crash_test.py`, ~20 s, stubs only on a stub-only PATH, synthetic
     fixtures (item 9). `CRASH_DIAGNOSE_BIN` for mutation checks; it was built by killing 8 of 8
     mutants (Step 6).
  7. The manual smoke from Task 7.

- [ ] **Step 4: CLAUDE.md.** In the suite list, after `python3 tests/capture_test.py …`, add
`python3 tests/crash_test.py   # crash → Claude diagnosis; stubs only; also run by theme_test.sh`.
After the capture Verify paragraph, add:
"**Run `tests/crash_test.py` after any edit to `bin/.local/bin/crash-diagnose` or
`crash-watch.service`.** Every tool it runs (journalctl, coredumpctl, notify-send, herdr, kitty,
claude, pacman, systemctl) is a stub on a PATH holding only the stub directory, so it never
reaches the live herdr server, mako or the journal. Its fixtures are synthetic: never paste a real
coredump entry in, because `COREDUMP_ENVIRON` is the process environment. `CRASH_DIAGNOSE_BIN`
points it at a copy for mutation checks (§9.33)."

- [ ] **Step 5: systemd/.config/systemd/user/README.md.** Append:

```markdown

# crash-watch

`crash-diagnose watch`: a toast for each crash of your own processes, with "Diagnose with Claude"
(PLAYBOOK §9.33). `KillMode=process`, so a restart never closes a Claude window a click opened.
This package is unfolded: a new unit needs `stow -R systemd` first.

    systemctl --user daemon-reload
    systemctl --user enable --now crash-watch.service
```

- [ ] **Step 6: Mutation proof.** For each mutant, copy `bin/.local/bin/crash-diagnose` to
`/tmp/crash-mut-<name>`, apply the one edit, and run
`CRASH_DIAGNOSE_BIN=/tmp/crash-mut-<name> python3 tests/crash_test.py`. Each one must FAIL, at
least on the named test. The first three are the spec's §6 mutations.

| Mutant | Edit | Must turn red |
|---|---|---|
| uid filter (spec) | in `own()`: `return str(uid) == str(os.getuid())` → `return True` | D1 `test_another_users_crash_is_ignored`, `test_root_crash_is_ignored` |
| coalesce window (spec) | `COALESCE_US = 30 * 60 * 1_000_000` → `COALESCE_US = 0` | D2 `test_a_repeat_within_30_min_replaces_the_toast_and_after_is_new` |
| environ (spec) | `ENTRY_FIELDS`: `"COREDUMP_PROC_STATUS")` → `"COREDUMP_PROC_STATUS", "COREDUMP_ENVIRON")` | D4 `test_the_environment_never_reaches_the_report` |
| no scrub | in `scrub()`: `report = report.replace(value, "[redacted]")` → `pass` | `test_a_secret_in_a_journal_line_is_redacted` |
| click twice | in `await_click()`: delete `if group["diagnosed"]:` and its `return` | `test_a_click_on_a_replaced_toast_diagnoses_once_the_newest` |
| kill child only | in `run()`: `os.killpg(proc.pid, signal.SIGKILL)` → `proc.kill()` | `test_gdb_timeout_kills_gdb_and_says_no_symbolised_backtrace` |
| no dedupe | in `crashes()`: `if not own(row.get("uid")) or key in seen:` → `if not own(row.get("uid")):` | `test_a_crash_the_journal_holds_twice_is_listed_once` |
| prune by name | in `prune()`: `key=lambda d: d.stat().st_mtime` → `key=lambda d: d.name` | D8 `test_keeps_the_newest_20_and_always_this_one` |

Ledger one line per mutant (name → red tests), then `rm /tmp/crash-mut-*`.

- [ ] **Step 7: Run everything and commit.**

Run: `python3 tests/crash_test.py && python3 tests/menu_test.py && sh tests/theme_test.sh`
Commit `PLAYBOOK.md CLAUDE.md systemd/.config/systemd/user/README.md packages.txt` with
`docs(crash): PLAYBOOK §9.33, §5.2 systemd row, CLAUDE.md test line, unit README, gdb` and the trailer.

---

### Task 7: Rollout and manual smoke (Xinye / orchestrator only, matching spec §7)

Everything here touches the live desktop. A subagent never runs it.

- [ ] **Step 1: Merge.** The branch goes through the normal PR (CodeRabbit gate) into `main`,
after capture. Then, in the live checkout: `cd ~/repos/dotfiles && git pull`.

- [ ] **Step 2: Link (both packages are unfolded, §5.2).**

```bash
cd ~/repos/dotfiles
stow -n -v bin systemd          # dry run: expect LINK crash-diagnose and LINK crash-watch.service, nothing else
stow -R bin systemd
readlink ~/.local/bin/crash-diagnose ~/.config/systemd/user/crash-watch.service   # both into ~/repos/dotfiles
```
Stow exits 0 even when it links to the wrong place, so judge by `readlink`, not by the exit code (§9.5).

- [ ] **Step 3: Enable.**

```bash
systemctl --user daemon-reload && systemctl --user enable --now crash-watch.service
systemctl --user is-active crash-watch.service      # active
sh tests/check_consumers.sh                         # crash-watch.service is active → ok; PASS
```

- [ ] **Step 4: Manual smoke** (spec §7):
  1. `sleep 60 & kill -SEGV $!`, a harmless crash of your own process. A toast "Crash: sleep (SIGSEGV)"
     appears, with the body "pid … · 1st since …".
  2. Click it. A low toast "Preparing crash report for sleep…" appears, then a herdr tab
     `crash: sleep` opens and focuses, with Claude reading `report.md`. The first gdb run may take
     about 20 s while debuginfod fetches coreutils' debug info.
  3. Within 30 min, run `sleep 60 & kill -SEGV $!` again. The toast is replaced and reads "2nd since …".
  4. Super+Space → `Dev › Diagnose a crash…` → pick the newest `sleep` line. Same result as step 2.
  5. `grep -c COREDUMP_ENVIRON ~/.local/state/crash-reports/*/report.md`: every count is 0.
  6. Optional, the kitty fallback: with herdr not running (do not stop it to test this), a click
     opens a kitty window in the report directory instead.
Ledger each result. Close the smoke tabs by hand.

---

## Spec coverage

| Spec | Delivered by |
|---|---|
| §1 terms (crash, report, coalescing) | Task 2 (`own`, report path), Task 3 (coalescing) |
| §2 X1 notify + palette, never unprompted | Task 3 (toast, click), Task 5 (row) |
| §2 X2 report by script, Claude under normal permissions | Task 2 (`build_report`, `launch`, PROMPT) |
| §2 X3 one tool, service, 30 min, gdb ≤ 90 s, herdr → kitty, keep 20 | Tasks 2, 3, 4 |
| §3 watch / list / diagnose flow, PROMPT | Tasks 2, 3 |
| §4 components (tool, unit, menu.toml, crash_test, check_consumers, docs) | Tasks 2-6 |
| §5 error handling (each row) | Task 2 (symbols/timeout, core gone, herdr/kitty, claude missing), Task 3 (journalctl exits → 1), Task 4 (Restart, consumers), Task 3 (dismissed), per-process diagnose |
| §6 probes | Planning (ledger P1, P2), Task 1 (re-check, P3 with Xinye) |
| §6 D1 uid filter | Task 3 `WatchUidTest` |
| §6 D2 coalescing | Task 3 `CoalesceTest` |
| §6 D3 click spawns diagnose | Task 3 `ClickTest` |
| §6 D4 report sections, no environ, missing lines | Task 2 `ReportTest` |
| §6 D5 herdr call shape, kitty fallback | Task 2 `LaunchTest` |
| §6 D6 prompt text | Task 2 `PromptTest` |
| §6 D7 list format, diagnose takes a list line | Task 2 `ListTest` |
| §6 D8 retention 20 | Task 2 `RetentionTest` |
| §6 mutations (uid → D1, window → D2, environ → D4) | Task 6 Step 6 |
| §7 rollout (`stow -R`, daemon-reload, enable) and smoke | Task 7 |
| §8 caveats | Task 6 Step 3 (§9.33 item 3) |
