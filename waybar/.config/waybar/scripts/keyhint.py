#!/usr/bin/env python3
"""keyhint — every sway key binding, read from the live config, shown in fuzzel.

Clicking the waybar clock runs this. It replaced keyhint.sh, a hardcoded yad
grid inherited from stock EndeavourOS: a flat cell list that read no config,
so it drifted from the real bindings, and whose 5-column layout shifted every
later row when a cell was missed (PLAYBOOK §7). Omarchy builds its cheat sheet
from the compositor's own bindings; sway has no IPC call that lists them
(`get_config` returns only the top-level file, not what it includes), so this
reads the files sway reads, the way sway reads them:

  * `include` lines are followed — `~` and environment variables expanded,
    globs in sorted order (sway's own), relative paths against the including
    file's directory;
  * `set $name value` defines a variable, substituted into keys and commands;
  * `bindsym`/`bindcode` come one per line or as a `bindsym [flags] { … }`
    block, and a `mode "name" { … }` block labels the bindings inside it;
  * a line ending in `\\` continues onto the next, and only a line whose first
    non-blank character is `#` is a comment.

Display only: choosing a row does nothing. The list is the answer.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

MODIFIERS = {"mod4": "Super", "mod1": "Alt", "ctrl": "Ctrl", "control": "Ctrl",
             "shift": "Shift"}
# bindcode's digit row: keycode 10 is `1` … 19 is `0` on every layout, which
# is why the workspace bindings use bindcode at all.
KEYCODES = {str(code): str((code - 9) % 10) for code in range(10, 20)}
BIND = re.compile(r"^(bindsym|bindcode)((?:\s+--[\w-]+)*)\s*(.*)$")


def logical_lines(path):
    """The file's lines with `\\` continuations joined and comments dropped."""
    out, pending = [], ""
    for raw in path.read_text(errors="replace").splitlines():
        line = pending + raw.strip()
        if line.endswith("\\"):
            pending = line[:-1] + " "
            continue
        pending = ""
        if line and not line.startswith("#"):
            out.append(line)
    if pending.strip():
        out.append(pending.strip())
    return out


def expand(text, variables):
    # Longest name first, so `$mod_alt` is never read as `$mod` + `_alt`.
    for name in sorted(variables, key=len, reverse=True):
        text = text.replace(name, variables[name])
    return text


def pretty_keys(keys, kind):
    parts = []
    for part in keys.split("+"):
        low = part.lower()
        if low in MODIFIERS:
            parts.append(MODIFIERS[low])
        elif kind == "bindcode" and part in KEYCODES:
            parts.append(KEYCODES[part])
        else:
            parts.append(part[:1].upper() + part[1:] if len(part) == 1 else part)
    return "+".join(parts)


def pretty_command(command):
    command = re.sub(r"\s+", " ", command)          # source alignment is not meaning
    command = re.sub(r"^exec\s+", "", command)
    return re.sub(r"(~|\S*)/\.config/sway/scripts/", "", command)


def bindings(config):
    """[(mode, keys, command)] for every key binding reachable from `config`."""
    variables, rows = {}, []
    stack = []            # one entry per open `{`: ("mode", name) / ("bind", kind) / ("other", _)

    def walk(path, seen):
        path = path.resolve()
        if path in seen or not path.is_file():
            return
        seen.add(path)
        for line in logical_lines(path):
            if line == "}":
                if stack:
                    stack.pop()
                continue
            if line.startswith("include "):
                pattern = expand(line.split(None, 1)[1].strip().strip('"'), variables)
                # sway runs include paths through wordexp(3): ~ and $HOME both.
                pattern = os.path.expandvars(os.path.expanduser(pattern))
                if not os.path.isabs(pattern):
                    pattern = str(path.parent / pattern)
                for name in sorted(glob.glob(pattern)):
                    walk(Path(name), seen)
                continue
            if line.startswith("set $"):
                _, name, *value = line.split(None, 2)
                variables[name] = expand(value[0], variables) if value else ""
                continue
            mode = next((v for k, v in reversed(stack) if k == "mode"), "default")
            if line.endswith("{"):
                head = line[:-1].strip()
                bind = BIND.match(head)
                if head.startswith("mode "):
                    stack.append(("mode", head.split(None, 1)[1].strip('"')))
                elif bind:
                    stack.append(("bind", bind.group(1)))
                else:
                    stack.append(("other", head))
                continue
            inner = stack[-1] if stack else None
            if inner and inner[0] == "bind":
                kind, rest = inner[1], line
            elif (bind := BIND.match(line)) and (not inner or inner[0] == "mode"):
                kind, rest = bind.group(1), bind.group(3)
            else:
                continue
            keys, _, command = rest.partition(" ")
            if command.strip():
                rows.append((mode, pretty_keys(expand(keys, variables), kind),
                             pretty_command(expand(command.strip(), variables))))

    walk(Path(config).expanduser(), set())
    return rows


def render(rows):
    width = max((len(keys) for _, keys, _ in rows), default=0)
    return [f"{keys:<{width}}  {command}" + ("" if mode == "default" else f"   [{mode} mode]")
            for mode, keys, command in rows]


def main(argv):
    """keyhint [--print] [CONFIG] — --print writes the list to stdout instead."""
    to_stdout = "--print" in argv
    rest = [a for a in argv if a != "--print"]
    config = rest[0] if rest else "~/.config/sway/config"
    lines = render(bindings(config))
    if not lines:
        print(f"keyhint: no bindings found under {config}", file=sys.stderr)
        return 1
    if to_stdout or not shutil.which("fuzzel"):
        print("\n".join(lines))
        return 0
    subprocess.run(["fuzzel", "--dmenu", "--prompt", "keys  ", "--width", "100",
                    "--lines", "30"], input="\n".join(lines), text=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
