#!/usr/bin/env bash
#
# Network module for the vertical bar: icon / download / upload, stacked like
# the clock, every value at most 4 characters ("0", "999", "9.9k", "999k").
#
# Waybar's built-in `network` module can't be squeezed this far: its bandwidth
# formatter is hard-coded to "{:.1f}{prefix}{unit}" (e.g. "12.3Mb/s"), roughly
# twice the width of the date below it, and the format spec is ignored. So the
# counters are read straight from /sys and formatted here instead.
#
# Values are bits/s, matching what the built-in module reported. The unit is
# dropped from the bar to save width and spelled out in the tooltip.

set -uo pipefail

# One sample of counters, to diff against the next one. $XDG_RUNTIME_DIR is a
# private 0700 tmpfs and the right home for it; the fallback is ~/.cache and
# NOT /tmp, which is world-writable, so a predictable name there is a symlink
# anyone on the box can plant for the `>` below to follow. Stale state after a
# reboot is already handled -- the uptime and counter deltas both go negative
# and the sample is discarded -- so an on-disk fallback costs nothing.
state_dir=${XDG_RUNTIME_DIR:-}
if [[ -z $state_dir ]]; then
    state_dir=${XDG_CACHE_HOME:-$HOME/.cache}
    mkdir -p "$state_dir" 2>/dev/null
fi
state="$state_dir/waybar-netspeed.state"

icon_wifi=$'\uf1eb'         # nf-fa-wifi
icon_ethernet=$'\U000f0200'  # nf-md-ethernet
icon_down=$'\uf071'         # nf-fa-warning

# Waybar wants one JSON object per run. Every field is escaped here, and the
# callers below pass REAL newlines rather than a hand-written \n, so this is
# the only place that knows anything about JSON syntax.
#
# Order matters and is not negotiable: the backslash rule runs FIRST, or it
# would go back over the backslashes the quote and control-character rules
# just added and double them. Only `"` used to be escaped, and only in the
# tooltip -- an SSID like `C:\Users net` (a real thing people name a hotspot)
# put a lone backslash into the JSON and waybar dropped the whole module as
# malformed.
#
# JSON forbids a literal control character (U+0000-U+001F) anywhere in a
# string, not just newline -- an SSID is arbitrary octets, so a tab, a bell, an
# escape byte, anything in that range can show up and a parser rejects the
# whole payload over it ("Invalid control character"). The five named escapes
# below cover what JSON has a shorthand for; the loop after them sweeps the
# rest of the range one code point at a time into \u00XX. 0x00 itself needs no
# case: a NUL byte can't survive into a bash string to begin with.
json_escape() {
    local s=$1 i h raw esc
    s=${s//\\/\\\\}
    s=${s//\"/\\\"}
    s=${s//$'\b'/\\b}
    s=${s//$'\t'/\\t}
    s=${s//$'\n'/\\n}
    s=${s//$'\f'/\\f}
    s=${s//$'\r'/\\r}
    for ((i = 1; i <= 0x1f; i++)); do
        case $i in 8|9|10|12|13) continue ;; esac  # already named above
        printf -v h '%02x' "$i"
        printf -v raw "\\x$h"
        esc="\\u00$h"
        s=${s//$raw/$esc}
    done
    printf '%s' "$s"
}

emit() {
    printf '{"text":"%s","tooltip":"%s","class":"%s"}\n' \
        "$(json_escape "$1")" "$(json_escape "$2")" "$(json_escape "$3")"
}

iface=$(ip route show default 2>/dev/null | awk '{print $5; exit}')

if [[ -z $iface ]]; then
    rm -f "$state"
    emit "$icon_down" "No default route" "disconnected"
    exit 0
fi

read -r uptime _ < /proc/uptime  # monotonic, unlike date(1)
rx=$(< "/sys/class/net/$iface/statistics/rx_bytes")
tx=$(< "/sys/class/net/$iface/statistics/tx_bytes")

prev_iface="" prev_uptime=0 prev_rx=0 prev_tx=0
[[ -r $state ]] && read -r prev_iface prev_uptime prev_rx prev_tx < "$state"
printf '%s %s %s %s\n' "$iface" "$uptime" "$rx" "$tx" > "$state"

# Counters restart on reboot or when the route moves to another interface;
# a negative delta means this sample has nothing to compare against.
IFS=$'\t' read -r short_rx short_tx long_rx long_tx < <(
    awk -v pif="$prev_iface" -v cif="$iface" \
        -v pt="$prev_uptime" -v ct="$uptime" \
        -v prx="$prev_rx" -v crx="$rx" -v ptx="$prev_tx" -v ctx="$tx" '
    function scale(v,   i) {
        # 999.5 rather than 1000 so the value never rounds up to 5 characters
        for (i = 0; v >= 999.5 && i < 4; i++) v /= 1000
        return sprintf("%.*f\t%s", (i && v < 10) ? 1 : 0, v, substr("kMGT", i, i ? 1 : 0))
    }
    function short(v,   p) { split(scale(v), p, "\t"); return p[1] p[2] }
    function long(v,    p) { split(scale(v), p, "\t"); return p[1] " " p[2] "b/s" }
    BEGIN {
        dt = ct - pt
        if (pif != cif || dt <= 0 || crx < prx || ctx < ptx) dt = 0
        drx = dt ? (crx - prx) * 8 / dt : 0
        dtx = dt ? (ctx - ptx) * 8 / dt : 0
        printf "%s\t%s\t%s\t%s\n", short(drx), short(dtx), long(drx), long(dtx)
    }'
)

ip_addr=$(ip -4 addr show dev "$iface" 2>/dev/null | awk '/inet /{print $2; exit}')

if [[ -d /sys/class/net/$iface/wireless ]]; then
    icon=$icon_wifi
    essid=$(iw dev "$iface" link 2>/dev/null | awk -F': ' '/SSID/{print $2; exit}')
    header="${essid:-$iface} (${ip_addr:-no address})"
    class=wifi
else
    icon=$icon_ethernet
    header="$iface (${ip_addr:-no address})"
    class=ethernet
fi

emit "$icon"$'\n'"$short_rx"$'\n'"$short_tx" \
     "$header"$'\n'"Down $long_rx"$'\n'"Up   $long_tx" \
     "$class"
