#!/bin/bash

# The lock screen. Four callers: $mod+f1 (config.d/default), the 300s idle
# timeout and before-sleep (config.d/autostart_applications, both passing -f),
# and the power menu's Lock entry. Plain swaylock over a solid $desktop
# background -- no clock, no power buttons, no avatar. §4.3 records what
# replacing gtklock cost and why it was paid.
#
# Why a script and not an inline `bindsym ... exec swaylock ...`: config.d/* is
# read ALPHABETICALLY, so `default` is parsed before `theme` defines any colour,
# and a sway $variable cannot cross that ordering (§9.13). Reading theme.gen.env
# here happens at lock time instead, which has the side benefit that the lock
# screen follows a palette switch with no sway reload.
#
# Why every colour is derived rather than typed: swaylock's colour flags take a
# BARE rrggbb, with no leading '#'. tests/check_hex.py was blind to that spelling
# for months while a hardcoded Nord red sat in a sway binding -- same colour,
# different spelling, guard blind to it. The check covers both now, and the
# ${ROLE#\#} below is that bare spelling, derived rather than typed.
#
# Nothing here authenticates. /etc/pam.d/swaylock is `auth include system-login`,
# so the prompt takes the ordinary account password; this script neither sets,
# stores nor checks one, and there is no password anywhere in this repo.

# Deliberately no `set -eu`. An abort anywhere before the exec below leaves the
# session UNLOCKED, which is the one failure this script must never have. Every
# path out of here ends in an exec of swaylock.
if [ -r "$HOME/.config/sway/theme.gen.env" ]; then
    . "$HOME/.config/sway/theme.gen.env"
fi

color_bg=${BG#\#}
color_surface=${SURFACE#\#}
color_fg=${FG#\#}
color_fg_bright=${FG_BRIGHT#\#}
color_accent=${ACCENT#\#}
color_indicator=${INDICATOR#\#}
color_critical=${CRITICAL#\#}
color_warning=${WARNING#\#}
color_success=${SUCCESS#\#}
color_desktop=${DESKTOP#\#}

# THE FAIL-SAFE, and the reason this script is shaped the way it is. A missing
# theme.gen.env (fresh clone, before `theme` has rendered) or a half-written one
# leaves a role empty or malformed, and swaylock exits with a usage error on a
# bad colour -- which would mean the screen never locked. So if ANY colour is not
# six hex digits, throw the whole set away and lock with swaylock's own defaults.
# An ugly lock screen beats an unlocked one; a missing theme file must never
# leave the session open.
for c in "$color_bg" "$color_surface" "$color_fg" "$color_fg_bright" \
         "$color_accent" "$color_indicator" "$color_critical" \
         "$color_warning" "$color_success" "$color_desktop"; do
    [[ $c =~ ^[0-9a-fA-F]{6}$ ]] || exec swaylock "$@"
done

# "$@" is passed through, and comes last so a caller's flag wins over these
# defaults. swayidle must pass -f (daemonize) or swaylock holds the timeout
# chain open -- gtklock spelled the same thing -d, which swaylock reads as
# --debug, so the rename is not a search-and-replace.
#
# --indicator-caps-lock puts caps-lock state on the ring: without it a stuck
# Caps Lock reads as a wrong password. Its caps-lock colours are set from the
# roles too, or the indicator would flip to swaylock's stock green mid-lock.
exec swaylock \
    --color                   "$color_desktop" \
    --inside-color            "$color_bg" \
    --inside-clear-color      "$color_bg" \
    --inside-ver-color        "$color_bg" \
    --inside-wrong-color      "$color_bg" \
    --inside-caps-lock-color  "$color_bg" \
    --ring-color              "$color_accent" \
    --ring-clear-color        "$color_success" \
    --ring-ver-color          "$color_indicator" \
    --ring-wrong-color        "$color_critical" \
    --ring-caps-lock-color    "$color_warning" \
    --key-hl-color            "$color_success" \
    --caps-lock-key-hl-color  "$color_success" \
    --bs-hl-color             "$color_warning" \
    --caps-lock-bs-hl-color   "$color_warning" \
    --line-color              "$color_desktop" \
    --line-caps-lock-color    "$color_desktop" \
    --separator-color         "$color_desktop" \
    --text-color              "$color_fg_bright" \
    --text-clear-color        "$color_fg_bright" \
    --text-ver-color          "$color_fg_bright" \
    --text-wrong-color        "$color_fg_bright" \
    --text-caps-lock-color    "$color_warning" \
    --layout-bg-color         "$color_surface" \
    --layout-border-color     "$color_accent" \
    --layout-text-color       "$color_fg" \
    --indicator-caps-lock \
    --show-failed-attempts \
    --ignore-empty-password \
    --indicator-radius 100 \
    --indicator-thickness 8 \
    --font "JetBrainsMono Nerd Font" \
    "$@"
