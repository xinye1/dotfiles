#!/usr/bin/env python3
"""menu — the Super+Space palette: apps and desktop actions in one fuzzel.

Design: docs/specs/2026-10-08-command-palette-design.md. The actions live in
~/.config/sway/menu.toml. Each visible action is written as a .desktop file
into $XDG_RUNTIME_DIR/fuzzel-menu/<pid>/applications and fuzzel runs in its ordinary
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
import fcntl
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
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
DEFAULT_DATA_DIRS = "/usr/local/share:/usr/share"
WHEN_TIMEOUT = 1.0
STDERR_LINES = 5
FUZZEL_WAIT = 2.0
# fuzzel's own search fields default to filename,name,generic: without
# keywords, `screenshot` or `restart` would find nothing (spec §4.2).
FIELDS = "filename,name,generic,keywords"


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
    try:
        os.execve(exe, argv, env)
    except OSError as e:  # found but not runnable: a traceback here goes nowhere
        notify(f"Menu: cannot start {argv[0]}", f"{type(e).__name__}: {e}")
        return 1


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


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def prune(root):
    """Remove the directories of palettes that are no longer running, and the
    pre-fix shared `applications` directory. A live palette's is left alone:
    its fuzzel may still be reading it."""
    if not root.is_dir():
        return
    for d in root.iterdir():
        if d.name == "applications" or (d.name.isdigit() and not alive(int(d.name))):
            shutil.rmtree(d, ignore_errors=True)


def write_entries(actions, appdir, exe):
    """Write a fresh directory, so a removed row cannot linger."""
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
    # One directory per palette, named for this pid -- which execve hands on to
    # fuzzel. A second Super+Space therefore never rewrites files a running
    # fuzzel may still be reading; it only prunes palettes that have exited.
    root = Path(base) / "fuzzel-menu"
    mine = root / str(os.getpid())
    actions = [a for a in load(config_path()) if shown(a, env)]
    prune(root)
    write_entries(actions, mine / "applications", str(SCRIPT))
    original = env.get("XDG_DATA_DIRS") or DEFAULT_DATA_DIRS
    cache = Path(env.get("XDG_CACHE_HOME") or Path(env["HOME"]) / ".cache") / "fuzzel-menu"
    # Without the prefix every app launched from here inherits the action
    # directory, and a launcher started from that app would list our actions.
    argv = ["fuzzel", "--cache", str(cache), "--fields", FIELDS,
            "--launch-prefix", f"env XDG_DATA_DIRS={original}"]
    return argv, dict(env, XDG_DATA_DIRS=f"{mine}:{original}")


def wait_for_fuzzel(env):
    """Wait, up to FUZZEL_WAIT seconds, until no fuzzel holds its instance lock.

    fuzzel allows one instance per display (an flock on
    $XDG_RUNTIME_DIR/fuzzel-$WAYLAND_DISPLAY.lock) and keeps it until it has
    finished tearing down -- after it has already started `menu.py --run`. A
    second-step fuzzel started in that window exits 1 with nothing on stdout,
    which reads exactly like Esc: Shutdown -> Enter would quietly do nothing.
    False means it never let go."""
    runtime, display = env.get("XDG_RUNTIME_DIR"), env.get("WAYLAND_DISPLAY")
    if not runtime or not display:
        return True
    lock = Path(runtime) / f"fuzzel-{display}.lock"
    deadline = time.monotonic() + FUZZEL_WAIT
    while True:
        try:
            fd = os.open(lock, os.O_RDONLY)
        except FileNotFoundError:
            return True
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            pass
        finally:
            os.close(fd)  # releases the probe's own lock at once
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


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
    # stderr to a file, not a pipe: wl-copy (cliphist_pick.sh, capture's OCR)
    # forks to serve the clipboard and keeps the action's stderr, so a pipe read
    # to EOF would hang this palette until the next copy.
    with tempfile.TemporaryFile() as err:
        r = subprocess.run(["sh", "-c", command], env=aenv, stdin=subprocess.DEVNULL, stderr=err)
        if r.returncode != 0:
            err.seek(0)
            notify(f'Menu: "{label}" failed ({r.returncode})', tail(err.read()))
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
            if not wait_for_fuzzel(env):
                notify("Menu: fuzzel is still running",
                       f"another fuzzel held its lock for over {FUZZEL_WAIT:g} s; nothing was run")
                return 1
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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
