"""Assert every colour file an application includes is one a template renders.

A missing include is a *warning* in sway and GTK, not an error, so this class
of breakage is silent at runtime and has to be caught here. It has happened:
a revert restored the pre-rename include paths, the files they named no longer
existed, and a sway reload still reported success.

Paths are compared resolved, not by basename. `colors.gen.*` is the house name
for a rendered palette, so the same basename recurs across packages and a
basename comparison would pass an include that points at the right filename in
the wrong directory. The collision that first made this concrete has since gone
away — `~/.config/waybar` and `~/.config/gtklock` both held a `colors.gen.css`
until gtklock was retired for swaylock — but the rule outlives the example: the
next themed package to render a `colors.gen.css` reintroduces it silently, and
nothing here would notice.
"""
import re
import subprocess
import sys
from pathlib import PurePosixPath
from pathlib import Path

# Each pattern captures the path as written in the config.
PATTERNS = [
    r'include\s*=\s*(\S+)',
    r'@import\s+url\("([^"]+)"\)',
    r'include\s+(\S+)',
    r'"include"\s*:\s*\["([^"]+)"\]',
    r'\.\s+"(\$HOME/[^"]+)"',
    r'source\s+(~\S+)',
    r'"(~/\.config/[^"]+)"',
    r"stdpath\('config'\) \.\. '(/[\w.-]+)'",
]
# Comment syntax is per-language, and getting that wrong here silently disabled
# the pattern this file exists for. A single alternation with `"` in it treats
# a leading double quote as a comment marker in EVERY file type; every line of
# waybar's JSON starts with a quoted key, so every one of them was skipped and
# the `"include": [...]` pattern below could never fire. Repointing waybar's
# include at a file no template renders still exited 0.
#
# Same table, same reason, as check_hex.py — keep the two in step.
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
# the shell rc files. waybar's `config` is JSON with no suffix and lands here —
# which is the point: `"` must not exempt it.
DEFAULT_COMMENT = r'^\s*#'
INTERESTING = re.compile(r'colors|colorscheme|theme\.')


def comment_re(path):
    return re.compile(COMMENT_MARKERS.get(path.suffix, DEFAULT_COMMENT))


def home_relative(package_path):
    """`waybar/.config/waybar/x` -> `.config/waybar/x` (drop the package dir)."""
    parts = PurePosixPath(package_path).parts
    return PurePosixPath(*parts[1:]) if len(parts) > 1 else PurePosixPath(package_path)


def normalise(path):
    out = []
    for part in PurePosixPath(path).parts:
        if part == "..":
            if out:
                out.pop()
        elif part not in (".", ""):
            out.append(part)
    return PurePosixPath(*out)


def main(repo):
    repo = Path(repo)
    produced = {normalise(home_relative(str(p.with_suffix("").relative_to(repo))))
                for p in repo.rglob("*.tmpl")}
    files = subprocess.run(["git", "-C", str(repo), "ls-files"],
                           capture_output=True, text=True).stdout.split()
    bad = set()
    for rel in files:
        if rel.endswith((".tmpl", ".md")) or rel.startswith(("tests/", "docs/")):
            continue
        path = repo / rel
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        skip = comment_re(path)
        for line in text.splitlines():
            if skip.match(line):
                continue
            for pat in PATTERNS:
                m = re.search(pat, line.strip())
                if not m or not INTERESTING.search(m.group(1)):
                    continue
                ref = m.group(1)
                if ref.startswith("$HOME/"):
                    target = PurePosixPath(ref[len("$HOME/"):])
                elif ref.startswith("~/"):
                    target = PurePosixPath(ref[2:])
                elif ref.startswith("/"):
                    target = home_relative(rel).parent / ref.lstrip("/")
                else:
                    target = home_relative(rel).parent / ref
                if normalise(target) not in produced:
                    bad.add(f"{rel}: includes {ref} -> {normalise(target)}, "
                            f"which no template renders")
                break
    for line in sorted(bad):
        print(line, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
