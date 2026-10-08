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
