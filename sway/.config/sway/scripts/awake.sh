#!/bin/bash
#
# Keep awake: hold the screen on and unlocked for a while, then hand back to
# the normal idle policy by itself. Three callers: waybar's custom/awake
# (click = toggle, right-click = pick), and System > Keep awake in the palette.
#
#   awake.sh on [time]    from now for <time>; default DEFAULT minutes
#   awake.sh off          end it now
#   awake.sh toggle       off if on, else `on`
#   awake.sh pick         fuzzel: a listed time, a typed one, or stop
#   awake.sh status       one line of JSON for waybar
#
# A time is bare minutes or a number with m/min/h/hour(s): 45, 90m, 3h, 2 hours.
#
# This only writes a deadline (epoch seconds) and pokes idle.sh, which is the
# one owner of the idle policy and the only thing that acts on it (§9.26).
# Not waybar's built-in idle_inhibitor: that holds a Wayland inhibitor inside
# the waybar process, so it cannot take a time picked at click time and ends
# whenever waybar crashes, which it does (§9.29). Never a logind `idle`
# inhibitor either: swayidle would then arm no timeout at all, ever (§9.26).
#
# While it holds, lid close and a manual suspend behave exactly as without it,
# and both still come back locked. The file is "<deadline> <$SWAYSOCK>", and
# only the sway named there honours it: the user lingers, so $XDG_RUNTIME_DIR
# survives a logout, and a bare deadline would carry into the next login and
# keep it from locking. A reboot wipes it either way.
#
# IDLE_AWAKE_FILE exists for tests/idle_test.sh only.

set -u

FILE=${IDLE_AWAKE_FILE:-${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/idle-awake-until}
DEFAULT=120   # minutes
MAX=1440      # a day; anything longer is a policy change, not an override
SIGNAL=11     # waybar custom/awake's "signal"
STOP='Stop keeping awake'

remaining() {   # seconds left in this session, or fail when it is off
    local until key left
    read -r until key 2>/dev/null <"$FILE" || return 1
    [[ $until =~ ^[0-9]{1,12}$ ]] && [ -n "$key" ] && [ "$key" = "${SWAYSOCK:-}" ] || return 1
    left=$(( until - $(date +%s) ))
    [ "$left" -gt 0 ] || return 1
    echo "$left"
}

minutes() {     # a time as above -> minutes in 1..MAX, or fail
    local s=${1,,} n
    s=${s// /}
    [[ $s =~ ^([0-9]{1,5})(m|min|mins|minute|minutes|h|hr|hrs|hour|hours)?$ ]] || return 1
    n=$((10#${BASH_REMATCH[1]}))
    [[ ${BASH_REMATCH[2]} == h* ]] && n=$((n * 60))
    [ "$n" -ge 1 ] && [ "$n" -le "$MAX" ] || return 1
    echo "$n"
}

human() {       # seconds -> "1h 30m" / "45m", rounded up to the minute
    local m=$(( ($1 + 59) / 60 ))
    if [ "$m" -ge 60 ]; then printf '%dh %02dm' $((m / 60)) $((m % 60)); else printf '%dm' "$m"; fi
}

poke() {        # never fatal: idle.sh's 15s poll catches up, the bar's interval too
    pkill -USR1 -x idle.sh 2>/dev/null
    pkill -RTMIN+$SIGNAL -x waybar 2>/dev/null
    return 0
}

on() {
    local m
    [ -n "${SWAYSOCK:-}" ] || {
        echo "awake: not inside a sway session (no \$SWAYSOCK)" >&2
        return 2
    }
    m=$(minutes "${1:-$DEFAULT}") || {
        echo "awake: not a time of 1 minute to $((MAX / 60)) hours: ${1:-}" >&2
        return 2
    }
    mkdir -p "$(dirname "$FILE")" &&
        printf '%s %s\n' $(( $(date +%s) + m * 60 )) "$SWAYSOCK" >"$FILE.tmp" &&
        mv -f "$FILE.tmp" "$FILE" || return 1
    poke
}

off() {
    rm -f "$FILE"
    poke
}

pick() {
    local rows choice
    rows=$'30 min\n1 hour\n2 hours\n4 hours\n8 hours'
    remaining >/dev/null && rows="$STOP"$'\n'"$rows"
    # Esc is a non-zero exit with nothing printed: not an error here.
    choice=$(printf '%s\n' "$rows" | fuzzel -d -p 'Keep awake for (or type e.g. 45m): ') || return 0
    [ -n "$choice" ] || return 0
    if [ "$choice" = "$STOP" ]; then
        off
    elif ! on "$choice" 2>/dev/null; then
        notify-send -a awake "Keep awake" "Not a time: $choice (1 minute to $((MAX / 60)) hours)"
    fi
    return 0
}

status() {
    local left
    if left=$(remaining); then
        printf '{"text":"","alt":"activated","class":"activated","tooltip":"%s"}\n' \
            "Screen stays on and unlocked: $(human "$left") left\\nClick: stop · Right-click: pick a time"
    else
        printf '{"text":"","alt":"deactivated","class":"deactivated","tooltip":"%s"}\n' \
            "Click: keep the screen on and unlocked for $(human $((DEFAULT * 60)))\\nRight-click: pick a time"
    fi
}

case ${1:-} in
    on)     shift; on "$@" ;;
    off)    off ;;
    toggle) if remaining >/dev/null; then off; else on; fi ;;
    pick)   pick ;;
    status) status ;;
    *)      echo "usage: awake.sh on [time] | off | toggle | pick | status" >&2; exit 2 ;;
esac
