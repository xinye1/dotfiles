#!/bin/sh
# Launch the applications that read the rendered files, and see whether they
# actually accept them.
#
# Everything else in this suite checks the files from the outside: that they
# were produced, that they parse, that includes resolve. That is not the same
# question. A render was "verified" and the desktop still broke: a `#` banner in
# JSON took waybar down, and nothing outside waybar noticed. The same banner
# went into the vimscript file; that one turned out to be harmless, since `#`
# there parses as `:number` -- but that was learned by asking vim, not by
# reasoning about it, which is the point of this file.
#
# This reads the LIVE config under ~, deliberately: the question is whether the
# desktop as deployed is good, not whether a sandbox render parses.
#
# Note: the waybar check briefly starts a second bar for about a second.

set -u

pass=0; fail=0
ok() { pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
no() { fail=$((fail+1)); printf '  FAIL  %s\n' "$1"; [ $# -lt 2 ] || printf '        %s\n' "$2"; }
have() { command -v "$1" >/dev/null 2>&1; }

printf '\nconsumers\n'

# --- sway ---
if have sway; then
    if out=$(sway --validate -c "$HOME/.config/sway/config" 2>&1); then
        ok "sway accepts its config"
    else
        no "sway accepts its config" "$(printf '%s' "$out" | head -2)"
    fi
fi

# --- foot ---
if have foot; then
    if out=$(foot --check-config 2>&1); then
        ok "foot accepts its config"
    else
        no "foot accepts its config" "$(printf '%s' "$out" | head -2)"
    fi
fi

# --- waybar ---
# No --check-config exists, so it has to be started. The signal is survival:
# a config or style error makes waybar exit at once, a good one keeps it up.
# Grepping its log for 'error' instead catches unrelated tray noise -- an
# iconless tray item made this fail while the config was perfectly fine.
if have waybar; then
    log=$(mktemp)
    waybar >"$log" 2>&1 &
    wb=$!
    sleep 2
    if kill -0 "$wb" 2>/dev/null; then
        kill "$wb" 2>/dev/null
        wait "$wb" 2>/dev/null
        ok "waybar accepts its config and style"
    else
        no "waybar accepts its config and style" \
           "$(grep -m1 -i 'error' "$log" 2>/dev/null | head -1)"
    fi
    rm -f "$log"
fi

# --- vim ---
# Note the limit of this one: vim accepts a stray `#` (it parses as `:number`),
# so this catches real syntax errors but would NOT have caught the wrong-comment
# banner. Only waybar's JSON check catches that class.
if have vim && [ -f "$HOME/.vim/colorscheme.gen.vim" ]; then
    out=$(vim -es -u NONE -c "source $HOME/.vim/colorscheme.gen.vim" -c q 2>&1 | head -5)
    if [ -z "$out" ]; then
        ok "vim sources its colourscheme"
    else
        no "vim sources its colourscheme" "$(printf '%s' "$out" | head -2)"
    fi
fi

# --- neovim ---
if have nvim; then
    out=$(timeout 20 nvim --headless -c q 2>&1 | head -5)
    case $out in
        *[Ee]rror*) no "nvim starts clean" "$(printf '%s' "$out" | head -2)" ;;
        *)          ok "nvim starts clean" ;;
    esac
fi

# --- GTK ---
# No binary validates gtk.css, but an undefined @name renders as black with no
# error, so the one thing worth asserting is that every @name is defined.
for css in "$HOME/.config/gtk-3.0/gtk.css" "$HOME/.config/gtk-4.0/gtk.css"; do
    [ -f "$css" ] || continue
    if python3 - "$css" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
defined = set(re.findall(r'@define-color\s+([\w-]+)', text))
used = set(re.findall(r'@(?!define-color|import)([\w-]+)', text))
missing = sorted(used - defined)
if missing:
    print("undefined:", ", ".join(missing), file=sys.stderr)
sys.exit(1 if missing else 0)
PY
    then ok "every @colour in ${css##*/} is defined"
    else no "every @colour in ${css##*/} is defined"
    fi
done

printf '\n%s  %d consumer checks\n\n' "$([ "$fail" -eq 0 ] && echo PASS || echo FAIL)" "$((pass+fail))"
[ "$fail" -eq 0 ]
