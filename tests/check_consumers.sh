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

# --- mako ---
# mako has no --check-config, but it parses its config (and everything the
# config includes) BEFORE it tries to take the D-Bus name, and a parse failure
# is reported distinctly from the name clash. So starting a second mako against
# the live config is a real check: the running daemon keeps the name, the
# second one exits immediately, and what it printed on the way out is the
# answer. Grepping for the parse error rather than the exit code is the point —
# the exit code is dominated by the expected name clash.
#
# This is the check that would have noticed a bad {{role}} reaching colors.gen,
# or a criteria mako no longer accepts, neither of which is visible from
# outside the file.
if have mako; then
    out=$(timeout 5 mako --config "$HOME/.config/mako/config" 2>&1)
    case $out in
        *"Failed to parse"*|*"Invalid "*|*"Unable to open"*)
            no "mako accepts its config" "$(printf '%s' "$out" | head -2)" ;;
        *)  ok "mako accepts its config" ;;
    esac
fi

# --- tmux ---
# tmux has no --check-config, but starting a server on a PRIVATE socket against
# the live config is equivalent and cannot disturb a running session: `-L` names
# a socket nothing else uses, so this is a second server, not a second client.
#
# Then a second, sharper question. The status bar reaches its colours through
# `@thm_*` user options that colors.gen.conf defines, and tmux does not care
# whether they exist: an undefined one expands to nothing, `#[fg=#{@thm_accent}]`
# becomes `#[fg=]`, and the bar renders in the default colours with no error at
# all -- the same silent-failure shape as GTK's undefined `@name`. Expanding the
# three format strings and looking for an empty `fg=` is what catches a role
# that was added to tmux.conf but not to the template.
#
# What this does NOT catch: a status-format whose `align=` groups are wrong.
# tmux accepts that silently too, and the only way to see it is to attach a
# client and look at the bar. See the note on `list=on` in tmux.conf.
if have tmux; then
    sock=dotfiles-check-$$
    out=$(tmux -L "$sock" -f "$HOME/.config/tmux/tmux.conf" \
              new-session -d -s check 2>&1)
    if [ -n "$out" ]; then
        no "tmux accepts its config" "$(printf '%s' "$out" | head -2)"
    else
        fmt=$(tmux -L "$sock" display-message -p \
              '#{E:status-format[0]}#{E:status-left}#{E:status-right}' 2>&1)
        case $fmt in
            *"fg=]"*|*"fg= "*|*"bg=]"*)
                no "tmux resolves every colour role" \
                   "an empty fg=/bg= means colors.gen.conf is missing a @thm_ role" ;;
            *)  ok "tmux accepts its config and resolves every colour" ;;
        esac
    fi
    tmux -L "$sock" kill-server 2>/dev/null
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
