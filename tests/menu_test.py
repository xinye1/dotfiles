"""Tests for sway/.config/sway/scripts/menu.py, the Super+Space palette (stdlib unittest).

Design: docs/specs/2026-10-08-command-palette-design.md. Everything menu.py
starts -- fuzzel, notify-send, kitty -- is a logging stub on PATH, and HOME and
XDG_RUNTIME_DIR are throwaway, so nothing here reaches the desktop. fuzzel's
answers are scripted: each invocation pops one line from STUB_REPLIES, and an
empty line is Esc (no output, exit 1).

MENU_BIN points the suite at another copy of menu.py, so the assertions can be
shown to go red against a broken one (the mutation check in the plan).
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MENU = Path(os.environ.get("MENU_BIN", REPO / "sway/.config/sway/scripts/menu.py"))
ACTION_PATH_TAIL = ":/usr/local/sbin:/usr/local/bin:/usr/bin"

STUB = r'''#!/usr/bin/env python3
# A logging stand-in for fuzzel, notify-send, kitty, cliphist and wl-copy.
import json, os, sys
name = os.path.basename(sys.argv[0])
args = sys.argv[1:]
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
        for name in ("fuzzel", "notify-send", "kitty", "cliphist", "wl-copy"):
            script(self.bin / name, STUB)
        self.toml = self.root / "menu.toml"
        self.log = self.root / "log.jsonl"
        self.replies = self.root / "replies"

    def env(self, **overrides):
        env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin",
               "XDG_RUNTIME_DIR": str(self.run), "XDG_CACHE_HOME": str(self.home / ".cache"),
               "MENU_TOML": str(self.toml), "STUB_LOG": str(self.log),
               "STUB_REPLIES": str(self.replies)}
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
        return self.run / "fuzzel-menu" / "applications"

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
        self.assertEqual(call["env"]["XDG_DATA_DIRS"], f"{root}:/a/share:/b/share")
        self.assertEqual(call["argv"], ["--cache", str(self.sb.home / ".cache/fuzzel-menu"),
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
