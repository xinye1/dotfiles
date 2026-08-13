"""Assert every colour file an application includes is one a template renders.

Split out of theme_test.sh because it needs real parsing. A missing include is
a *warning* in sway and GTK, not an error, so this class of breakage is silent
at runtime and has to be caught here.
"""
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = [
    r'include\s*=\s*\S*?([\w.-]+)$',
    r'@import\s+url\("([^"]+)"\)',
    r'include\s+\S*?([\w.-]+)$',
    r'"include"\s*:\s*\["[^"]*?/([^"/]+)"\]',
    r'\.\s+"\$HOME/\S*?/([\w.-]+)"',
    r'source\s+~\S*?/([\w.-]+)$',
    r'"~/\.config/alacritty/([\w.-]+)"',
    r"stdpath\('config'\) \.\. '/([\w.-]+)'",
]
COMMENT = re.compile(r'^\s*(#|//|--|"|/\*|\*)')
INTERESTING = re.compile(r'colors|colorscheme|theme\.')


def main(repo):
    repo = Path(repo)
    produced = {p.with_suffix("").name for p in repo.rglob("*.tmpl")}
    files = subprocess.run(["git", "-C", str(repo), "ls-files"],
                           capture_output=True, text=True).stdout.split()
    bad = set()
    for rel in files:
        if rel.endswith((".tmpl", ".md")) or rel.startswith(("tests/", "docs/")):
            continue
        try:
            text = (repo / rel).read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            if COMMENT.match(line):
                continue
            for pat in PATTERNS:
                m = re.search(pat, line.strip())
                if m and INTERESTING.search(m.group(1)):
                    if m.group(1) not in produced:
                        bad.add(f"{rel}: includes {m.group(1)}, which no template renders")
                    break
    for line in sorted(bad):
        print(line, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
