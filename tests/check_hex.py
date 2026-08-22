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

# Suffix -> the regex matching a comment line in that language. The same table
# lives in check_includes.py, which needs the identical knowledge for the
# identical reason; keep the two in step.
COMMENT_MARKERS = {
    ".vim": r'^\s*"',
    ".lua": r'^\s*--',
    ".css": r'^\s*(/\*|\*)',
    ".toml": r'^\s*#',
    ".ini": r'^\s*#',
    ".conf": r'^\s*#',
    ".sh": r'^\s*#',
    ".json": r'^\s*//',              # waybar's JSON accepts // comments
}
# Extensionless and unknown: `#` covers sway's config.d, foot, mako, htoprc and
# the shell rc files. Deliberately NOT `"` — that is vimscript's rule alone,
# and applying it everywhere is the bug this file's docstring describes.
DEFAULT_COMMENT = r'^\s*#'
# waybar's `config` is JSONC too, but has no suffix to key COMMENT_MARKERS on,
# so without this it falls through to DEFAULT_COMMENT and a `//`-commented hex
# reads as a live one. Keyed by the exact repo-relative path rather than
# basename: kanshi and mako also ship an extensionless `config`, and those
# really are `#`-commented, so matching on the filename alone would break
# them. Same table, same reason, as check_includes.py — keep the two in step.
PATH_COMMENT_MARKERS = {
    "waybar/.config/waybar/config": r'^\s*//',
}
# 3-, 4-, 6- and 8-digit forms are all legal CSS/GTK colours.
HEX = re.compile(r'#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3,4}\b')
# ...but not every consumer spells a colour with a leading `#`. fuzzel's -t/-S
# take a bare RRGGBBAA, and a `#`-only check passed for months while
# `-t bf616aff` sat in a sway binding: same colour, different spelling, guard
# blind to it. A green check asserting a rule it cannot see is worse than no
# check, because the next colour gets added on the strength of it.
#
# Deliberately not requiring a letter a-f: that would exempt `112233`, a real
# colour. Pure-digit runs of exactly 6 or 8 are vanishingly rare in these
# configs (measured: zero across the tracked tree), and a false positive here
# fails loudly, which is the right direction for a guard to be wrong in.
BARE_HEX = re.compile(r'(?<![#\w])(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6})(?!\w)')
SKIP_PREFIX = ("tests/", "docs/")
SKIP_EXACT = {"palettes.toml"}


def comment_re(rel, path):
    if rel in PATH_COMMENT_MARKERS:
        return re.compile(PATH_COMMENT_MARKERS[rel])
    return re.compile(COMMENT_MARKERS.get(path.suffix, DEFAULT_COMMENT))


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
        skip = comment_re(rel, path)
        for n, line in enumerate(text.splitlines(), 1):
            if skip.match(line):
                continue
            if HEX.search(line):
                bad.append(f"{rel}:{n}: literal colour outside palettes.toml: {line.strip()[:60]}")
            elif BARE_HEX.search(line):
                bad.append(f"{rel}:{n}: literal colour (bare, no '#') outside "
                           f"palettes.toml: {line.strip()[:60]}")
    for line in bad:
        print(line, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
