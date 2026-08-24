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

pass=0; fail=0; skip=0
ok() { pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
no() { fail=$((fail+1)); printf '  FAIL  %s\n' "$1"; [ $# -lt 2 ] || printf '        %s\n' "$2"; }
# A check that cannot run says so out loud rather than going quiet, so a green
# run never means "it passed" when it meant "it never looked".
sk() { skip=$((skip+1)); printf '  skip  %s\n' "$1"; [ $# -lt 2 ] || printf '        %s\n' "$2"; }
have() { command -v "$1" >/dev/null 2>&1; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=${here%/tests}

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

# --- kitty ---
# kitty 0.48 has no --debug-config, but its config parser is importable and
# `kitty +runpy` runs a snippet against it without opening a window or needing
# a display. load_config() follows the `include`, so this checks the rendered
# colours too.
#
# Two failures, not one, and only the first is loud: a bad *value* raises, but
# an unknown *key* is only logged as "Ignoring unknown config key" and kitty
# starts perfectly happily with the option silently absent. That is the same
# shape as GTK's undefined @name and tmux's empty fg=, so it is checked the
# same way — by looking at what the parser said, not at the exit code alone.
if have kitty; then
    out=$(timeout 20 kitty +runpy \
              'from kitty.config import load_config; load_config("'"$HOME"'/.config/kitty/kitty.conf")' 2>&1)
    rc=$?
    if [ "$rc" -ne 0 ]; then
        no "kitty accepts its config" "$(printf '%s' "$out" | tail -2)"
    else
        case $out in
            *"Ignoring unknown config key"*)
                no "kitty accepts every key in its config" \
                   "$(printf '%s' "$out" | grep -m1 'Ignoring unknown')" ;;
            *)  ok "kitty accepts its config and every key in it" ;;
        esac
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

# --- waybar paint ---
# Surviving startup is not the same as looking right. waybar's state classes are
# bare GTK style classes, so `warning` collides with GtkInfoBar's stock one --
# which the Nordic theme styles unscoped, painting an orange infobar fill behind
# any module in a warning state. waybar started perfectly happily either way.
#
# check_waybar_paint.py renders each module offscreen under every GTK theme
# palettes.toml names, so it answers for the palette that is NOT switched on
# too; that is the whole point, since this bug shipped green under gruvbox and
# only appeared on the switch to nord months later.
#
# Only python3 is guarded here, and nothing else is. Every other block in this
# file goes silent when its tool is absent, which is right for them -- no foot
# means nothing about foot to check. This one is the opposite: the subject is
# still there, only the instrument is missing, and going quiet about that is
# how a green run comes to mean "never looked". check_waybar_paint.py already
# reports its own missing pieces -- no stylesheet, no bindings, no display, no
# installed GTK theme -- as exit 77, with the reason on stderr. Re-testing any
# of those here would just be a second, wordless copy that swallows the answer
# the script was about to give.
if have python3; then
    out=$(python3 "$here/check_waybar_paint.py" "$repo" \
              "$HOME/.config/waybar/style.css" \
              "$HOME/.config/waybar/config" 2>&1)
    case $? in
        0)  ok "no waybar module inherits paint from the GTK theme ($(printf '%s' "$out" | tail -1))" ;;
        77) sk "no waybar module inherits paint from the GTK theme" \
               "$(printf '%s' "$out" | head -1)" ;;
        *)  no "no waybar module inherits paint from the GTK theme" \
               "$(printf '%s' "$out" | head -1)" ;;
    esac
else
    sk "no waybar module inherits paint from the GTK theme" \
       "no python3 — the check could not run at all"
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
            *"fg=]"*|*"fg= "*|*"bg=]"*|*"bg= "*)
                no "tmux resolves every colour role" \
                   "an empty fg=/bg= means colors.gen.conf is missing a @thm_ role" ;;
            *)  ok "tmux accepts its config and resolves every colour" ;;
        esac
    fi
    tmux -L "$sock" kill-server 2>/dev/null
fi

# --- yazi ---
# `yazi --debug` is a real validator, and a better one than most consumers here
# have: it parses init.lua, yazi.toml, keymap.toml and theme.toml and exits 1
# with the offending line and a caret under the token. Measured against a
# scratch $YAZI_CONFIG_HOME, it rejects malformed TOML, an unknown [section],
# a bad hex (`Failed to parse Colors`) and an empty value.
#
# `</dev/null` is not decoration. On a parse failure yazi prints "Press <Enter>
# to continue with preset settings..." and WAITS -- interactively it then starts
# in preset colours, which is the degradation this check exists to notice.
# Closing stdin turns that prompt into the non-zero exit.
#
# What --debug does NOT catch, and the reason theme.toml.tmpl carries a header
# about where its keys came from: an unknown KEY inside a known section is
# ignored in silence, with no warning even here. Same shape as an undefined GTK
# @name or an empty tmux `fg=`.
#
# Hence the second assertion, which is the sharper one. yazi exits 0 with no
# theme.toml at all, quietly using its preset colours -- exactly what a fresh
# clone that has not run `theme`, or an unfolded `yazi` package that has not
# been `stow -R`'d after a new file, would produce. The debug output names each
# config path and either its size or the errno, so asking whether the theme
# actually loaded is a question with a real answer.
if have yazi; then
    if out=$(timeout 20 yazi --debug </dev/null 2>&1); then
        # Captured, not piped straight into `case`. An absent line used to fall
        # through the empty result to `*)` -> ok, so the sharper of the two
        # assertions -- the one that catches yazi sitting quietly on preset
        # colours -- would have gone green forever the day a yazi release
        # renamed or reformatted its `Theme :` row. A check that can no longer
        # see its subject reports that, rather than success.
        themeline=$(printf '%s\n' "$out" | grep -E '^ +Theme +:' || true)
        case "$themeline" in
            "") no "yazi loaded its rendered theme" \
                   "no 'Theme :' row in \`yazi --debug\` output — this check can no longer see whether the theme loaded; re-derive it from the current output" ;;
            *"No such file"*|*error*)
                no "yazi loaded its rendered theme" \
                   "yazi is running on PRESET colours: run \`theme\`, then \`stow -R yazi\`" ;;
            *)  ok "yazi accepts its config and loaded its rendered theme" ;;
        esac
    else
        no "yazi accepts its config" \
           "$(printf '%s\n' "$out" | grep -v '^ *$' | tail -3 | head -2)"
    fi
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
#
# Both files are called gtk.css, so the label carries the parent directory too:
# `${css##*/}` alone printed "gtk.css" twice and a failure did not say which of
# the two was broken.
for css in "$HOME/.config/gtk-3.0/gtk.css" "$HOME/.config/gtk-4.0/gtk.css"; do
    [ -f "$css" ] || continue
    dir=${css%/*}
    label=${dir##*/}/${css##*/}
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
    then ok "every @colour in $label is defined"
    else no "every @colour in $label is defined"
    fi
done

printf '\n%s  %d consumer checks%s\n\n' \
    "$([ "$fail" -eq 0 ] && echo PASS || echo FAIL)" "$((pass+fail))" \
    "$([ "$skip" -eq 0 ] || printf ', %d skipped' "$skip")"
[ "$fail" -eq 0 ]
