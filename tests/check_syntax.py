"""Assert every rendered file is syntactically acceptable to the tool that reads it.

This exists because a generated-file banner was written in the wrong comment
syntax and nothing noticed until the bar disappeared. `#` is a comment in most
of these formats and in none of JSON or legacy vimscript, so a banner that
defaults to `#` produces a file the consumer refuses to parse — and both waybar
and vim fail at startup, not at render time.
"""
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

# The comment marker each consumer actually accepts.
COMMENT = {
    ".json": "//",     # waybar's parser takes // but not #
    ".vim": '"',       # legacy vimscript; # is E492
    ".lua": "--",
    ".css": "/*",
    ".toml": "#",
    ".ini": "#",
    ".conf": "#",
    ".env": "#",
}
DEFAULT = "#"


def marker_for(path):
    name = path.name
    if name.startswith(".gtkrc"):
        return "#"
    for suffix, mark in COMMENT.items():
        if name.endswith(suffix):
            return mark
    return DEFAULT


def main(repo):
    repo = Path(repo)
    bad = []
    for tmpl in sorted(repo.rglob("*.tmpl")):
        out = tmpl.with_suffix("")
        if not out.exists():
            bad.append(f"{out.relative_to(repo)}: not rendered")
            continue
        text = out.read_text()
        want = marker_for(out)
        first = next((l for l in text.splitlines() if l.strip()), "")
        if first.strip() and not first.lstrip().startswith(want):
            # only complain when the line is prose, not config
            if re.match(r'^\s*(#|//|--|"|/\*)', first):
                bad.append(f"{out.relative_to(repo)}: comment starts {first.strip()[:2]!r}, "
                           f"but this format needs {want!r}")
        # machine-checkable formats get parsed for real
        try:
            if out.name.endswith(".json"):
                json.loads(re.sub(r'(?m)^\s*//.*$', '', text))
            elif out.name.endswith(".toml"):
                tomllib.loads(text)
        except (json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
            bad.append(f"{out.relative_to(repo)}: does not parse: {exc}")
    for line in bad:
        print(line, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
