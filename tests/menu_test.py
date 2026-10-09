"""Tests for sway/.config/sway/scripts/menu.py, the Super+Space palette (stdlib unittest).

Design: docs/specs/2026-10-08-command-palette-design.md. Everything menu.py
starts -- fuzzel, notify-send, kitty -- is a logging stub on PATH, and HOME and
XDG_RUNTIME_DIR are throwaway, so nothing here reaches the desktop. fuzzel's
answers are scripted: each invocation pops one line from STUB_REPLIES, and an
empty line is Esc (no output, exit 1).

MENU_BIN points the suite at another copy of menu.py, so the assertions can be
shown to go red against a broken one (the mutation check in the plan).
"""
import fcntl
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MENU = Path(os.environ.get("MENU_BIN", REPO / "sway/.config/sway/scripts/menu.py"))
ACTION_PATH_TAIL = ":/usr/local/sbin:/usr/local/bin:/usr/bin"

STUB = r'''#!/usr/bin/env python3
# A logging stand-in for fuzzel, notify-send, kitty, cliphist and wl-copy.
import fcntl, json, os, sys
name = os.path.basename(sys.argv[0])
args = sys.argv[1:]
if name == "fuzzel" and os.environ.get("XDG_RUNTIME_DIR"):
    # Like fuzzel 1.15 (main.c): one instance per display, by flock; a second
    # one exits 1 at once, printing nothing on stdout.
    lock = os.path.join(os.environ["XDG_RUNTIME_DIR"],
                        "fuzzel-%s.lock" % os.environ.get("WAYLAND_DISPLAY", ""))
    held = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.stderr.write(lock + ": failed to acquire lock: fuzzel already running?\n")
        sys.exit(1)
if name == "slurp":
    sys.stderr.write("selection cancelled\n")
    sys.exit(1)
if name == "swaymsg":
    print("{}")
reads = ((name == "fuzzel" and ("--dmenu" in args or "-d" in args))
         or name == "wl-copy" or (name == "cliphist" and args[:1] == ["decode"]))
data = sys.stdin.buffer.read() if reads else b""
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps({"name": name, "argv": args,
                          "stdin": data.decode("utf-8", "replace"),
                          "env": {k: os.environ.get(k) for k in ("XDG_DATA_DIRS", "PATH")}}) + "\n")
if name == "fuzzel":
    path = os.environ["STUB_REPLIES"]
    with open(path) as f:
        replies = f.read().split("\n")
    with open(path, "w") as f:
        f.write("\n".join(replies[1:]))
    if replies[0]:
        print(replies[0])
    sys.exit(0 if replies[0] else 1)
if name == "cliphist" and args[:1] == ["list"]:
    print("7\thello world")
if name == "cliphist" and args[:1] == ["decode"]:
    sys.stdout.buffer.write(data.split(b"\t", 1)[-1])
'''

VALID = """
[[action]]
group = "System"
label = "Lock"
icon = "system-lock-screen"
run = "true"
"""


def script(path, body):
    path.write_text(body)
    path.chmod(0o755)
    return path


class Sandbox:
    def __init__(self, test):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        self.bin = self.root / "bin"
        self.run = self.root / "run"
        for d in (self.home / ".local/bin", self.bin, self.run):
            d.mkdir(parents=True)
        for name in ("fuzzel", "notify-send", "kitty", "cliphist", "wl-copy", "slurp",
                     "swaymsg", "grim"):
            script(self.bin / name, STUB)
        self.toml = self.root / "menu.toml"
        self.log = self.root / "log.jsonl"
        self.replies = self.root / "replies"

    def env(self, **overrides):
        env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin",
               "XDG_RUNTIME_DIR": str(self.run), "XDG_CACHE_HOME": str(self.home / ".cache"),
               "MENU_TOML": str(self.toml), "STUB_LOG": str(self.log),
               "STUB_REPLIES": str(self.replies), "WAYLAND_DISPLAY": "wayland-test"}
        env.update(overrides)
        return {k: v for k, v in env.items() if v is not None}

    def menu(self, *args, toml=None, replies=(), script=MENU, **overrides):
        if toml is not None:
            self.toml.write_text(textwrap.dedent(toml))
        self.replies.write_text("\n".join(replies))
        self.log.write_text("")
        return subprocess.run([sys.executable, str(script), *args], env=self.env(**overrides),
                              capture_output=True, text=True, timeout=30)

    def calls(self, name=None):
        rows = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [r for r in rows if name is None or r["name"] == name]

    def appdir(self):
        """The action directory the last palette handed fuzzel (each palette
        has its own, named for its pid)."""
        calls = self.calls("fuzzel")
        dirs = calls[-1]["env"]["XDG_DATA_DIRS"] if calls else None
        if not dirs or not dirs.startswith(str(self.run / "fuzzel-menu")):
            return self.run / "no-palette-dir"
        return Path(dirs.split(":")[0]) / "applications"

    def entries(self):
        d = self.appdir()
        return {p.name: p.read_text() for p in sorted(d.glob("*.desktop"))} if d.exists() else {}


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(self)

    def test_valid_file_passes(self):
        r = self.sb.menu("--check", toml=VALID)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_schema_errors_are_rejected_with_the_reason(self):
        a = '[[action]]\ngroup = "A"\nlabel = "B"\n'
        cases = {
            "syntax": ("[[action]\n", str(self.sb.toml)),
            "unknown key": (VALID + "confrim = true\n", "unknown key 'confrim'"),
            "top-level key": ('title = "x"\n' + VALID, "unknown top-level key 'title'"),
            "missing run": (a, "missing 'run'"),
            "wrong type": (VALID + 'confirm = "yes"\n', "'confirm' must be bool"),
            "keywords": (VALID + "keywords = [1]\n", "'keywords' must be a list of strings"),
            "duplicate id": (VALID + VALID, "duplicate id 'system-lock'"),
            "choice, no choices": (a + 'run = "x {choice}"\n', "go together"),
            "choices, no choice": (a + 'run = "x"\nchoices = "true"\n', "go together"),
            "bad id": (VALID + 'id = "Has Caps"\n', "must be [a-z0-9-]+"),
            "tab in label": ('[[action]]\ngroup = "A"\nlabel = "a\\tb"\nrun = "true"\n',
                             "tab or newline"),
        }
        for name, (toml, reason) in cases.items():
            with self.subTest(name):
                r = self.sb.menu("--check", toml=toml)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn(reason, r.stderr)

    def test_check_resolves_against_the_action_path_not_its_own(self):
        # T9: ~/.local/bin is in the action PATH though not on this test's PATH;
        # the test's own bin dir is on its PATH but in none of the action PATH's dirs.
        script(self.sb.home / ".local/bin/homecmd", "#!/bin/sh\nexit 0\n")
        script(self.sb.bin / "shellcmd", "#!/bin/sh\nexit 0\n")
        ok = self.sb.menu("--check", toml=VALID.replace('"true"', '"homecmd --flag"'))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        bad = self.sb.menu("--check", toml=VALID.replace('"true"', '"shellcmd"'))
        self.assertEqual(bad.returncode, 1)
        self.assertIn("run: 'shellcmd' not found in the action PATH", bad.stderr)

    def test_check_covers_when_choices_and_paths(self):
        toml = ('[[action]]\ngroup = "A"\nlabel = "B"\nrun = "true {choice}"\n'
                'choices = "nosuchlister"\nwhen = "~/.local/bin/nosuchtest"\n')
        r = self.sb.menu("--check", toml=toml)
        self.assertEqual(r.returncode, 1)
        self.assertIn("choices: 'nosuchlister' not found", r.stderr)
        self.assertIn("when: '~/.local/bin/nosuchtest' not found", r.stderr)


class CliphistPickTest(unittest.TestCase):
    SCRIPT = REPO / "sway/.config/sway/scripts/cliphist_pick.sh"

    def pick(self, reply):
        sb = Sandbox(self)
        sb.replies.write_text(reply)
        sb.log.write_text("")
        r = subprocess.run([str(self.SCRIPT)], env=sb.env(), capture_output=True, text=True,
                           timeout=10)
        return r, sb

    def test_esc_exits_0_and_copies_nothing(self):
        r, sb = self.pick("")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sb.calls("wl-copy"), [])

    def test_a_pick_is_decoded_into_the_clipboard(self):
        r, sb = self.pick("7\thello world")
        self.assertEqual(r.returncode, 0, r.stderr)
        [decode] = [c for c in sb.calls("cliphist") if c["argv"] == ["decode"]]
        self.assertEqual(decode["stdin"], "7\thello world\n")
        self.assertEqual(len(sb.calls("wl-copy")), 1)


TWO = VALID + """
[[action]]
group = "Capture"
label = "Region → clipboard"
icon = "camera-photo"
keywords = ["screenshot", "grab"]
run = "true"
"""


def validate(test, path):
    tool = shutil.which("desktop-file-validate")
    test.assertIsNotNone(tool, "desktop-file-validate missing: install desktop-file-utils")
    r = subprocess.run([tool, str(path)], capture_output=True, text=True)
    test.assertEqual(r.returncode, 0, r.stdout + r.stderr)


def exec_argv(entry):
    line = next(l for l in entry.splitlines() if l.startswith("Exec="))
    return shlex.split(line[len("Exec="):])


class PaletteTest(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(self)

    def test_one_valid_desktop_file_per_action(self):  # T1
        self.sb.menu(toml=TWO)
        entries = self.sb.entries()
        self.assertEqual(set(entries), {"menu-system-lock.desktop",
                                        "menu-capture-region-clipboard.desktop"})
        text = entries["menu-capture-region-clipboard.desktop"]
        for line in ("Type=Application", "Name=Capture › Region → clipboard",
                     "Icon=camera-photo", "Keywords=screenshot;grab;"):
            self.assertIn(line + "\n", text)
        self.assertEqual(exec_argv(text), [str(MENU), "--run", "capture-region-clipboard"])
        for name in entries:
            validate(self, self.sb.appdir() / name)

    def test_rows_that_disappear_are_removed(self):  # T1
        self.sb.menu(toml=TWO)
        self.sb.menu(toml=VALID)
        self.assertEqual(set(self.sb.entries()), {"menu-system-lock.desktop"})

    def test_an_explicit_id_names_the_file(self):
        self.sb.menu(toml=VALID + 'id = "lock"\n')
        self.assertEqual(set(self.sb.entries()), {"menu-lock.desktop"})

    def test_fuzzel_gets_the_actions_and_apps_get_the_original_dirs(self):  # T2
        self.sb.menu(toml=VALID, XDG_DATA_DIRS="/a/share:/b/share")
        [call] = self.sb.calls("fuzzel")
        root = self.sb.run / "fuzzel-menu"
        self.assertRegex(call["env"]["XDG_DATA_DIRS"], rf"^{re.escape(str(root))}/\d+:/a/share:/b/share$")
        self.assertEqual(call["argv"], ["--cache", str(self.sb.home / ".cache/fuzzel-menu"),
                                        "--fields", "filename,name,generic,keywords",
                                        "--launch-prefix", "env XDG_DATA_DIRS=/a/share:/b/share"])

    def test_unset_data_dirs_restore_to_the_spec_default(self):  # T2
        self.sb.menu(toml=VALID, XDG_DATA_DIRS=None)
        [call] = self.sb.calls("fuzzel")
        self.assertEqual(call["argv"][-1], "env XDG_DATA_DIRS=/usr/local/share:/usr/share")
        self.assertTrue(call["env"]["XDG_DATA_DIRS"].endswith(":/usr/local/share:/usr/share"))

    def test_when_hides_only_on_a_clean_no(self):  # T3
        tests = {"yes": "true", "no": "false", "slow": "sleep 3", "missing": "nosuchcommand",
                 "chatty": "echo noise; echo more >&2; true"}
        toml = "".join(f'[[action]]\ngroup = "W"\nlabel = "{k}"\nrun = "true"\nwhen = "{v}"\n\n'
                       for k, v in tests.items())
        self.sb.menu(toml=toml)
        self.assertEqual(set(self.sb.entries()),
                         {f"menu-w-{k}.desktop" for k in ("yes", "slow", "missing", "chatty")})

    def test_a_broken_menu_toml_still_opens_plain_fuzzel(self):  # T8
        self.sb.menu(toml="[[action]\n")
        [call] = self.sb.calls("fuzzel")
        self.assertEqual(call["argv"], [])
        self.assertIsNone(call["env"]["XDG_DATA_DIRS"])
        [note] = self.sb.calls("notify-send")
        self.assertEqual(note["argv"][:4], ["-u", "critical", "-a", "menu"])
        self.assertIn("plain launcher", note["argv"][4])

    def test_no_runtime_dir_still_opens_plain_fuzzel(self):  # Review Focus 3
        self.sb.menu(toml=VALID, XDG_RUNTIME_DIR=None)
        [call] = self.sb.calls("fuzzel")
        self.assertEqual(call["argv"], [])
        self.assertEqual(len(self.sb.calls("notify-send")), 1)
        self.assertEqual(self.sb.entries(), {})

    def test_a_fuzzel_that_cannot_be_executed_notifies(self):  # CodeRabbit, PR #44
        # Found on PATH and executable, but not a program: os.execve raises
        # ENOEXEC. That used to escape as a traceback sway throws away.
        (self.sb.bin / "fuzzel").write_bytes(b"\x00\x01 not a program")
        r = self.sb.menu(toml=VALID)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)
        [note] = self.sb.calls("notify-send")
        self.assertEqual(note["argv"][4], "Menu: cannot start fuzzel")

    def test_desktop_metacharacters_survive(self):  # Review Focus 1
        toml = r"""
[[action]]
group = "Odd"
label = '50% off \ back'
keywords = ["semi;colon"]
run = "true"
"""
        self.sb.menu(toml=toml)
        [(name, text)] = self.sb.entries().items()
        self.assertIn("Name=Odd › 50% off \\\\ back\n", text)
        self.assertIn("Keywords=semi\\;colon;\n", text)
        validate(self, self.sb.appdir() / name)

    def test_a_script_path_with_a_space_is_quoted_in_exec(self):  # Review Focus 2
        spaced = self.sb.root / "my scripts" / "menu.py"
        spaced.parent.mkdir()
        shutil.copy(MENU, spaced)
        self.sb.menu(toml=VALID, script=spaced)
        text = self.sb.entries()["menu-system-lock.desktop"]
        self.assertEqual(exec_argv(text), [str(spaced), "--run", "system-lock"])
        validate(self, self.sb.appdir() / "menu-system-lock.desktop")


REBOOT = """
[[action]]
group = "System"
label = "Reboot"
icon = "system-reboot"
run = 'echo rebooted >> "$HOME/out"'
confirm = true
"""

THEME = """
[[action]]
group = "Style"
label = "Theme…"
choices = "lister"
run = 'printf "%s\\n" {choice} >> "$HOME/out"'
"""


class RunTest(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(self)

    def out(self):
        path = self.sb.home / "out"
        return path.read_text() if path.exists() else ""

    def lister(self, body):
        script(self.sb.home / ".local/bin/lister", "#!/bin/sh\n" + body)

    def test_confirm_yes_runs_no_and_esc_do_not(self):  # T5
        for reply, expected in (("Yes", "rebooted\n"), ("No", ""), ("", "")):
            with self.subTest(reply=reply or "Esc"):
                (self.sb.home / "out").unlink(missing_ok=True)
                r = self.sb.menu("--run", "system-reboot", toml=REBOOT, replies=[reply])
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(self.out(), expected)
                [pick] = self.sb.calls("fuzzel")
                self.assertIn("--dmenu", pick["argv"])
                self.assertEqual(pick["stdin"], "No\nYes\n")
                self.assertEqual(self.sb.calls("notify-send"), [])

    def test_choices_pick_is_one_quoted_word(self):  # T6, Review Focus 5
        self.lister("printf '%s\\n' nord '' gruvbox 'x; touch \"$HOME/pwned\"'\n")
        hostile = 'x; touch "$HOME/pwned"'
        r = self.sb.menu("--run", "style-theme", toml=THEME, replies=[hostile])
        self.assertEqual(r.returncode, 0, r.stderr)
        [pick] = self.sb.calls("fuzzel")
        self.assertEqual(pick["stdin"], f"nord\ngruvbox\n{hostile}\n")  # blank line dropped
        self.assertEqual(self.out(), hostile + "\n")
        self.assertFalse((self.sb.home / "pwned").exists())

    def test_choices_that_fail_or_are_empty_notify_and_run_nothing(self):  # T6
        for body in ("exit 0\n", "echo oops >&2; exit 4\n"):
            with self.subTest(body=body):
                self.lister(body)
                r = self.sb.menu("--run", "style-theme", toml=THEME)
                self.assertEqual(r.returncode, 1)
                self.assertEqual(self.sb.calls("fuzzel"), [])
                self.assertEqual(len(self.sb.calls("notify-send")), 1)
                self.assertEqual(self.out(), "")

    def test_esc_at_choices_runs_nothing(self):  # T6
        self.lister("echo nord\n")
        r = self.sb.menu("--run", "style-theme", toml=THEME, replies=[""])
        self.assertEqual((r.returncode, self.out(), self.sb.calls("notify-send")), (0, "", []))

    def test_a_failing_action_raises_one_critical_notification(self):  # T7
        toml = VALID.replace('"true"', """'for i in 1 2 3 4 5 6 7; do echo "line $i" >&2; done; exit 3'""")
        r = self.sb.menu("--run", "system-lock", toml=toml)
        self.assertEqual(r.returncode, 3)
        [note] = self.sb.calls("notify-send")
        self.assertEqual(note["argv"], ["-u", "critical", "-a", "menu", 'Menu: "Lock" failed (3)',
                                        "line 3\nline 4\nline 5\nline 6\nline 7"])

    def test_a_succeeding_action_is_silent(self):  # T7
        r = self.sb.menu("--run", "system-lock", toml=VALID)
        self.assertEqual((r.returncode, self.sb.calls("notify-send")), (0, []))

    def test_non_utf8_stderr_still_notifies(self):  # Review Focus 4
        toml = VALID.replace('"true"', """'printf "\\\\377\\\\376 bad\\\\n" >&2; exit 1'""")
        r = self.sb.menu("--run", "system-lock", toml=toml)
        self.assertEqual(r.returncode, 1)
        [note] = self.sb.calls("notify-send")
        self.assertIn("bad", note["argv"][5])

    def test_terminal_actions_go_to_a_floating_kitty_and_never_notify(self):  # T7
        r = self.sb.menu("--run", "system-lock", toml=VALID.replace('"true"', '"false"\nterminal = true'))
        self.assertEqual(r.returncode, 0, r.stderr)
        [kitty] = self.sb.calls("kitty")
        self.assertEqual(kitty["argv"][:4], ["--class", "menu-term", "bash", "-c"])
        self.assertTrue(kitty["argv"][4].startswith("false\n"))
        self.assertIn("read -rsn1", kitty["argv"][4])
        self.assertEqual(kitty["env"]["PATH"], f"{self.sb.home}/.local/bin{ACTION_PATH_TAIL}")
        self.assertEqual(self.sb.calls("notify-send"), [])

    def test_actions_run_with_the_action_path(self):  # T9, runtime half
        script(self.sb.home / ".local/bin/homecmd", '#!/bin/sh\necho home >> "$HOME/out"\n')
        script(self.sb.bin / "shellcmd", "#!/bin/sh\nexit 0\n")
        ok = self.sb.menu("--run", "system-lock", toml=VALID.replace('"true"', '"homecmd"'))
        self.assertEqual((ok.returncode, self.out()), (0, "home\n"))
        bad = self.sb.menu("--run", "system-lock", toml=VALID.replace('"true"', '"shellcmd"'))
        self.assertEqual(bad.returncode, 127)
        [note] = self.sb.calls("notify-send")
        self.assertEqual(note["argv"][4], 'Menu: "Lock" failed (127)')

    def test_an_unknown_id_notifies(self):
        r = self.sb.menu("--run", "nope", toml=VALID)
        self.assertEqual(r.returncode, 1)
        [note] = self.sb.calls("notify-send")
        self.assertIn("nope", note["argv"][4])


class GroupTest(unittest.TestCase):
    TOML = VALID + REBOOT + '\n[[action]]\ngroup = "Capture"\nlabel = "Region"\nrun = "true"\n'

    def setUp(self):
        self.sb = Sandbox(self)

    def test_group_lists_only_its_rows_in_file_order_with_icons(self):  # T4
        r = self.sb.menu("--group", "System", toml=self.TOML, replies=[""])
        self.assertEqual(r.returncode, 0, r.stderr)
        [pick] = self.sb.calls("fuzzel")
        self.assertEqual(pick["stdin"], "system-lock\tLock\0icon\x1fsystem-lock-screen\n"
                                        "system-reboot\tReboot\0icon\x1fsystem-reboot\n")
        for flag in ("--dmenu", "--with-nth=2", "--accept-nth=1"):
            self.assertIn(flag, pick["argv"])
        self.assertNotIn("--cache", pick["argv"])
        self.assertEqual(self.sb.calls("notify-send"), [])

    def test_the_picked_id_runs_through_confirm(self):  # T4
        r = self.sb.menu("--group", "System", toml=self.TOML, replies=["system-reboot", "Yes"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.sb.home / "out").read_text(), "rebooted\n")
        self.assertEqual(self.sb.calls("fuzzel")[1]["stdin"], "No\nYes\n")

    def test_an_unknown_group_notifies(self):  # T4
        r = self.sb.menu("--group", "Nope", toml=self.TOML)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(self.sb.calls("notify-send")), 1)


class PaletteDirTest(unittest.TestCase):
    """Each palette writes its own fuzzel-menu/<pid> directory: menu.py execs
    fuzzel, so the pid is the running fuzzel's. A second Super+Space used to
    rmtree the one shared directory while the first fuzzel could still be
    reading it (final review, deferred minor #4)."""

    def setUp(self):
        self.sb = Sandbox(self)
        self.root = self.sb.run / "fuzzel-menu"

    def first_dir(self):
        return self.sb.calls("fuzzel")[-1]["env"]["XDG_DATA_DIRS"].split(":")[0]

    def test_palettes_never_share_a_directory(self):
        self.sb.menu(toml=VALID)
        first = self.first_dir()
        self.sb.menu(toml=VALID)
        self.assertNotEqual(self.first_dir(), first)

    def test_a_live_palettes_directory_is_left_alone(self):
        live = self.root / str(os.getpid()) / "applications"  # this test process: alive
        live.mkdir(parents=True)
        (live / "menu-x.desktop").write_text("kept\n")
        self.sb.menu(toml=VALID)
        self.assertEqual((live / "menu-x.desktop").read_text(), "kept\n")

    def test_dead_palettes_directories_are_pruned(self):
        gone = subprocess.Popen(["true"])
        gone.wait()
        dead = self.root / str(gone.pid) / "applications"
        dead.mkdir(parents=True)
        legacy = self.root / "applications"  # the pre-fix shared layout
        legacy.mkdir()
        self.sb.menu(toml=VALID)
        self.assertFalse(dead.parent.exists())
        self.assertFalse(legacy.exists())


class FuzzelLockTest(unittest.TestCase):
    """fuzzel holds a per-display instance lock until it has finished tearing
    down, and the palette starts `menu.py --run` before then. A second-step
    fuzzel started in that window exits 1 with empty stdout -- which read as
    Esc, so Shutdown -> Enter could quietly do nothing (final review #1)."""

    def setUp(self):
        self.sb = Sandbox(self)
        self.lockfile = self.sb.run / "fuzzel-wayland-test.lock"

    def hold(self, seconds=None):
        fd = os.open(self.lockfile, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        if seconds is None:
            self.addCleanup(os.close, fd)
        else:
            timer = threading.Timer(seconds, os.close, (fd,))
            timer.start()
            self.addCleanup(timer.join)

    def test_run_waits_for_the_palette_to_let_go(self):
        self.hold(0.5)
        r = self.sb.menu("--run", "system-reboot", toml=REBOOT, replies=["Yes"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.sb.home / "out").read_text(), "rebooted\n")

    def test_group_waits_too(self):
        self.hold(0.5)
        r = self.sb.menu("--group", "System", toml=REBOOT, replies=["system-reboot", "Yes"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.sb.home / "out").read_text(), "rebooted\n")

    def test_a_fuzzel_that_never_lets_go_is_reported_not_swallowed(self):
        self.hold()
        r = self.sb.menu("--run", "system-reboot", toml=REBOOT, replies=["Yes"])
        self.assertEqual(r.returncode, 1)
        [note] = self.sb.calls("notify-send")
        self.assertIn("fuzzel", note["argv"][4])
        self.assertFalse((self.sb.home / "out").exists())


class RepoMenuTest(unittest.TestCase):
    def test_every_command_in_the_repo_menu_resolves(self):
        # T10, the rot guard. The deployed layout is built from the repo rather
        # than read from the live ~, so this judges the repo, not what is stowed.
        sb = Sandbox(self)
        (sb.home / ".local/bin").rmdir()
        (sb.home / ".local/bin").symlink_to(REPO / "bin/.local/bin")
        (sb.home / ".config").mkdir()
        for pkg in ("sway", "waybar"):
            (sb.home / ".config" / pkg).symlink_to(REPO / pkg / ".config" / pkg)
        r = sb.menu("--check", MENU_TOML=str(REPO / "sway/.config/sway/menu.toml"))
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
