#!/bin/bash
#
# Direct interpreter path, not `#!/usr/bin/env bash`: the latter makes the
# kernel exec `env`, which then execs bash itself in a SEPARATE execve --
# comm becomes "bash", not this script's name, and `pkill -x waybar_run.sh`
# in autostart_applications silently matches nothing. Confirmed against the
# live process (`/proc/<pid>/comm`) before landing on this; idle.sh uses the
# same direct form for the same reason.
#
# Launched from config.d/autostart_applications via exec_always, NOT from a
# `bar { swaybar_command ... }` block. waybar crashes intermittently (SIGABRT
# via an uncaught C++ exception in a background thread -- `coredumpctl list`
# showed 5 hits across 2026-09-01..13, none correlated with output hotplug,
# suspend/resume or lock events, so it looks like an internal waybar race
# rather than anything in this repo's own custom-module scripts, which
# already guard their JSON output). Sway does not respawn a bar_command that
# exits on its own, so a crash used to leave the bar gone until the next
# `swaymsg reload` ($mod+Shift+c) -- this loop makes that automatic instead.
#
# It is NOT a `bar { swaybar_command ... }` target because that path turned
# out to be a dead end here: with a bar already dead, `swaymsg reload`
# reliably re-ran every OTHER exec_always (idle.sh and kanshi both got fresh
# PIDs) but never relaunched the bar's process -- tried with the plain
# `waybar` command, an inline `sh -c` loop, and this exact script, all three
# times zero result after 5s of polling. `swaymsg exec waybar`, by contrast,
# started it immediately every time. So the bar is launched the same way as
# every other daemon in this repo (exec_always + pkill, see idle.sh/kanshi),
# never through the bar block.
#
# `setpriv --pdeathsig TERM` is the load-bearing part, not a nicety, and it
# is why this script cannot be reduced back to a bare `waybar &`. Without it
# a supervisor that dies leaves its waybar running, reparented to init -- and
# an unsupervised bar is pixel-identical to a supervised one, so the desktop
# looks perfect while the restart-on-crash this file exists to provide is
# silently gone. That is not hypothetical: on 2026-09-15 the bar vanished at
# 08:07:54 and stayed gone for 13 hours, and the coredump recorded `PPid: 1`
# on the waybar that died -- it had been orphaned days earlier and nobody
# could see it. A trap alone does not close this: SIGKILL (and anything else
# that never reaches a handler) runs no trap, whereas PR_SET_PDEATHSIG is the
# kernel's own bookkeeping and fires regardless of how the parent died.
# Verified by SIGKILLing a supervisor and watching the child go with it.
# setpriv execs waybar in place, so comm stays "waybar" and the
# `pkill -x waybar` in autostart_applications still matches. See §9.29.
#
# The traps matter for the ordinary signals: without them a TERM/INT that
# reaches only this process would leave the child behind (pdeathsig is the
# backstop, but leaving a window where two waybars fight over one layer-shell
# surface is still worth closing). `exit 0` on every catchable stop signal,
# with the kill hung off EXIT so *every* exit path -- signal, error, or
# falling out of the loop -- goes through the same cleanup. `pid` is
# initialised because `set -u` would otherwise abort the EXIT trap on a
# signal that lands before the first assignment, which is the one moment the
# cleanup is needed.
#
# The comm name matters too: `pkill -x` in autostart_applications only works
# because `waybar_run.sh` is <=15 bytes and survives comm truncation -- don't
# rename this past that. And `pkill -x` matches by name across the whole
# session, not per-directory: a test that copies this script must rename the
# copy, or it kills the live desktop's bar (§9.29).
set -u

# Restart history. waybar's own stderr goes to sway's tty, which nothing
# records, so before this the only evidence a bar had ever died was a
# coredump. Bounded on every start; a crash-loop must not fill the disk.
log_dir=${XDG_STATE_HOME:-$HOME/.local/state}/waybar
log=$log_dir/run.log
mkdir -p "$log_dir" 2>/dev/null || true
say() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >>"$log" 2>/dev/null || true
}
if [ "$(wc -l <"$log" 2>/dev/null || echo 0)" -gt 500 ]; then
    tail -n 200 "$log" >"$log.tmp" 2>/dev/null && mv "$log.tmp" "$log" 2>/dev/null
fi

pid=
cleanup() { [ -n "$pid" ] && kill "$pid" 2>/dev/null; return 0; }
trap 'exit 0' TERM INT HUP QUIT
trap cleanup EXIT

say "supervisor started (pid $$)"

# A bar that cannot start at all -- a broken config, a missing module binary --
# exits immediately, and a flat `sleep 1` would respawn it forever at 1Hz with
# nothing on screen and nothing said. Back off instead, and once it is clear
# this is not a one-off crash, say so through the only channel a missing bar
# leaves: a notification.
# Resolved once, not per restart, so the warning below cannot repeat on a
# crash loop. setpriv ships in util-linux, which pacman lists as `Required By:
# base` -- this branch should be unreachable on any working Arch system, which
# is exactly why it must be loud if it ever fires rather than quietly handing
# back the orphan bug this script exists to remove. It still starts waybar:
# a bar with degraded recovery is the pre-2026-09-15 status quo and beats no
# bar at all, and check_consumers.sh's supervision check catches the orphan if
# one ever appears.
if command -v setpriv >/dev/null 2>&1; then
    have_setpriv=1
else
    have_setpriv=0
    say "setpriv MISSING - waybar runs without pdeathsig; a killed supervisor can orphan it"
    command -v notify-send >/dev/null 2>&1 && notify-send -u critical \
        "waybar supervision degraded" \
        "setpriv (util-linux) is missing, so a killed supervisor can leave the bar orphaned. PLAYBOOK §9.29." 2>/dev/null
fi

fails=0
while :; do
    started=$(date +%s)

    # The `if` is two literal invocations rather than an array or a function
    # so that both branches are a plain background command: `$!` must be
    # waybar's own pid, not a wrapper shell's, or cleanup and pdeathsig would
    # both be aimed one process too high.
    if [ "$have_setpriv" = 1 ]; then
        setpriv --pdeathsig TERM waybar &
    else
        waybar &
    fi
    pid=$!

    wait "$pid"
    rc=$?
    ran=$(( $(date +%s) - started ))

    if [ "$ran" -lt 5 ]; then
        fails=$((fails + 1))
    else
        fails=0
    fi
    say "waybar (pid $pid) exited rc=$rc after ${ran}s; consecutive fast exits: $fails"

    # 1, 2, 4, 8, 16, then hold at 30s.
    delay=1
    i=1
    while [ "$i" -lt "$fails" ] && [ "$delay" -lt 30 ]; do
        delay=$((delay * 2))
        i=$((i + 1))
    done
    [ "$delay" -gt 30 ] && delay=30

    if [ "$fails" = 5 ] && command -v notify-send >/dev/null 2>&1; then
        notify-send -u critical "waybar keeps dying" \
            "5 restarts in a row, each under 5s. See $log" 2>/dev/null || true
    fi

    sleep "$delay"
done
