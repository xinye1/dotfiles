#!/bin/bash

# Owns the swayidle timeout chain and restarts swayidle whenever AC/battery
# state changes. swayidle itself has no concept of a power source, and
# config.d/* is only read at sway startup/reload, so nothing there can react
# to a plug/unplug live -- the same ordering problem lock.sh solves for
# colours (§9.13), solved here for the timeout chain instead.
#
# On AC: lock only, never auto-suspend -- a machine plugged in and idle is
# not a machine anyone wants asleep on its own.
# On battery: lock AND suspend at the same 300s timeout, since idle screen
# time on battery is exactly what this is for. Which of the two fires first
# does not matter: before-sleep below calls lock.sh -f independently of
# *why* the machine is suspending, so a suspend that somehow beat the lock
# still comes back locked.
#
# AC/online is polled, not watched via udev/acpid: noticing a plug/unplug
# within 15s is more than precise enough for a policy switch nobody is
# timing, against a udev-monitor text parser this repo would have to trust
# to stay stable across systemd releases for something this low-stakes.
# See PLAYBOOK.md §9.26.
#
# A failed read of AC/online defaults to the AC branch (lock, no suspend) --
# the same "when unsure, fail toward the safer state" lock.sh's own
# fail-safes follow (§9.25): losing track of power state must never be the
# reason a machine suspends itself.

AC=/sys/class/power_supply/AC/online
state=""

on_ac() {
    ! [ -r "$AC" ] || [ "$(cat "$AC" 2>/dev/null)" = "1" ]
}

start() {
    pkill -x swayidle
    if [ "$1" = battery ]; then
        swayidle -w idlehint 300 \
            timeout 300 '~/.config/sway/scripts/lock.sh -f' \
            timeout 300 'systemctl suspend' \
            timeout 600 'swaymsg "output * dpms off"' \
                resume 'swaymsg "output * dpms on"' \
            before-sleep '~/.config/sway/scripts/lock.sh -f' &
    else
        swayidle -w idlehint 300 \
            timeout 300 '~/.config/sway/scripts/lock.sh -f' \
            timeout 600 'swaymsg "output * dpms off"' \
                resume 'swaymsg "output * dpms on"' \
            before-sleep '~/.config/sway/scripts/lock.sh -f' &
    fi
}

while :; do
    if on_ac; then new=ac; else new=battery; fi
    [ "$new" = "$state" ] || { start "$new"; state=$new; }
    sleep 15
done
