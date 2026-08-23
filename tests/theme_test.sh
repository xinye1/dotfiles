#!/bin/sh
# Tests for `theme` and the palette table.
#
# Runs against a throwaway copy of the repo under a fake $HOME, with swaymsg,
# sway and makoctl stubbed to fail, so it never touches the live desktop.
#
#   sh tests/theme_test.sh
#
# What is worth testing changed with the mechanism. The old suite guarded the
# eighteen pointers and the hand-written ignore list; neither exists now. What
# can still go wrong is a template referring to a role no palette defines, the
# two palettes drifting apart, a literal hex sneaking back into a config, or a
# switch dirtying the tree.

set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

# REPO is derived from this script's location, so running a COPY of it from
# somewhere else resolves it somewhere else too -- from /tmp it resolves to /,
# and the `cp -r "$REPO"` below then copies the entire filesystem into a tmpfs.
# That is not hypothetical; it filled a 16G /tmp. Refuse unless REPO really is
# the repo.
for marker in palettes.toml bin/.local/bin/theme .stowrc; do
    [ -e "$REPO/$marker" ] || {
        printf 'theme_test: %s does not look like the dotfiles repo (no %s).\n' "$REPO" "$marker" >&2
        printf 'theme_test: run this script from inside the repo, not a copy.\n' >&2
        exit 2
    }
done
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
#
# The list is DERIVED from `theme` itself, not hand-written. It was
# hand-written, and it went stale: `kitty` became a reload target in `theme`
# and was never added here, so shutil.which("kitty") found the REAL binary and
# every run of this "never touches the live desktop" suite made all of the
# user's live kitty windows re-read their config -- ten times per run,
# discarding whatever runtime overrides they were holding. Every external
# binary `theme` names is either a shutil.which("x") or the first element of a
# subprocess argv list, so matching those two shapes cannot silently miss the
# next reload target the way a hand-kept list did.
mkdir -p "$WORK/bin"
stubs=$(grep -oE '(shutil\.which|run_ok|subprocess\.run)\(\[?"[a-z0-9_.-]+"' \
            "$SANDBOX/bin/.local/bin/theme" \
        | grep -oE '"[a-z0-9_.-]+"' | tr -d '"' | sort -u)
# A floor, not the list. The derivation may only ever ADD to this; if it ever
# matches nothing -- `theme` rewritten, a call spelled another way -- that has
# to be loud here rather than silent on the user's desktop.
for required in swaymsg sway makoctl papirus-folders kitty; do
    printf '%s\n' $stubs | grep -qx "$required" || {
        printf 'theme_test: no "%s" found in bin/.local/bin/theme by the stub\n' "$required" >&2
        printf 'theme_test: derivation, so it would not be stubbed and the real\n' >&2
        printf 'theme_test: binary would run. Refusing. Derived: %s\n' "$(printf '%s ' $stubs)" >&2
        exit 2
    }
done
for stub in $stubs; do
    printf '#!/bin/sh\nexit 1\n' > "$WORK/bin/$stub"
    chmod +x "$WORK/bin/$stub"
done
HOME_REAL=$HOME
PATH=$WORK/bin:$PATH
export PATH HOME=$WORK
# $HOME alone does not sandbox `theme`: state_file() reads $XDG_STATE_HOME
# FIRST and only falls back to ~/.local/state, so an exported XDG_STATE_HOME
# wins over the fake HOME and the suite writes the user's real remembered
# palette -- after which the next bare `theme`, or ./setup.sh, flips their
# desktop. It is merely unset on this machine today; one line in a profile is
# all it takes. The note further down about being left "on a different palette.
# Silently." is this same shape, caught once for the in-repo .theme file and
# not for the XDG one. Point the whole set inside the sandbox, not just the one
# variable `theme` happens to read today.
export XDG_STATE_HOME=$WORK/.local/state
export XDG_CACHE_HOME=$WORK/.cache
export XDG_CONFIG_HOME=$WORK/.config
export XDG_DATA_HOME=$WORK/.local/share

theme() { python3 "$SANDBOX/bin/.local/bin/theme" "$@" 2>&1; }

printf '\ntheme\n'

# The installed script is checked, but never used to RENDER: it resolves its
# repo from its own path, so rendering through it would write to the live tree.
# `--list` proves the symlink and the interpreter are good without doing that.
if [ -x "$HOME_REAL/.local/bin/theme" ]; then
    if "$HOME_REAL/.local/bin/theme" --list >/dev/null 2>&1; then
        ok "the installed ~/.local/bin/theme runs"
    else
        no "the installed ~/.local/bin/theme runs"
    fi
fi

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

# The checksums below are driven off the TEMPLATE list, never off a glob of the
# outputs. `-name '*.gen*'` was the glob, and it structurally cannot match the
# seven rendered files that carry no marker -- gtk-{3,4}.0/gtk.css,
# gtk-{3,4}.0/settings.ini, xsettingsd.conf, .gtkrc-2.0, yazi/theme.toml --
# because they are read at hardcoded paths and cannot be renamed (§2.3). Seven
# of nineteen escaped both checks below, and they are precisely the ones whose
# failure modes are silent: an undefined GTK @name renders black with no error
# (§9.10), a dropped yazi key is ignored without a warning (§9.22).
#
# Every `*.tmpl` renders to itself with the suffix stripped, so the templates
# ARE the list of outputs, and no naming convention can leave one out.
rendered_files() { find "$SANDBOX" -name '*.tmpl' -type f | sed 's/\.tmpl$//' | sort; }
rendered_sum()   { rendered_files | tr '\n' '\0' | xargs -0 cat | md5sum; }

theme --no-icons gruvbox >/dev/null

# ...which is only true while every template has actually produced its output.
# A missing one would otherwise drop silently out of both checksums and take
# its coverage with it -- the same failure the glob had, one level down.
want=$(rendered_files | wc -l)
got=$(rendered_files | while IFS= read -r f; do [ -f "$f" ] && printf 'x\n'; done | wc -l)
check "every template renders an output the checksums cover" "$got" "$want"

# Deterministic: rendering twice must produce identical bytes.
sum1=$(rendered_sum)
theme --no-icons gruvbox >/dev/null
sum2=$(rendered_sum)
check "rendering is deterministic" "$sum1" "$sum2"

# Switching and switching back must return the original bytes.
theme --no-icons nord >/dev/null
theme --no-icons gruvbox >/dev/null
sum3=$(rendered_sum)
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
python3 "$REPO/tests/check_hex.py" "$REPO" \
  && ok "no tracked config carries a literal hex" \
  || no "no tracked config carries a literal hex"

# The waybar claude widget's own unit tests (stdlib unittest). Deliberately not
# ok/no-wrapped: a failure here must abort the suite via set -e, not just
# decrement a counter -- claude_usage_test.py already prints its own failures.
python3 "$REPO/tests/claude_usage_test.py" >/dev/null

# Every colour file an application includes must be one a template produces.
# This is the assertion that would have caught a repointing being reverted: the
# include still named `colors.css`, no template produced it any more, and
# nothing failed loudly because sway and GTK treat a missing include as a
# warning rather than an error.
# Every rendered file must be syntactically acceptable to the tool that reads
# it. A banner written in the wrong comment syntax renders fine and fails at
# the consumer: `#` is a comment in most of these formats and in neither JSON
# nor legacy vimscript, and that is how the bar disappeared.
python3 "$REPO/tests/check_syntax.py" "$SANDBOX" \
  && ok "every rendered file parses for its consumer" \
  || no "every rendered file parses for its consumer"

python3 "$REPO/tests/check_includes.py" "$REPO" \
  && ok "every include names a file a template renders" \
  || no "every include names a file a template renders"

# A `;` outside quotes on an exec line runs only the first segment at sway
# startup -- the daemon appears after `swaymsg reload` and never at login, so
# the repo's own reload-based check cannot see it. Asserted across every exec
# line, not just the two that were found broken.
python3 "$REPO/tests/check_sway_exec.py" "$REPO" \
  && ok "no sway exec line splits on an unquoted semicolon" \
  || no "no sway exec line splits on an unquoted semicolon"

# packages.txt / packages-aur.txt are consumed as $(cat file) by pacman, which
# chokes on comments; sorted-unique keeps every diff a one-line change.
for f in packages.txt packages-aur.txt; do
    if LC_ALL=C sort -uc "$REPO/$f" 2>/dev/null && ! grep -qE '^$|[^a-z0-9@._+-]' "$REPO/$f"; then
        ok "$f is a sorted, comment-free package list"
    else
        no "$f is a sorted, comment-free package list"
    fi
done

# The pre-Python `theme` kept per-palette "fragments" (colors-nord.css, theme.env)
# behind symlinks it flipped. §10 kept instructing that scheme long after the
# rewrite — five rows of a troubleshooting table telling the reader to check
# things that no longer exist. Words that can only describe the old mechanism
# are therefore treated as doc bugs, mechanically.
stale=$(grep -nE 'fragment|theme\.env|colors\.conf|symlinks it flipped|(colors|colorscheme|theme)-(nord|gruvbox|\*|\{)' \
    "$REPO/README.md" "$REPO/PLAYBOOK.md" "$REPO/CLAUDE.md" || true)
if [ -z "$stale" ]; then
    ok "docs describe the render scheme, not the retired symlink one"
else
    no "docs describe the render scheme, not the retired symlink one" "$stale"
fi

# Switching is an operational change, never a git one. Asserted against a
# sandbox repo with its own .git -- doing this in $REPO renders into the live
# tree (the packages are symlinked into ~) and overwrites .theme, so the
# "restore" read back the value it had just clobbered and left the user on a
# different palette. Silently.
(
  cd "$SANDBOX"
  git init -q . 2>/dev/null
  git add -A >/dev/null 2>&1
  git -c user.email=t@t -c user.name=t commit -qm init >/dev/null 2>&1
  python3 bin/.local/bin/theme --no-icons gruvbox >/dev/null 2>&1
  before=$(git status --porcelain | sort | md5sum)
  python3 bin/.local/bin/theme --no-icons nord >/dev/null 2>&1
  after=$(git status --porcelain | sort | md5sum)
  [ "$before" = "$after" ]
) && ok "switching leaves git status untouched" \
  || no "switching leaves git status untouched"

printf '\n%s  %d assertions\n\n' "$([ "$fail" -eq 0 ] && echo PASS || echo FAIL)" "$((pass+fail))"
[ "$fail" -eq 0 ]
