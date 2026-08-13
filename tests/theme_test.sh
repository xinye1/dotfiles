#!/bin/sh
# Tests for `theme` and the palette table.
#
# Runs against a throwaway copy of the repo under a fake $HOME, with swaymsg,
# sway and makoctl stubbed to fail, so it never touches the live desktop.
#
#   sh tests/theme_test.sh                                # the copy in the repo
#   THEME_BIN=~/.local/bin/theme sh tests/theme_test.sh   # the installed symlink
#
# What is worth testing changed with the mechanism. The old suite guarded the
# eighteen pointers and the hand-written ignore list; neither exists now. What
# can still go wrong is a template referring to a role no palette defines, the
# two palettes drifting apart, a literal hex sneaking back into a config, or a
# switch dirtying the tree.

set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
THEME_BIN=${THEME_BIN:-$REPO/bin/.local/bin/theme}
pass=0; fail=0

ok()   { pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
no()   { fail=$((fail+1)); printf '  FAIL  %s\n' "$1"; [ $# -lt 2 ] || printf '        %s\n' "$2"; }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else no "$1" "got '$2', want '$3'"; fi; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cp -r "$REPO" "$WORK/dotfiles"
rm -rf "$WORK/dotfiles/.git"
SANDBOX=$WORK/dotfiles

# Stubs: the desktop must never be touched by a test run.
mkdir -p "$WORK/bin"
for stub in swaymsg sway makoctl papirus-folders; do
    printf '#!/bin/sh\nexit 1\n' > "$WORK/bin/$stub"
    chmod +x "$WORK/bin/$stub"
done
PATH=$WORK/bin:$PATH
export PATH HOME=$WORK

theme() { python3 "$SANDBOX/bin/.local/bin/theme" "$@" 2>&1; }

printf '\ntheme\n'

# --- the CLI contract -------------------------------------------------------
out=$(theme --list | tr '\n' ' ' | sed 's/ *$//')
check "--list names both palettes" "$out" "gruvbox nord"

if theme --no-icons no-such-palette >/dev/null 2>&1; then
    no "unknown palette exits non-zero"
else
    ok "unknown palette exits non-zero"
fi
out=$(theme --no-icons no-such-palette || true)
case $out in
    *gruvbox*nord*) ok "unknown palette names the valid ones" ;;
    *)              no "unknown palette names the valid ones" "$out" ;;
esac

# --- rendering --------------------------------------------------------------
for p in nord gruvbox; do
    if theme --no-icons "$p" >/dev/null 2>&1; then
        ok "renders $p"
    else
        no "renders $p" "$(theme --no-icons "$p")"
    fi
done

# Every placeholder in every template must resolve in every palette. `theme`
# dies naming the role when one does not, so a clean run over both is the test.
missing=$(theme --no-icons nord; theme --no-icons gruvbox)
case $missing in
    *"no such role"*) no "every placeholder resolves in both palettes" "$missing" ;;
    *)                ok "every placeholder resolves in both palettes" ;;
esac

# Deterministic: rendering twice must produce identical bytes.
theme --no-icons gruvbox >/dev/null
sum1=$(find "$SANDBOX" -name '*.gen*' ! -name '*.tmpl' -type f -exec cat {} + | md5sum)
theme --no-icons gruvbox >/dev/null
sum2=$(find "$SANDBOX" -name '*.gen*' ! -name '*.tmpl' -type f -exec cat {} + | md5sum)
check "rendering is deterministic" "$sum1" "$sum2"

# Switching and switching back must return the original bytes.
theme --no-icons nord >/dev/null
theme --no-icons gruvbox >/dev/null
sum3=$(find "$SANDBOX" -name '*.gen*' ! -name '*.tmpl' -type f -exec cat {} + | md5sum)
check "switching round-trips" "$sum3" "$sum1"

# --- the palette table ------------------------------------------------------
printf '\npalettes.toml\n'

python3 - "$SANDBOX" <<'PY' && ok "both palettes define exactly the same keys" || no "both palettes define exactly the same keys"
import sys, tomllib
d = tomllib.load(open(sys.argv[1] + "/palettes.toml", "rb"))
def flat(p, pre=""):
    o = {}
    for k, v in p.items():
        o.update(flat(v, f"{pre}{k}_")) if isinstance(v, dict) else o.update({f"{pre}{k}": v})
    return o
shapes = {n: set(flat(t)) for n, t in d.items()}
first = next(iter(shapes))
sys.exit(0 if all(s == shapes[first] for s in shapes.values()) else 1)
PY

# A role defined in only one palette renders as black in GTK CSS with no error,
# which is why this is a test and not a comment. Simulate the drift.
python3 - "$WORK" "$SANDBOX" <<'PY' >/dev/null 2>&1 && no "a role missing from one palette is refused" || ok "a role missing from one palette is refused"
import sys, shutil, subprocess, tomllib, pathlib
work, sandbox = sys.argv[1], sys.argv[2]
broken = pathlib.Path(work) / "broken"
shutil.copytree(sandbox, broken, dirs_exist_ok=True)
p = broken / "palettes.toml"
text = p.read_text().replace('indicator = ', 'indicator_renamed = ', 1)
p.write_text(text)
r = subprocess.run([sys.executable, str(broken / "bin/.local/bin/theme"),
                    "--no-icons", "nord"], capture_output=True)
sys.exit(r.returncode)
PY

# --- the standing rule: no literal colour outside the table -----------------
printf '\nconventions\n'
# Comment lines are exempt: the rule forbids a hex as a config VALUE, and the
# configs explain their own history in prose.
stray=$(cd "$REPO" && git ls-files 2>/dev/null \
        | grep -v -e '^palettes.toml$' -e '^docs/' -e '\.md$' -e '^tests/' \
        | while read -r f; do
            sed -E '/^[[:space:]]*(#|--|"|\/\/|\/\*|\*)/d' "$f" 2>/dev/null \
              | grep -qEi '#[0-9a-f]{6}\b' && echo "$f"
          done || true)
if [ -z "$stray" ]; then
    ok "no tracked config carries a literal hex"
else
    no "no tracked config carries a literal hex" "$(echo "$stray" | tr '\n' ' ')"
fi

# Every colour file an application includes must be one a template produces.
# This is the assertion that would have caught a repointing being reverted: the
# include still named `colors.css`, no template produced it any more, and
# nothing failed loudly because sway and GTK treat a missing include as a
# warning rather than an error.
python3 "$REPO/tests/check_includes.py" "$REPO" \
  && ok "every include names a file a template renders" \
  || no "every include names a file a template renders"

# Switching is an operational change, never a git one.
if [ -d "$REPO/.git" ]; then
    before=$(cd "$REPO" && git status --porcelain | sort | md5sum)
    (cd "$REPO" && python3 bin/.local/bin/theme --no-icons nord >/dev/null 2>&1) || true
    (cd "$REPO" && python3 bin/.local/bin/theme --no-icons "$(cat "$REPO/.theme" 2>/dev/null || echo gruvbox)" >/dev/null 2>&1) || true
    after=$(cd "$REPO" && git status --porcelain | sort | md5sum)
    check "switching leaves git status untouched" "$after" "$before"
fi

printf '\n%s  %d assertions\n\n' "$([ "$fail" -eq 0 ] && echo PASS || echo FAIL)" "$((pass+fail))"
[ "$fail" -eq 0 ]
