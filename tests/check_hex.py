"""Assert no tracked config carries a literal colour outside palettes.toml.

Comment syntax is per-language, which matters more than it looks: treating a
leading `"` as a comment marker everywhere (vimscript's rule) exempts every
line of waybar's JSON, because JSON lines start with a quoted key. That made
the check pass on files it had never actually examined.
"""
import re
import subprocess
import sys
from pathlib import Path

COMMENT_MARKERS = {
    ".vim": (r'"', r'^\s*"'),
    ".lua": (None, r'^\s*--'),
    ".css": (None, r'^\s*(/\*|\*)'),
    ".toml": (None, r'^\s*#'),
    ".ini": (None, r'^\s*#'),
    ".conf": (None, r'^\s*#'),
    ".sh": (None, r'^\s*#'),
    ".json": (None, r'^\s*//'),      # waybar's JSON accepts // comments
}
DEFAULT_COMMENT = r'^\s*#'
# 3-, 4-, 6- and 8-digit forms are all legal CSS/GTK colours.
HEX = re.compile(r'#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3,4}\b')
SKIP_PREFIX = ("tests/", "docs/")
SKIP_EXACT = {"palettes.toml"}


def comment_re(path):
    return re.compile(COMMENT_MARKERS.get(path.suffix, (None, DEFAULT_COMMENT))[1])


def main(repo):
    repo = Path(repo)
    files = subprocess.run(["git", "-C", str(repo), "ls-files"],
                           capture_output=True, text=True).stdout.split()
    bad = []
    for rel in files:
        if rel in SKIP_EXACT or rel.startswith(SKIP_PREFIX) or rel.endswith((".md", ".tmpl")):
            continue
        path = repo / rel
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        skip = comment_re(path)
        for n, line in enumerate(text.splitlines(), 1):
            if skip.match(line):
                continue
            if HEX.search(line):
                bad.append(f"{rel}:{n}: literal colour outside palettes.toml: {line.strip()[:60]}")
    for line in bad:
        print(line, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
