#!/bin/bash
#
# Lid closed (config.d/input's `bindswitch lid:on`): the panel goes off, and the
# session locks unless another display is still on.
#
# The lock is the fix. On AC inhibit-sleep-on-ac.service holds logind's
# `handle-lid-switch`, so logind does nothing with the lid and nothing else
# locks: a closed laptop on AC used to sit unlocked until the 300s idle lock.
# On battery logind suspends and swayidle's before-sleep locks anyway; locking
# here first costs nothing.
#
# Not when another display is active: lid shut at a desk means the session is
# in use on that screen. Anything that cannot answer that question -- sway
# unreachable, no JSON -- locks: fail toward locking, like lock.sh (§9.25).
# Already locked (--locked fires under swaylock too): no second swaylock.
#
# LID_LOCK exists for tests/idle_test.sh only.

PANEL=eDP-1
LOCK=${LID_LOCK:-$HOME/.config/sway/scripts/lock.sh}

others=$(swaymsg -t get_outputs 2>/dev/null |
    jq --arg p "$PANEL" '[.[] | select(.active and .name != $p)] | length' 2>/dev/null)

swaymsg output "$PANEL" disable >/dev/null 2>&1

[ "$others" -gt 0 ] 2>/dev/null && exit 0
pgrep -x swaylock >/dev/null 2>&1 && exit 0
exec "$LOCK" -f
