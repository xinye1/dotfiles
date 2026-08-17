#!/bin/sh
# setup.sh — a fresh clone to a stowed desktop, in the documented order.
#
#   ./setup.sh <palette>     first run: render <palette>, then stow everything
#   ./setup.sh               later runs: re-render the remembered palette
#
# This script manages nothing. It is the README quickstart made executable:
# the same mkdir/theme/stow commands, in the one order that works, stopping at
# the first failure instead of leaving a half-linked $HOME. Re-running it is
# always safe. What it cannot do — system packages, GTK themes, vim plugin
# clones, the papirus tint — stays manual: PLAYBOOK.md §4 and §8.

set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for marker in palettes.toml bin/.local/bin/theme .stowrc; do
    [ -e "$REPO/$marker" ] || {
        printf 'setup: %s does not look like the dotfiles repo (no %s).\n' "$REPO" "$marker" >&2
        exit 2
    }
done
cd "$REPO"    # .stowrc (--target=~ --dir=.) is read from here; stow must run from the root

command -v stow >/dev/null || { echo 'setup: GNU Stow is not installed (pacman -S stow)' >&2; exit 1; }
python3 -c 'import tomllib' 2>/dev/null \
    || { echo 'setup: python3 >= 3.11 required (theme needs tomllib)' >&2; exit 1; }

# Missing system packages are a warning, not a stop: stow and theme work
# without them, and a half-provisioned machine still deserves a linked $HOME.
# packages.txt / packages-aur.txt are the canonical lists (PLAYBOOK §4).
if command -v pacman >/dev/null; then
    missing=$(pacman -T $(cat packages.txt) || true)
    [ -z "$missing" ] || printf 'setup: not installed yet (sudo pacman -S --needed $(cat packages.txt)):\n%s\n' "$missing"
    missing=$(pacman -T $(cat packages-aur.txt) || true)
    [ -z "$missing" ] || printf 'setup: not installed yet, from the AUR (yay -S --needed):\n%s\n' "$missing"
fi

# --- palette ----------------------------------------------------------------
# No argument means "whatever is already applied" — theme reads
# $XDG_STATE_HOME/theme/palette. On a fresh machine there is nothing to read,
# so the first run must name one; catch that here with the choices listed,
# rather than three steps in.
PALETTE=${1:-}
if [ -z "$PALETTE" ] && [ ! -f "${XDG_STATE_HOME:-$HOME/.local/state}/theme/palette" ]; then
    printf 'setup: first run needs a palette: ./setup.sh <%s>\n' \
        "$(python3 bin/.local/bin/theme --list | tr '\n' '|' | sed 's/|$//')" >&2
    exit 1
fi

# --- keep the deliberately-unfolded packages unfolded (PLAYBOOK §5.2) -------
# Stow folds any target directory that does not exist yet — it links the whole
# directory into the repo. For these targets that would be a trap sprung later:
# each one accumulates untracked content (installed binaries in ~/.local/bin,
# plugin clones in ~/.vim, Claude Code state in ~/.claude, nwg-look output in
# gtk-{3,4}.0, `ya pkg` installs in ~/.config/yazi), and folded, all of it
# lands inside the repo. On a fresh $HOME none of these directories exist, so
# create them before stow sees them. mkdir -p is a no-op when they already do.
for dir in "$HOME/.local/bin" "$HOME/.vim" "$HOME/.claude" "$HOME/.icons" \
           "$HOME/.config/gtk-3.0" \
           "$HOME/.config/gtk-4.0" "$HOME/.config/yazi"; do
    if [ -L "$dir" ]; then
        printf 'setup: %s is already a symlink — stow folded it on an earlier run.\n' "$dir" >&2
        printf 'setup: unfold it first: stow -D <pkg>; mkdir %s; stow <pkg>  (PLAYBOOK §5.2)\n' "$dir" >&2
        exit 1
    fi
    mkdir -p "$dir"
done

# --- render before stow (PLAYBOOK §3.3) -------------------------------------
# Rendered files do not exist in a fresh clone, and the unfolded packages link
# file-by-file: a file that appears after stow is silently absent until
# `stow -R`. So render first. $PALETTE may be empty — then theme re-applies
# the remembered one.
python3 bin/.local/bin/theme ${PALETTE:+"$PALETTE"}

# --- stow everything --------------------------------------------------------
# Every top-level directory is a package except docs/ and tests/ — derived
# here rather than listed, so a new package cannot be forgotten.
pkgs=''
for d in */; do
    case ${d%/} in docs|tests) ;; *) pkgs="$pkgs ${d%/}" ;; esac
done

# ~/.bashrc exists from /etc/skel on any fresh Arch, and stow refuses to
# replace a real file. Move it aside once; when it is already our symlink
# there is nothing to do.
if [ -e "$HOME/.bashrc" ] && [ ! -L "$HOME/.bashrc" ]; then
    [ -e "$HOME/.bashrc.bak" ] && {
        echo 'setup: both ~/.bashrc and ~/.bashrc.bak exist; resolve by hand first' >&2
        exit 1
    }
    mv "$HOME/.bashrc" "$HOME/.bashrc.bak"
    echo '  moved ~/.bashrc -> ~/.bashrc.bak'
fi

# Dry run first: stow refuses to overwrite real files, and on a stock
# EndeavourOS Sway install ~/.config/sway, waybar, foot etc. ARE real files.
# Surface every conflict before linking anything, so a failure never leaves
# half the packages stowed.
if ! out=$(stow -n $pkgs 2>&1); then
    printf '%s\n' "$out" >&2
    cat >&2 <<'EOF'
setup: stow found existing files in the way (list above). For a stock config
setup: you are replacing, move the directory aside and re-run, e.g.:
setup:     mv ~/.config/sway ~/.config/sway.stock
setup: To keep local changes instead, adopt them first — PLAYBOOK §5.3.
EOF
    exit 1
fi
stow $pkgs
printf '  stowed:%s\n' "$pkgs"

# --- verify -----------------------------------------------------------------
sh tests/theme_test.sh

cat <<'EOF'
setup: done. Still manual, and needed once per machine (PLAYBOOK §4, §8):
setup:   - system packages           §4.1/§4.2 (pacman + AUR)
setup:   - GTK themes                nordic-theme (AUR), Colloid-…-Gruvbox (§8)
setup:   - vim plugins               three git clones (§8)
setup:   - papirus folder tint       sudo papirus-folders … (§8), or just `theme`
setup: When the desktop is up: sh tests/check_consumers.sh
EOF
