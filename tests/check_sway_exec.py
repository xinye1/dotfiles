"""Assert no top-level `exec`/`exec_always` line carries an unquoted `;`.

sway runs an exec line by two different routes, and only one of them treats the
line as a single shell command.

At a *reload* the config is already active, so the line is dispatched straight
to `sh -c` with the `;` intact. At **startup** the same line is deferred into a
queue and replayed through the parser `swaymsg` uses, and that parser splits a
command string on `;`. So

    exec_always pkill -x idle.sh; pkill -x swayidle; ~/.config/sway/scripts/idle.sh

ran only the first `pkill` at login and rejected the other two segments as
unknown sway commands, while a reload started the daemon perfectly. The machine
booted with no swayidle -- no lock, ever -- and every reload-based check said 1.
`kanshi` had been broken the same way for as long as its line existed.

The fix is to hand sway one command whose `;` are the inner shell's:

    exec_always sh -c 'pkill -x idle.sh; pkill -x swayidle; exec ~/…/idle.sh'

Hence the invariant asserted here, across every exec line rather than the two
that were found broken: a `;` outside quotes on an exec line is a boot-time
failure that no `swaymsg reload` can reproduce. See PLAYBOOK.md §9.2.

`bindsym … exec …` is deliberately out of scope: a binding is dispatched through
the splitting parser by design, so `;` there separates sway commands and means
what it says.
"""
import sys
from pathlib import Path

KEYWORDS = ("exec", "exec_always")


def unquoted_semicolon(command):
    """True if `command` contains a `;` at quoting level zero."""
    in_single = in_double = False
    for ch in command:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ";" and not in_single and not in_double:
            return True
    return False


def logical_lines(text):
    """Yield (line_number, joined_text), folding trailing-backslash continuations."""
    buf, start = "", None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if start is None:
            start = n
        if line.endswith("\\"):
            buf += line[:-1]
            continue
        yield start, buf + line
        buf, start = "", None
    if start is not None:
        yield start, buf


def main(repo):
    sway = Path(repo) / "sway/.config/sway"
    targets = [sway / "config"] + sorted((sway / "config.d").glob("*"))
    bad = []
    for path in targets:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for n, line in logical_lines(text):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Split on whitespace, not a literal space: sway accepts a tab
            # between a command and its arguments (`sway --validate` takes
            # `exec_always\ttrue`), and a guard that skips that spelling is
            # exactly the blind spot this file exists to close.
            parts = stripped.split(None, 1)
            head = parts[0]
            rest = parts[1] if len(parts) > 1 else ""
            if head not in KEYWORDS:
                continue
            if unquoted_semicolon(rest):
                rel = path.relative_to(repo)
                bad.append(
                    f"{rel}:{n}: `{head}` line has a `;` outside quotes, so only the "
                    f"first segment runs at sway startup -- wrap it as "
                    f"`{head} sh -c '...'`"
                )
    for line in bad:
        print(line, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
