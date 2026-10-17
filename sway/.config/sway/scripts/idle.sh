#!/bin/bash

# ---------------------------------------------------------------------------
# THE POWER POLICY -- edit these, then `swaymsg reload` to apply.
#
# Seconds of no input before each step. 0 means "never". The steps are
# independent: each counts from the last input, not from the step before it.
#
#                    plugged in       on battery
AC_SCREEN_OFF=180;   BAT_SCREEN_OFF=60
AC_LOCK=300;         BAT_LOCK=120
AC_SLEEP=0;          BAT_SLEEP=900
#
# power-profiles-daemon profile -- `powerprofilesctl list` shows the choices.
# On this Dell `performance` drives both the firmware platform profile (fan
# and thermal limits) and intel_pstate's energy preference; empty leaves the
# profile alone.
AC_PROFILE=performance; BAT_PROFILE=balanced
#
# Sleep is a plain suspend. There is no hibernation, by decision (2026-10-17):
# it needs swap the size of RAM on a disk that is 88% full.
#
# On AC, sleep is also blocked outright by inhibit-sleep-on-ac.service, so
# AC_SLEEP stays 0: a nonzero value would only make swayidle ask and be told no.
#
# Keep-awake (awake.sh: the bar's eye, or System > Keep awake in the palette)
# drops all three steps on either source until its deadline, then this policy
# comes back by itself. Its default length lives in awake.sh.
# ---------------------------------------------------------------------------

# Owns the swayidle timeout chain and the power profile, and reapplies both
# whenever AC/battery state changes. swayidle itself has no concept of a power
# source, and config.d/* is only read at sway startup/reload, so nothing there
# can react to a plug/unplug live -- the same ordering problem lock.sh solves
# for colours (§9.13), solved here for the power policy instead.
#
# before-sleep calls lock.sh -f independently of *why* the machine is
# suspending, so a sleep that beat the lock step, or a lid close, still comes
# back locked.
#
# No `idlehint`: it reported the session idle to logind, which feeds logind's
# own IdleAction. That made two owners of one policy -- a logind IdleAction on
# this machine would start its own suspend clock and race the one here. The
# policy is this file's alone.
#
# AC/online is polled, not watched via udev/acpid: noticing a plug/unplug
# within 15s is more than precise enough for a policy switch nobody is
# timing, against a udev-monitor text parser this repo would have to trust
# to stay stable across systemd releases for something this low-stakes.
#
# A failed read of AC/online defaults to the AC branch -- the same "when
# unsure, fail toward the safer state" lock.sh's own fail-safes follow
# (§9.25): losing track of power state must never be the reason a machine
# suspends itself.
#
# The name predates the power profile; it stays idle.sh because §9.2's
# pkill-by-name and tests/check_sway_exec.py both key on it.
#
# Keep-awake is a deadline, not a Wayland idle inhibitor held by some client:
# awake.sh writes it, this loop alone acts on it, so the policy keeps one
# owner and a waybar crash cannot end it. While it holds, swayidle runs with no
# timeouts but keeps before-sleep, so a lid close or a manual suspend still
# comes back locked. The deadline names the sway that set it ($SWAYSOCK, which
# carries sway's pid and survives a reload): $XDG_RUNTIME_DIR outlives a logout
# here, because the user lingers, so without that a deadline would carry into
# the next login and keep it from ever locking. One that has passed, does not
# parse or names another session is deleted and counts as off -- fail toward
# locking, as above.
#
# IDLE_AC_ONLINE, IDLE_POLL and IDLE_AWAKE_FILE exist for tests/idle_test.sh only.

AC=${IDLE_AC_ONLINE:-/sys/class/power_supply/AC/online}
POLL=${IDLE_POLL:-15}
AWAKE=${IDLE_AWAKE_FILE:-${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/idle-awake-until}
# The ~ is for swayidle, which runs each command through sh -c.
# shellcheck disable=SC2088
LOCK='~/.config/sway/scripts/lock.sh -f'
state=""
power=""

# awake.sh sends USR1 after it changes the deadline. The trap only has to
# exist: it ends the `wait` below early, so the loop re-reads at once. Set
# before the first swayidle starts -- USR1's default action is to exit.
trap : USR1

on_ac() {
    [ "$(cat "$AC" 2>/dev/null)" != "0" ]
}

awake() {
    local until key
    read -r until key 2>/dev/null <"$AWAKE" || return 1
    [[ $until =~ ^[0-9]{1,12}$ ]] && [ -n "$key" ] && [ "$key" = "${SWAYSOCK:-}" ] &&
        [ "$until" -gt "$(date +%s)" ] && return 0
    rm -f "$AWAKE"
    return 1
}

# start <ac|battery> <normal|awake>
start() {
    local screen_off lock sleep_after profile args=()
    if [ "$1" = battery ]; then
        screen_off=$BAT_SCREEN_OFF lock=$BAT_LOCK sleep_after=$BAT_SLEEP profile=$BAT_PROFILE
    else
        screen_off=$AC_SCREEN_OFF lock=$AC_LOCK sleep_after=$AC_SLEEP profile=$AC_PROFILE
    fi
    if [ "$2" = normal ]; then
        [ "$screen_off" -gt 0 ] && args+=(timeout "$screen_off" 'swaymsg "output * dpms off"'
                                          resume 'swaymsg "output * dpms on"')
        [ "$lock" -gt 0 ] && args+=(timeout "$lock" "$LOCK")
        [ "$sleep_after" -gt 0 ] && args+=(timeout "$sleep_after" 'systemctl suspend')
    fi
    pkill -x swayidle
    swayidle -w "${args[@]}" before-sleep "$LOCK" &
    # After swayidle, and never fatal: a missing daemon or a refused switch
    # must not cost the lock. Only when the power source changes (or at
    # start), so a profile picked by hand holds until the next plug/unplug or
    # sway reload -- switching keep-awake does not reset it.
    [ "$1" != "$power" ] && [ -n "$profile" ] && powerprofilesctl set "$profile" 2>/dev/null
}

while :; do
    if on_ac; then new=ac; else new=battery; fi
    if awake; then mode=awake; else mode=normal; fi
    [ "$new:$mode" = "$state" ] || { start "$new" "$mode"; state=$new:$mode; power=$new; }
    sleep "$POLL" &
    wait $!
    kill $! 2>/dev/null   # a USR1 ends the wait, not the sleep
done
