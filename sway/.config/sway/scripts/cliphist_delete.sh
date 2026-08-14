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

. "$HOME/.config/sway/theme.gen.env"

tint="${CRITICAL#\#}ff"

cliphist list \
    | fuzzel -d -w 90 -l 30 -t "$tint" -S "$tint" \
             -p "Select an entry to delete it from cliphist:" \
    | cliphist delete
