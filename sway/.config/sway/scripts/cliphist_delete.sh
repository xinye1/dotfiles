#!/bin/bash

# The cliphist delete picker, tinted $critical so it cannot be mistaken for the
# ordinary copy picker on $mod+Ctrl+v.
#
# Why this is a script and not an inline `bindsym … exec fuzzel …` line, which
# is what it used to be: config.d/* is read ALPHABETICALLY, so `default` is
# parsed before `theme` defines any colour. A sway $variable cannot cross that
# ordering. Reading theme.gen.env here happens at press time instead, which has
# the side benefit that the tint follows a palette switch with no sway reload.
#
# The inline version hardcoded `bf616aff` — Nord's red — so the picker stayed
# Nord-red under gruvbox. It survived for months because tests/check_hex.py only
# looked for a leading '#', and fuzzel's -t/-S want a BARE RRGGBBAA without one.
# Same colour, different spelling, guard blind to it. The check now covers both;
# the `${CRITICAL#\#}ff` below is that bare spelling, derived rather than typed.

# THE FAIL-SAFE, and lock.sh is where its shape comes from: a colour that did
# not survive the render must never decide whether the feature happens.
# theme.gen.env is generated, gitignored and absent on a fresh clone until
# `theme` has run, and the unguarded `.` here read straight through that. With
# CRITICAL unset the tint below was the bare string "ff", fuzzel rejected it,
# and $mod+Ctrl+x did NOTHING AT ALL -- no picker, no message, nothing to tell
# a broken binding apart from an empty clipboard. So the tint is checked and
# dropped if it does not hold up. An untinted delete picker is worse than a red
# one and far better than a keybinding that silently does not work.
#
# Deliberately no `set -eu`: an unset CRITICAL is a case this handles, not a
# reason to abort before the picker opens.
theme_env="$HOME/.config/sway/theme.gen.env"
[ -r "$theme_env" ] && . "$theme_env"

tint="${CRITICAL#\#}ff"
tint_args=()
if [[ $tint =~ ^[0-9a-fA-F]{8}$ ]]; then
    tint_args=(-t "$tint" -S "$tint")
else
    printf 'cliphist_delete: no usable critical colour in %s -- picker runs untinted\n' \
        "$theme_env" >&2
fi

cliphist list \
    | fuzzel -d -w 90 -l 30 "${tint_args[@]}" \
             -p "Select an entry to delete it from cliphist:" \
    | cliphist delete
