# Command Palette (Super+Space) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One fuzzel window on Super+Space that searches apps and desktop actions together, with
every action defined in `menu.toml` and every failure made visible.

**Architecture:** `menu.py` reads `menu.toml`, writes each visible action as a `.desktop` file into
`$XDG_RUNTIME_DIR/fuzzel-menu/applications`, and `exec`s fuzzel's ordinary launcher with that
directory prepended to `XDG_DATA_DIRS`, so fuzzel launches apps and ranks everything. Picking an
action runs `menu.py --run <id>`, which does the second step (confirm or choices), runs the
command with a fixed action PATH, and raises a critical notification on a non-zero exit.
`menu.py --group System` is a plain dmenu list for the power picker.

**Tech Stack:** Python 3.14 stdlib (`tomllib`, `subprocess`, `unittest`), fuzzel 1.15, sway,
waybar, mako (`notify-send`), kitty, `desktop-file-validate` (test only).

**Spec:** `docs/specs/2026-10-08-command-palette-design.md` (read it first; this plan argues from
it). Repo rules: `CLAUDE.md`, `PLAYBOOK.md`.

## Global Constraints

- Python stdlib only; no new runtime packages. `desktop-file-utils` is added to `packages.txt` for the test.
- fuzzel 1.15 flags used: `--cache`, `--launch-prefix`, `--dmenu`, `--prompt`, `--lines`, `--with-nth=2`, `--accept-nth=1`.
- Action PATH is the constant `$HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/bin`, used by `run`/`when`/`choices` **and** `--check`. `menu.py`'s own tools (`fuzzel`, `notify-send`, `kitty`) are found on the inherited `PATH`.
- Runtime dir: `$XDG_RUNTIME_DIR/fuzzel-menu/applications/menu-<id>.desktop`. Cache: `${XDG_CACHE_HOME:-$HOME/.cache}/fuzzel-menu`. Unset `XDG_DATA_DIRS` means `/usr/local/share:/usr/share`.
- Notifications: `notify-send -u critical -a menu <summary> <body>`. Failure summary: `Menu: "<label>" failed (<code>)`; body is the last 5 stderr lines.
- `when`: 1 s timeout; exit 0 shows the row, other exits hide it, except 126/127 and timeouts, which show it.
- Icons are freedesktop names (all used ones verified present in Papirus-Dark), never Nerd Font glyphs. No literal hex anywhere (`check_hex.py`).
- Tests never touch the live desktop: stubs for fuzzel/notify-send/kitty/cliphist/wl-copy, throwaway `HOME`/`XDG_RUNTIME_DIR`, never `pkill -x waybar`.
- `$mod+d` stays plain fuzzel.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01K3ULXJat1nthjNCUBQVarU
  ```

## Review Focus

Inputs the spec implies but its T1–T10 don't exercise, most likely first. Each has a test in the
owning task.

1. **A label, group or keyword holding `%`, `\` or `;`** should land in the `.desktop` file
   escaped and still pass `desktop-file-validate` (Task 2, `test_desktop_metacharacters_survive`).
2. **`menu.py` at a path with a space** should still have a correctly quoted `Exec=` line
   (Task 2, `test_a_script_path_with_a_space_is_quoted_in_exec`).
3. **`XDG_RUNTIME_DIR` unset** (a stripped environment) should notify and open plain fuzzel, not
   write anywhere else (Task 2, `test_no_runtime_dir_still_opens_plain_fuzzel`).
4. **A failing action with non-UTF-8 stderr** should still notify, with replacement characters
   (Task 3, `test_non_utf8_stderr_still_notifies`).
5. **A `choices` line containing shell metacharacters** should reach `{choice}` as one quoted
   word and execute nothing (Task 3, `test_choices_pick_is_one_quoted_word`).

---

## File Structure

| Path | Task | Responsibility |
|---|---|---|
| `sway/.config/sway/scripts/menu.py` | 1–3 | The engine: load/validate, `--check`, palette, `--run`, `--group` |
| `sway/.config/sway/menu.toml` | 1 | The 24 actions (spec §4.3) |
| `sway/.config/sway/scripts/cliphist_pick.sh` | 1 | Clipboard history pick, shared by `$mod+Ctrl+v` and the palette; Esc exits 0 |
| `tests/menu_test.py` | 1–3 | Sandboxed suite (stub harness + T1–T10 + Review Focus) |
| `tests/theme_test.sh` | 1 | Runs `menu_test.py` |
| `sway/.config/sway/config.d/default` | 4 | `$palette`, `$powermenu`, `$mod+space`, `$mod+Alt+space`, `$mod+Ctrl+v` |
| `sway/.config/sway/config.d/application_defaults` | 4 | `menu-term` floating rule |
| `waybar/.config/waybar/config` | 4 | Launcher and power on-clicks |
| `sway/.config/sway/scripts/power_menu.sh` | 4 | Deleted |
| `PLAYBOOK.md` | 4, 5 | §4.3 and §9.4 references (Task 4); §7 paragraph (Task 5) |
| `tests/check_consumers.sh`, `CLAUDE.md`, `packages.txt` | 5 | Live check, Verify docs, test dependency |

`sway` is a folded stow package, so new files under it are live in `~/.config/sway` immediately;
no `stow` command is needed anywhere in this plan.

---

### Task 0: Branch and commit the spec and plan

**Files:** `docs/specs/2026-10-08-command-palette-design.md`, `docs/plans/2026-10-08-command-palette.md` (both already written)

- [ ] **Step 1: Create the branch from an up-to-date main**

```bash
cd ~/repos/dotfiles
git switch main && git pull --ff-only
git switch -c feat/command-palette
```

- [ ] **Step 2: Commit**

```bash
git add docs/specs/2026-10-08-command-palette-design.md docs/plans/2026-10-08-command-palette.md
git commit -m "docs(specs): command palette design and plan

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K3ULXJat1nthjNCUBQVarU"
```

---

### Task 1: Load, validate and `--check`, plus the real `menu.toml` and `cliphist_pick.sh`

**Files:**
- Create: `sway/.config/sway/scripts/menu.py` (executable)
- Create: `sway/.config/sway/menu.toml`
- Create: `sway/.config/sway/scripts/cliphist_pick.sh` (executable). It is here, not with `--run`,
  because `menu.toml` names it and the rot guard (T10) must be green from this task on
- Create: `tests/menu_test.py`
- Modify: `tests/theme_test.sh` (after the `keyhint_test.py` line, ~line 220)

**Interfaces:**
- Produces (used by Tasks 2–3): `SCRIPT: Path`, `ConfigError(Exception)`, `config_path() -> Path`
  (env `MENU_TOML` overrides; default `SCRIPT.parent.parent / "menu.toml"`), `slug(text) -> str`,
  `load(path) -> list[dict]` (each dict has `group`, `label`, `run`, `id`, `icon`, plus any
  optional keys present), `action_env(env: dict) -> dict`, `resolve(word, env) -> str | None`,
  `check(actions, env) -> list[str]`, `main(argv) -> int`.
- Test harness (used by Tasks 2–3): `Sandbox(test)` with `.root .home .bin .run .toml .log
  .replies`, `.env(**overrides)`, `.menu(*args, toml=None, replies=(), script=MENU, **overrides)
  -> CompletedProcess`, `.calls(name=None) -> list[dict]`, `.entries() -> dict[str, str]`,
  `.appdir() -> Path`; module constants `REPO`, `MENU`, `VALID`.

- [ ] **Step 1: Write the test harness and the failing Task 1 tests**

Create `tests/menu_test.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd ~/repos/dotfiles && python3 tests/menu_test.py`
Expected: every test FAILs or ERRORs (`menu.py` and `cliphist_pick.sh` do not exist).

- [ ] **Step 3: Write `menu.py` (load, validate, `--check`)**

Create `sway/.config/sway/scripts/menu.py`:

```python
#!/usr/bin/env python3
"""menu — the Super+Space palette: apps and desktop actions in one fuzzel.

Design: docs/specs/2026-10-08-command-palette-design.md. The actions live in
~/.config/sway/menu.toml. Each visible action is written as a .desktop file
into $XDG_RUNTIME_DIR/fuzzel-menu/applications and fuzzel runs in its ordinary
launcher mode with that directory prepended to XDG_DATA_DIRS -- so fuzzel, not
this script, finds and launches apps, draws icons and ranks by use. Picking an
action runs `menu.py --run <id>`.

  menu.py                 the palette
  menu.py --group <G>     group G's actions only, as a dmenu list ($mod+Shift+e)
  menu.py --run <id>      one action: choices, confirm, terminal, failure notification
  menu.py --check         validate menu.toml and resolve every command; exit 1 on a problem

A broken part must never make the key do nothing (spec §5): a menu.toml that
does not load still opens plain fuzzel, and a failing action raises a critical
notification instead of vanishing into sway's discarded stderr (PLAYBOOK §7).
"""
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

SCRIPT = Path(os.path.abspath(__file__))
REQUIRED = {"group": str, "label": str, "run": str}
OPTIONAL = {"icon": str, "id": str, "keywords": list, "confirm": bool,
            "choices": str, "when": str, "terminal": bool}
DEFAULT_ICON = "system-run"
# The desktop session's PATH has no ~/.local/bin (only .bashrc adds it), and a
# terminal's PATH has directories the session lacks. So actions get this fixed
# PATH, and --check resolves against it: a check run anywhere judges exactly
# what a keypress will see (spec §3.3).
SYSTEM_PATH = "/usr/local/sbin:/usr/local/bin:/usr/bin"


class ConfigError(Exception):
    pass


def config_path():
    override = os.environ.get("MENU_TOML")
    return Path(override) if override else SCRIPT.parent.parent / "menu.toml"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def load(path):
    """menu.toml's actions, validated. An unknown key is an error, never
    ignored: a typo in `confirm` must not turn a guarded reboot into an
    unguarded one."""
    try:
        data = tomllib.loads(path.read_text())
    except OSError as e:
        raise ConfigError(f"{path}: {e.strerror}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from e
    extra = sorted(set(data) - {"action"})
    if extra:
        raise ConfigError(f"{path}: unknown top-level key {extra[0]!r}")
    rows = data.get("action", [])
    if not isinstance(rows, list):
        raise ConfigError(f"{path}: actions must be [[action]] tables")
    actions, seen = [], set()
    for n, row in enumerate(rows, 1):
        where = f"{path}: action {n}"
        for key in row:
            if key not in REQUIRED and key not in OPTIONAL:
                raise ConfigError(f"{where}: unknown key {key!r}")
        for key, kind in {**REQUIRED, **OPTIONAL}.items():
            if key not in row:
                if key in REQUIRED:
                    raise ConfigError(f"{where}: missing {key!r}")
            elif not isinstance(row[key], kind):
                raise ConfigError(f"{where}: {key!r} must be {kind.__name__}")
        where = f"{path}: [{row['group']}] {row['label']}"
        if re.search(r"[\t\n\0]", row["group"] + row["label"]):
            raise ConfigError(f"{where}: group and label cannot hold a tab or newline")
        if not all(isinstance(k, str) for k in row.get("keywords", [])):
            raise ConfigError(f"{where}: 'keywords' must be a list of strings")
        if ("{choice}" in row["run"]) != ("choices" in row):
            raise ConfigError(f"{where}: '{{choice}}' in run and 'choices' go together")
        action = dict(row)
        action.setdefault("id", slug(f"{row['group']}-{row['label']}"))
        action.setdefault("icon", DEFAULT_ICON)
        if not re.fullmatch(r"[a-z0-9-]+", action["id"]):
            raise ConfigError(f"{where}: id {action['id']!r} must be [a-z0-9-]+")
        if action["id"] in seen:
            raise ConfigError(f"{where}: duplicate id {action['id']!r}")
        seen.add(action["id"])
        actions.append(action)
    return actions


def action_env(env):
    """The environment actions run with: env, with the fixed action PATH."""
    home = env.get("HOME") or str(Path.home())
    return dict(env, PATH=f"{home}/.local/bin:{SYSTEM_PATH}")


def resolve(word, env):
    """Where `word` would run from under the action PATH, or None."""
    word = os.path.expanduser(word)
    if "/" in word:
        return word if os.path.isfile(word) and os.access(word, os.X_OK) else None
    return shutil.which(word, path=action_env(env)["PATH"])


def check(actions, env):
    """One line per command whose first word does not resolve."""
    problems = []
    for a in actions:
        for field in ("run", "when", "choices"):
            if field not in a:
                continue
            try:
                words = shlex.split(a[field])
            except ValueError as e:
                problems.append(f"[{a['group']}] {a['label']}: {field}: {e}")
                continue
            if not words or resolve(words[0], env) is None:
                first = words[0] if words else "(empty)"
                problems.append(f"[{a['group']}] {a['label']}: {field}: "
                                f"{first!r} not found in the action PATH")
    return problems


def main(argv):
    env = dict(os.environ)
    if argv == ["--check"]:
        try:
            actions = load(config_path())
        except ConfigError as e:
            print(e, file=sys.stderr)
            return 1
        problems = check(actions, env)
        for problem in problems:
            print(f"menu.toml: {problem}", file=sys.stderr)
        return 1 if problems else 0
    print("usage: menu.py [--check | --run <id> | --group <name>]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Then: `chmod +x sway/.config/sway/scripts/menu.py`

- [ ] **Step 4: Write the real `menu.toml`**

Create `sway/.config/sway/menu.toml` (System rows first and in this order: it is the power
picker's fixed order):

```toml
# The command palette's actions: Super+Space (~/.config/sway/scripts/menu.py).
# Design: docs/specs/2026-10-08-command-palette-design.md.
#
# One [[action]] per row, shown as "<group> › <label>". Keys:
#   group, label, run  required. `run` is an `sh -c` command.
#   icon               freedesktop icon name (Papirus-Dark resolves it). Default system-run.
#                      Never a Nerd Font glyph.
#   id                 [a-z0-9-]+, default the slug of group-label. It keys the rank
#                      fuzzel keeps, so set it before renaming a label to keep that rank.
#   keywords           extra search words
#   confirm = true     a No/Yes step first
#   choices            a command whose output lines are offered; the pick fills {choice}
#   when               a shell test; the row shows only when it exits 0
#   terminal = true    run in a floating kitty that waits for a key
# An unknown key is an error, never ignored.
#
# Actions run with a FIXED PATH: ~/.local/bin, then /usr/local/sbin:/usr/local/bin:/usr/bin.
# The session's own PATH has no ~/.local/bin; this is what lets `theme` work from here.
# An action that opens its own picker must exit 0 when that picker is cancelled,
# or Esc raises a failure notification.
#
# `menu.py --check` (tests/menu_test.py, check_consumers.sh) fails when a command
# named here stops resolving.

# --- System (also $mod+Shift+e and waybar's power button, in this order) ---

[[action]]
group = "System"
label = "Lock"
icon = "system-lock-screen"
run = "~/.config/sway/scripts/lock.sh"

[[action]]
group = "System"
label = "Suspend"
icon = "system-suspend"
run = "systemctl suspend"
confirm = true
# Hidden when suspend is masked, as power_menu.sh did.
when = '[ "$(systemctl is-enabled suspend.target 2>/dev/null)" != masked ]'

[[action]]
group = "System"
label = "Log out"
icon = "system-log-out"
run = "swaymsg exit"
confirm = true

[[action]]
group = "System"
label = "Reboot"
icon = "system-reboot"
keywords = ["restart"]
run = "systemctl reboot"
confirm = true

[[action]]
group = "System"
label = "Reboot to UEFI"
icon = "system-reboot"
keywords = ["bios", "firmware"]
run = "systemctl reboot --firmware-setup"
confirm = true

[[action]]
group = "System"
label = "Shutdown"
icon = "system-shutdown"
keywords = ["power off"]
run = "systemctl poweroff"
confirm = true

# --- Capture ---

[[action]]
group = "Capture"
label = "Region → edit"
icon = "applets-screenshooter"
keywords = ["screenshot"]
run = "~/.config/sway/scripts/screenshot_region.sh"

[[action]]
group = "Capture"
label = "Region → clipboard"
icon = "applets-screenshooter"
keywords = ["screenshot"]
run = "~/.config/sway/scripts/screenshot_region.sh --clipboard"

[[action]]
group = "Capture"
label = "Window → edit"
icon = "applets-screenshooter"
keywords = ["screenshot"]
run = "~/.config/sway/scripts/screenshot_window.sh"

[[action]]
group = "Capture"
label = "Display → edit"
icon = "applets-screenshooter"
keywords = ["screenshot"]
run = "~/.config/sway/scripts/screenshot_display.sh"

# --- Clipboard ---

[[action]]
group = "Clipboard"
label = "History"
icon = "edit-paste"
keywords = ["paste", "cliphist"]
run = "~/.config/sway/scripts/cliphist_pick.sh"

[[action]]
group = "Clipboard"
label = "Delete an entry"
icon = "edit-delete"
keywords = ["cliphist"]
run = "~/.config/sway/scripts/cliphist_delete.sh"

# --- Notifications ---

[[action]]
group = "Notifications"
label = "Toggle Do Not Disturb"
icon = "notifications-disabled"
keywords = ["dnd"]
run = "makoctl mode -t do-not-disturb"

[[action]]
group = "Notifications"
label = "Restore last"
icon = "notifications"
run = "makoctl restore"

[[action]]
group = "Notifications"
label = "Dismiss all"
icon = "edit-clear-all"
run = "makoctl dismiss --all"

# --- Windows and keys ---

[[action]]
group = "Windows"
label = "Switch window"
icon = "view-restore"
run = "~/.config/sway/scripts/window_switcher.sh"

[[action]]
group = "Windows"
label = "Toggle gaps"
icon = "view-restore"
run = "swaymsg gaps inner current toggle 12"

[[action]]
group = "Keys"
label = "Show keybindings"
icon = "preferences-desktop-keyboard-shortcuts"
keywords = ["cheatsheet", "shortcuts"]
run = "~/.config/waybar/scripts/keyhint.py"

# --- Style ---

[[action]]
group = "Style"
label = "Theme…"
icon = "preferences-desktop-theme"
keywords = ["palette", "colours", "colors"]
choices = "theme --list"
run = "theme {choice}"

# --- Dev ---

[[action]]
group = "Dev"
label = "Claude: limits were reset early"
icon = "edit-undo"
confirm = true
# -x is load-bearing: without it the signal also kills waybar's supervisor (PLAYBOOK §9.29).
run = "~/.config/waybar/scripts/claude_usage.py --limits-reset && pkill -RTMIN+8 -x waybar"

[[action]]
group = "Dev"
label = "Backups: status"
icon = "drive-harddisk"
keywords = ["restic", "tp-backup"]
run = "tp-backup status"
terminal = true

[[action]]
group = "Dev"
label = "herdr: back up sessions now"
icon = "document-save"
run = "herdr-session-backup"

# --- Sway ---

[[action]]
group = "Sway"
label = "Reload config"
icon = "view-refresh"
run = "sway --validate -c ~/.config/sway/config && swaymsg reload"

[[action]]
group = "Sway"
label = "Displays: re-apply kanshi"
icon = "preferences-desktop-display"
keywords = ["monitor", "kanshi"]
run = "kanshictl reload"
```

- [ ] **Step 5: Write `cliphist_pick.sh`**

Create `sway/.config/sway/scripts/cliphist_pick.sh`, then `chmod +x` it:

```sh
#!/bin/sh
# Pick a cliphist entry and put it back on the clipboard: $mod+Ctrl+v and the
# palette's "Clipboard › History".
#
# It was an inline bindsym pipeline. It is a script because the palette runs it
# too (menu.toml's `Clipboard › History`), and the palette raises a failure notification on any non-zero exit: the
# pipeline exited non-zero on Esc, so a cancelled pick would have announced
# itself as a failure. Here a cancelled or empty pick exits 0 (spec §4.2).
set -u
sel=$(cliphist list \
      | fuzzel -d -w 90 -l 30 -p "Select an entry to copy it to your clipboard buffer:") \
    || exit 0
[ -n "$sel" ] || exit 0
printf '%s\n' "$sel" | cliphist decode | wl-copy
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 tests/menu_test.py -v`
Expected: 7 tests, all `ok`. If `test_every_command_in_the_repo_menu_resolves` fails, its message
names the row; fix the row, never the test.

Also run `python3 tests/check_hex.py .`. Expected: exit 0, since nothing added carries a hex.

- [ ] **Step 7: Hook the suite into `theme_test.sh`**

In `tests/theme_test.sh`, directly after `python3 "$REPO/tests/keyhint_test.py" 2>/dev/null`, add:

```sh

# The Super+Space command palette (menu.py, menu.toml). Stubs only; a failure
# aborts. Includes the rot guard: every command menu.toml names must resolve in
# the PATH actions really run with, not this shell's (spec §3.3).
python3 "$REPO/tests/menu_test.py" 2>/dev/null
```

Run: `sh tests/theme_test.sh`
Expected: completes, with its final tally showing no failures.

- [ ] **Step 8: Commit**

```bash
git add sway/.config/sway/scripts/menu.py sway/.config/sway/menu.toml sway/.config/sway/scripts/cliphist_pick.sh tests/menu_test.py tests/theme_test.sh
git commit -m "feat(menu): menu.toml, its validator, the --check rot guard, cliphist_pick.sh

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K3ULXJat1nthjNCUBQVarU"
```

---

### Task 2: The palette (`.desktop` generation, fuzzel launch, fallback)

**Files:**
- Modify: `sway/.config/sway/scripts/menu.py` (add functions above `main`, replace `main`)
- Modify: `tests/menu_test.py` (add `PaletteTest` above `RepoMenuTest`)

**Interfaces:**
- Consumes: everything Task 1 produces.
- Produces (used by Task 3): `notify(summary, body="") -> None`, `execute(argv, env) -> int`
  (execs `argv[0]` found on the inherited PATH; returns 1 after notifying if not found),
  `shown(action, env) -> bool`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/menu_test.py`, above `class RepoMenuTest`:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 tests/menu_test.py -v PaletteTest`
Expected: all FAIL. No-argument `menu.py` prints usage and exits 2, so there are no entries and no fuzzel call.

- [ ] **Step 3: Implement the palette**

In `menu.py`, add the constants below `SYSTEM_PATH`:

```python
DEFAULT_DATA_DIRS = "/usr/local/share:/usr/share"
WHEN_TIMEOUT = 1.0
```

Add these functions above `main`:

```python
def notify(summary, body=""):
    """A critical notification, and the same words on stderr."""
    try:
        subprocess.run(["notify-send", "-u", "critical", "-a", "menu", summary, body],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass
    print(f"menu: {summary}" + (f": {body}" if body else ""), file=sys.stderr)


def execute(argv, env):
    """exec argv[0] -- found on menu.py's own PATH -- with env as its environment.
    Returns only on failure."""
    exe = shutil.which(argv[0])
    if exe is None:
        notify(f"Menu: {argv[0]} not found", f"{argv[0]} is not on PATH")
        return 1
    os.execve(exe, argv, env)


def shown(action, env):
    """A row hides only when its `when` test cleanly says no. A test that hangs
    or cannot execute (126/127) shows it: hiding would be the silent rot this
    palette exists to avoid, and a really-broken action then fails loudly."""
    if "when" not in action:
        return True
    try:
        code = subprocess.run(["sh", "-c", action["when"]], env=action_env(env),
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=WHEN_TIMEOUT).returncode
    except (subprocess.TimeoutExpired, OSError):
        return True
    return code in (0, 126, 127)


def _string(value):
    """A Desktop Entry string: backslash, newline and tab escaped."""
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")


def _exec_arg(arg):
    """One Exec argument: double-quoted with " ` $ \\ escaped, % doubled."""
    return '"' + re.sub(r'(["`$\\])', r"\\\1", arg).replace("%", "%%") + '"'


def desktop_entry(action, exe):
    lines = ["[Desktop Entry]", "Type=Application",
             f"Name={_string(action['group'])} › {_string(action['label'])}",
             f"Icon={_string(action['icon'])}",
             # The Exec value is a string too, so its quoting is escaped again.
             "Exec=" + _string(f"{_exec_arg(exe)} --run {action['id']}")]
    if action.get("keywords"):
        lines.append("Keywords=" + "".join(_string(k).replace(";", "\\;") + ";"
                                           for k in action["keywords"]))
    return "\n".join(lines) + "\n"


def write_entries(actions, appdir, exe):
    """Rewrite the directory from scratch, so a removed row cannot linger."""
    if appdir.exists():
        shutil.rmtree(appdir)
    appdir.mkdir(parents=True)
    for action in actions:
        (appdir / f"menu-{action['id']}.desktop").write_text(desktop_entry(action, exe))


def palette(env):
    """fuzzel's argv and environment for the palette."""
    base = env.get("XDG_RUNTIME_DIR")
    if not base:
        raise RuntimeError("XDG_RUNTIME_DIR is not set")
    root = Path(base) / "fuzzel-menu"
    actions = [a for a in load(config_path()) if shown(a, env)]
    write_entries(actions, root / "applications", str(SCRIPT))
    original = env.get("XDG_DATA_DIRS") or DEFAULT_DATA_DIRS
    cache = Path(env.get("XDG_CACHE_HOME") or Path(env["HOME"]) / ".cache") / "fuzzel-menu"
    # Without the prefix every app launched from here inherits the action
    # directory, and a launcher started from that app would list our actions.
    argv = ["fuzzel", "--cache", str(cache), "--launch-prefix", f"env XDG_DATA_DIRS={original}"]
    return argv, dict(env, XDG_DATA_DIRS=f"{root}:{original}")
```

Replace `main` with:

```python
def main(argv):
    env = dict(os.environ)
    if not argv:
        try:
            fuzzel_argv, fuzzel_env = palette(env)
        except Exception as e:  # anything at all: the key must still open something
            notify("Menu: palette unavailable, plain launcher instead",
                   f"{type(e).__name__}: {e}")
            fuzzel_argv, fuzzel_env = ["fuzzel"], env
        return execute(fuzzel_argv, fuzzel_env)
    if argv == ["--check"]:
        try:
            actions = load(config_path())
        except ConfigError as e:
            print(e, file=sys.stderr)
            return 1
        problems = check(actions, env)
        for problem in problems:
            print(f"menu.toml: {problem}", file=sys.stderr)
        return 1 if problems else 0
    print("usage: menu.py [--check | --run <id> | --group <name>]", file=sys.stderr)
    return 2
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `python3 tests/menu_test.py -v`
Expected: all `ok` (17 tests). If `validate` fails on a *hint* rather than an error, read
`desktop-file-validate`'s output. Hints do not change its exit code, so a non-zero exit is a real
error in `desktop_entry`. Fix it there.

- [ ] **Step 5: Try it live (read-only on the desktop; nothing is bound yet)**

Run: `~/.config/sway/scripts/menu.py` from a terminal. The palette opens; type `reb` and you
should see `System › Reboot` with its icon. Press **Esc**; do not choose an action, because
`--run` arrives in Task 3.

- [ ] **Step 6: Commit**

```bash
git add sway/.config/sway/scripts/menu.py tests/menu_test.py
git commit -m "feat(menu): the palette, as generated .desktop files under fuzzel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K3ULXJat1nthjNCUBQVarU"
```

---

### Task 3: `--run` and `--group`

**Files:**
- Modify: `sway/.config/sway/scripts/menu.py` (add functions above `main`, replace `main`)
- Modify: `tests/menu_test.py` (add `RunTest`, `GroupTest` above `RepoMenuTest`)

**Interfaces:**
- Consumes: `load`, `config_path`, `action_env`, `notify`, `execute`, `shown` (Tasks 1–2).
- Produces: `dmenu(lines, prompt, extra=()) -> str | None`, `tail(data: bytes) -> str`,
  `run_action(action, env) -> int`, `group(name, env) -> int`; the final `main`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/menu_test.py`, above `class RepoMenuTest`:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 tests/menu_test.py -v RunTest GroupTest`
Expected: all FAIL. `--run`/`--group` print usage and exit 2.

- [ ] **Step 3: Implement `--run` and `--group`**

In `menu.py`, add below `WHEN_TIMEOUT`:

```python
STDERR_LINES = 5
```

Add above `main`:

```python
def tail(data):
    """The last few lines of a captured stream, whatever its encoding."""
    lines = data.decode("utf-8", "replace").strip().splitlines()
    return "\n".join(lines[-STDERR_LINES:])


def dmenu(lines, prompt, extra=()):
    """One fuzzel --dmenu pick: the chosen line, or None when dismissed.
    fuzzel 1.15 does not document its exit status on Esc, so 'nothing on
    stdout' is the cancel signal, whatever the code (spec §8)."""
    r = subprocess.run(["fuzzel", "--dmenu", "--prompt", prompt,
                        "--lines", str(min(len(lines), 15)), *extra],
                       input="\n".join(lines) + "\n", capture_output=True, text=True)
    return r.stdout.rstrip("\n") or None


def run_action(action, env):
    """The second step, then the command. Cancelling is not a failure."""
    aenv, label = action_env(env), action["label"]
    choice = None
    if "choices" in action:
        r = subprocess.run(["sh", "-c", action["choices"]], env=aenv,
                           stdin=subprocess.DEVNULL, capture_output=True)
        options = [l for l in r.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
        if r.returncode != 0 or not options:
            notify(f'Menu: "{label}" has nothing to choose ({r.returncode})', tail(r.stderr))
            return 1
        choice = dmenu(options, f"{label} ")
        if choice is None:
            return 0
    if action.get("confirm") and dmenu(["No", "Yes"], f"{label}? ") != "Yes":
        return 0
    command = action["run"]
    if choice is not None:
        command = command.replace("{choice}", shlex.quote(choice))
    if action.get("terminal"):
        # A newline, not `;`, before the pause: a `run` ending in a comment or
        # `&` must not swallow it. bash, for `read -n`.
        script = f'{command}\nprintf "\\n[press a key to close]"; read -rsn1'
        return execute(["kitty", "--class", "menu-term", "bash", "-c", script], aenv)
    r = subprocess.run(["sh", "-c", command], env=aenv, stdin=subprocess.DEVNULL,
                       stderr=subprocess.PIPE)
    if r.returncode != 0:
        notify(f'Menu: "{label}" failed ({r.returncode})', tail(r.stderr))
    return r.returncode


def group(name, env):
    """One group's actions as a dmenu list ($mod+Shift+e), in file order. Not
    the .desktop mechanism: narrowing XDG_DATA_DIRS to hide the apps would hide
    the icon themes with them (spec §3.1)."""
    actions = [a for a in load(config_path()) if a["group"] == name and shown(a, env)]
    if not actions:
        notify(f'Menu: no actions in group "{name}"')
        return 1
    rows = [f"{a['id']}\t{a['label']}\0icon\x1f{a['icon']}" for a in actions]
    picked = dmenu(rows, f"{name} ", ("--with-nth=2", "--accept-nth=1"))
    if picked is None:
        return 0
    by_id = {a["id"]: a for a in actions}
    if picked not in by_id:
        notify(f"Menu: fuzzel returned an unknown id {picked!r}")
        return 1
    return run_action(by_id[picked], env)
```

Replace `main` with the final version:

```python
def main(argv):
    env = dict(os.environ)
    if not argv:
        try:
            fuzzel_argv, fuzzel_env = palette(env)
        except Exception as e:  # anything at all: the key must still open something
            notify("Menu: palette unavailable, plain launcher instead",
                   f"{type(e).__name__}: {e}")
            fuzzel_argv, fuzzel_env = ["fuzzel"], env
        return execute(fuzzel_argv, fuzzel_env)
    if argv == ["--check"]:
        try:
            actions = load(config_path())
        except ConfigError as e:
            print(e, file=sys.stderr)
            return 1
        problems = check(actions, env)
        for problem in problems:
            print(f"menu.toml: {problem}", file=sys.stderr)
        return 1 if problems else 0
    if len(argv) == 2 and argv[0] in ("--run", "--group"):
        try:
            if argv[0] == "--group":
                return group(argv[1], env)
            actions = {a["id"]: a for a in load(config_path())}
            if argv[1] not in actions:
                notify(f"Menu: no action {argv[1]!r}", "menu.toml changed while the palette was open?")
                return 1
            return run_action(actions[argv[1]], env)
        except Exception as e:  # never a silent failure behind a keypress
            notify("Menu: failed", f"{type(e).__name__}: {e}")
            return 1
    print("usage: menu.py [--check | --run <id> | --group <name>]", file=sys.stderr)
    return 2
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `python3 tests/menu_test.py -v`
Expected: all `ok` (30 tests). Then run `sh tests/theme_test.sh`; expect no failures.

- [ ] **Step 5: Try the action path live (nothing bound yet)**

Run `~/.config/sway/scripts/menu.py --group System` from a terminal. It shows Lock … Shutdown with
icons. Pick **Reboot**, then **No**: nothing happens. Next run
`~/.config/sway/scripts/menu.py --run notifications-dismiss-all`: it exits 0 with no notification.

- [ ] **Step 6: Commit**

```bash
git add sway/.config/sway/scripts/menu.py tests/menu_test.py
git commit -m "feat(menu): run actions with confirm, choices and failure toasts; --group

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K3ULXJat1nthjNCUBQVarU"
```

---

### Task 4: Wire it in, and retire `power_menu.sh`

**Files:**
- Modify: `sway/.config/sway/config.d/default` (lines ~33–36, ~51–52, ~168–169, ~291–292)
- Modify: `sway/.config/sway/config.d/application_defaults` (append)
- Modify: `waybar/.config/waybar/config` (`custom/launcher` ~line 29, `custom/power` ~line 224)
- Modify: `PLAYBOOK.md` (§4.3 ~line 307, §9.4 ~line 694)
- Delete: `sway/.config/sway/scripts/power_menu.sh`

**Interfaces:** consumes `menu.py`, `menu.py --group System`, `cliphist_pick.sh`.

- [ ] **Step 1: sway variables.** In `config.d/default`, replace

```
# Power Menu
set $powermenu ~/.config/sway/scripts/power_menu.sh
```

with

```
# The command palette (Super+Space): apps and desktop actions in one fuzzel,
# defined in ~/.config/sway/menu.toml (PLAYBOOK §7). $launcher stays plain
# fuzzel on $mod+d: the fallback if the palette itself is ever broken.
set $palette ~/.config/sway/scripts/menu.py

# Power menu: the palette's System group on its own.
set $powermenu ~/.config/sway/scripts/menu.py --group System
```

- [ ] **Step 2: Bindings.** After the `bindsym $mod+d exec $launcher` line, add

```

    # Open the command palette (Omarchy's key for it)
    bindsym $mod+space exec $palette
```

Replace

```
    # Swap focus between the tiling area and the floating area
    bindsym $mod+space focus mode_toggle
```

with

```
    # Swap focus between the tiling area and the floating area. Was $mod+space,
    # which is now the command palette.
    bindsym $mod+Alt+space focus mode_toggle
```

Replace the `$mod+Ctrl+v` line (keep the comment above it) with

```
    bindsym $mod+Ctrl+v exec ~/.config/sway/scripts/cliphist_pick.sh
```

- [ ] **Step 3: Floating rule.** Append to `config.d/application_defaults`:

```
# The command palette's terminal actions (menu.toml `terminal = true`).
for_window [app_id="menu-term"] floating enable, resize set width 50 ppt height 50 ppt
```

- [ ] **Step 4: waybar.** In `waybar/.config/waybar/config`, change `custom/launcher`'s
`"on-click": "fuzzel",` to `"on-click": "~/.config/sway/scripts/menu.py",` and `custom/power`'s
`"on-click": "exec ~/.config/sway/scripts/power_menu.sh",` to
`"on-click": "exec ~/.config/sway/scripts/menu.py --group System",`.

- [ ] **Step 5: Retire `power_menu.sh` and its references.**

```bash
git rm sway/.config/sway/scripts/power_menu.sh
git grep -n power_menu -- ':!docs/'
```

Expected `git grep` hits are only `PLAYBOOK.md` ~307 and ~694. Edit them:
- §4.3: "`$mod+Shift+e` reaches the same suspend/reboot/shutdown actions through `power_menu.sh`,
  from an" becomes "`$mod+Shift+e` reaches the same suspend/reboot/shutdown actions through the
  command palette's System group (`menu.py --group System`, §7), from an".
- §9.4: "waybar and `power_menu.sh` are full of Nerd Font icons" becomes "waybar is full of Nerd
  Font icons".

Re-run `git grep -n power_menu -- ':!docs/'`; expected: no output.

- [ ] **Step 6: Validate, apply, verify (§9.29)**

```bash
sway --validate -c ~/.config/sway/config && swaymsg reload
pgrep -xc swayidle                                   # exactly 1
pgrep -xc waybar_run.sh                              # exactly 1
sup=$(pgrep -x waybar_run.sh); for p in $(pgrep -x waybar); do awk '/^PPid/{print $2}' /proc/$p/status; done   # each == $sup
swaymsg reload; pgrep -xc swayidle; pgrep -xc waybar_run.sh   # still 1 and 1
python3 tests/keyhint_test.py                        # bind-line count absorbs the new binding
sh tests/theme_test.sh                               # includes menu_test.py and check_sway_exec.py
sh tests/check_consumers.sh                          # sway, waybar, mako still accept their configs
```

Expected: validate is silent, both counts are 1 before and after the second reload, every waybar's
`PPid` equals `$sup`, and all suites pass (`check_consumers.sh` may print `skip` lines; a skip is
not a pass, so read them).

- [ ] **Step 7: Commit**

```bash
git add -A sway/.config/sway waybar/.config/waybar/config PLAYBOOK.md
git commit -m "feat(sway): Super+Space opens the command palette; retire power_menu.sh

focus mode_toggle moves to Super+Alt+Space. Super+Shift+E and waybar's power
button show the palette's System group. Super+Ctrl+V runs cliphist_pick.sh.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K3ULXJat1nthjNCUBQVarU"
```

---

### Task 5: Docs, live check, packages, mutation proof, smoke

**Files:**
- Modify: `PLAYBOOK.md` §7 (after the paragraph ending "nobody notices it rotted.")
- Modify: `CLAUDE.md` (suite list; a Verify paragraph; the `theme` convention line)
- Modify: `tests/check_consumers.sh` (after the `--- sway ---` block)
- Modify: `packages.txt` (alphabetical: after `cliphist`)

- [ ] **Step 1: PLAYBOOK §7.** In the paragraph "**A binding is for something done often.** …",
change "`theme <name>` at a shell is the interface." to "`theme <name>` at a shell, or `Style ›
Theme…` in the command palette, is the interface." Then append after that paragraph:

```markdown
**The command palette is `$mod+space`** (`sway/.config/sway/scripts/menu.py`, actions in
`sway/.config/sway/menu.toml`; design in `docs/specs/2026-10-08-command-palette-design.md`). One
fuzzel window lists every app *and* every desktop action (`System › Reboot`, `Capture › Region →
clipboard`, `Style › Theme…`), searched together and ranked by use: Omarchy's Super+Space,
rebuilt on fuzzel. Each action is written as a `.desktop` file into `$XDG_RUNTIME_DIR/fuzzel-menu`
and fuzzel's ordinary launcher runs over it, so launching an app is exactly what `$mod+d` does.
`$mod+Shift+e` and waybar's power button show the System group alone. `focus mode_toggle`, which
`$mod+space` used to be, is now `$mod+Alt+space`.

The palette is where rare operations live. The rule above still holds for *keys*, and its reason,
silent rot, is answered here rather than ignored: a failing action raises a critical notification
carrying its stderr, and `menu.py --check` (run by `tests/menu_test.py` and `check_consumers.sh`)
fails the moment a command an action names stops resolving. Actions run with a fixed `PATH`,
`~/.local/bin` plus the system directories, because the session's own `PATH` has no
`~/.local/bin` (only `.bashrc` adds it). `--check` resolves against that same `PATH`, so a check
run from a terminal judges what a keypress sees.

`$mod+d` stays plain fuzzel on purpose: if the palette is ever broken, the way to open a terminal
and fix it must not depend on it. A `menu.toml` that fails to load still opens plain fuzzel, with a
notification saying why. The palette retires with the Omarchy migration (D1); `menu.toml` is then
the list of personal actions to recreate as Omarchy menu extensions.
```

- [ ] **Step 2: CLAUDE.md.** In the Verify suite list, after the `keyhint_test.py` line, add:

```sh
python3 tests/menu_test.py    # the Super+Space palette; also run by theme_test.sh
```

After the `tp_backup_test.sh` paragraph, add:

```markdown
**Run `tests/menu_test.py` after any edit to `menu.py`, `menu.toml` or `cliphist_pick.sh`.**
fuzzel, notify-send, kitty, cliphist and wl-copy are logging stubs and `HOME`/`XDG_RUNTIME_DIR`
are throwaway, so nothing reaches the desktop. Actions run with a **fixed** `PATH`
(`~/.local/bin` + system dirs), not the session's, which has no `~/.local/bin`; `menu.py --check`
resolves against that same `PATH`, and the suite's rot guard runs it over the repo's `menu.toml`.
Point `MENU_BIN` at a copy to check the assertions can still fail (PLAYBOOK §7).
```

In Conventions, change "**Switching is `theme <name>`** (`bin/.local/bin/theme`), deliberately
unbound (§7)." to "**Switching is `theme <name>`** (`bin/.local/bin/theme`; also `Style › Theme…`
in the palette), deliberately unbound (§7)."

- [ ] **Step 3: Live check.** In `tests/check_consumers.sh`, after the `--- sway ---` block's
closing `fi`, add:

```sh

# --- menu (the Super+Space palette) ---
# Every command the DEPLOYED menu.toml names must resolve in the PATH actions
# actually run with -- not this shell's, which has ~/.local/bin and more
# (PLAYBOOK §7). menu.py --check never uses its inherited PATH.
menu="$HOME/.config/sway/scripts/menu.py"
if [ -x "$menu" ]; then
    if out=$("$menu" --check 2>&1); then
        ok "menu.toml: every action's command resolves"
    else
        no "menu.toml: every action's command resolves" "$(printf '%s' "$out" | head -2)"
    fi
else
    no "menu.toml: every action's command resolves" "no $menu — run \`stow sway\`"
fi
```

- [ ] **Step 4: packages.txt.** Insert `desktop-file-utils` after `cliphist`.

- [ ] **Step 5: Run everything**

```bash
python3 tests/menu_test.py
sh tests/theme_test.sh
sh tests/check_consumers.sh      # expect: "ok    menu.toml: every action's command resolves"
```

- [ ] **Step 6: Mutation proof (the suite must be able to go red)**

```bash
mut=$(mktemp -d)
python3 - "$mut" <<'EOF'
import sys
from pathlib import Path
src = Path("sway/.config/sway/scripts/menu.py").read_text()
mutants = {
    "no-launch-prefix": ('"--launch-prefix", f"env XDG_DATA_DIRS={original}"', '"--launch-prefix", "true"'),
    "when-timeout-hides": ("    except (subprocess.TimeoutExpired, OSError):\n        return True",
                           "    except (subprocess.TimeoutExpired, OSError):\n        return False"),
    "no-plain-fallback": ('fuzzel_argv, fuzzel_env = ["fuzzel"], env', 'return 1'),
    "no-failure-toast": ("""notify(f'Menu: "{label}" failed ({r.returncode})', tail(r.stderr))""", "pass"),
    "check-inherited-path": ('shutil.which(word, path=action_env(env)["PATH"])', "shutil.which(word)"),
}
for name, (old, new) in mutants.items():
    assert src.count(old) == 1, name
    Path(sys.argv[1], f"{name}.py").write_text(src.replace(old, new))
EOF
for m in "$mut"/*.py; do
    if MENU_BIN="$m" python3 tests/menu_test.py >/dev/null 2>&1; then
        echo "SURVIVED: $(basename "$m")"
    else
        echo "killed:   $(basename "$m")"
    fi
done
rm -rf "$mut"
```

Expected: five `killed:` lines and no `SURVIVED:`. A survivor means the suite cannot see that
regression; strengthen the owning test and re-run before going on.

- [ ] **Step 7: Commit**

```bash
git add PLAYBOOK.md CLAUDE.md tests/check_consumers.sh packages.txt
git commit -m "docs(menu): PLAYBOOK §7 palette, CLAUDE.md test line, live --check

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01K3ULXJat1nthjNCUBQVarU"
```

- [ ] **Step 8: Manual smoke (Xinye; a real keypress can't be automated here)**

1. Press Super+Space, type `reb`, press Enter, choose **No**. Nothing happens.
2. Press Super+Space, open **Google Chrome**, then in a terminal run
   `tr '\0' '\n' </proc/$(pgrep -o chrome)/environ | grep XDG_DATA_DIRS`. The output must not
   contain `fuzzel-menu`.
3. Press Super+Shift+E. Only the System rows appear, with icons, Lock first.
4. Press Super+Space, choose **Style › Theme…**. You're offered `gruvbox`/`nord`; pressing Esc does nothing.
5. Press Super+Space, choose **Dev › Backups: status**. A floating kitty shows the table and closes
   on a key.
6. Press Super+Space, choose **Notifications › Restore last** with an empty history. If it raises
   a "failed" toast, that is the spec §8 caveat: change the row's `run` to absorb that one exit
   code (check `makoctl restore; echo $?` first) and add a test.
```
