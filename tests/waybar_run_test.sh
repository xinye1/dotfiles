#!/bin/sh
# Sandboxed tests for `sway/.config/sway/scripts/waybar_run.sh`.
#
# Never touches the live desktop: the script under test is run against a fake
# `waybar` on PATH and a throwaway $HOME, and every process this file kills is
# killed by a PID it captured itself.
#
# **No `pkill` in here, at any cost.** `pkill -x` matches by comm across the
# whole session, so `pkill -x waybar_run.sh` inside a "sandbox" reaches out and
# kills the real supervisor, and `pkill -x waybar` kills the real bar. That is
# not a hypothetical either -- it is how the bar got taken down while this very
# regression was being investigated (§9.29).
#
# Point WBR_BIN at another copy to check the assertions can still fail. A green
# suite that cannot go red is the gate-fixtures trap (see tp_backup_test.sh):
# this one was built by proving cases 3 and 4 fail against the pre-fix script.

set -u

WBR_BIN=${WBR_BIN:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/sway/.config/sway/scripts/waybar_run.sh}

pass=0; fail=0
ok() { pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
no() { fail=$((fail+1)); printf '  FAIL  %s\n' "$1"; [ $# -lt 2 ] || printf '        %s\n' "$2"; }

sandbox=$(mktemp -d)
# Cleanup hangs off EXIT alone; the signal traps do nothing but exit into it.
# A signal trap that cleaned up and *returned* would drop the script back into
# the next check with $PATH still pointing at the deleted sandbox -- where
# `waybar` resolves to the real one, so an interrupted run would start the
# live bar and supervise it. Same shape as the script under test.
trap 'kill_all; rm -rf "$sandbox"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

tracked=''
kill_all() {
    for p in $tracked; do
        kill -9 "$p" 2>/dev/null
        # reap it here, or the shell prints its own "Killed" notice later and
        # scribbles over the tally this file exists to produce
        wait "$p" 2>/dev/null || true
    done
    tracked=''
}
track() { tracked="$tracked $1"; }

mkdir -p "$sandbox/bin" "$sandbox/home"
export HOME="$sandbox/home"
export XDG_STATE_HOME="$sandbox/home/.local/state"
export PATH="$sandbox/bin:$PATH"
export SPAWNS="$sandbox/spawns"
: >"$SPAWNS"

# The stub stands in for waybar: it records that it started and then sits
# there. STUB_LIFE=0 makes it exit at once, which is what a broken config
# looks like from the supervisor's side.
cat >"$sandbox/bin/waybar" <<'STUB'
#!/bin/sh
echo "$$" >>"$SPAWNS"
[ "${STUB_LIFE:-300}" = 0 ] && exit 1
exec sleep "${STUB_LIFE:-300}"
STUB
chmod +x "$sandbox/bin/waybar"

start_supervisor() {
    "$WBR_BIN" </dev/null >"$sandbox/out" 2>&1 &
    sup=$!
    track "$sup"
    # Wait for the first child rather than sleeping a guessed interval.
    n=0
    while [ "$n" -lt 50 ]; do
        child=$(pgrep -P "$sup" 2>/dev/null | head -1)
        [ -n "$child" ] && { track "$child"; return 0; }
        sleep 0.1
        n=$((n+1))
    done
    child=''
    return 1
}

alive() { kill -0 "$1" 2>/dev/null; }
orphaned() { [ "$(awk '/^PPid:/{print $2}' "/proc/$1/status" 2>/dev/null)" = 1 ]; }

printf '\nwaybar_run\n'
printf '  (%s)\n' "$WBR_BIN"

# --- 1. a crashed bar comes back ---
# The whole reason the script exists. SIGABRT is what waybar actually dies of.
if start_supervisor; then
    first=$child
    kill -ABRT "$first" 2>/dev/null
    n=0; second=''
    while [ "$n" -lt 50 ]; do
        second=$(pgrep -P "$sup" 2>/dev/null | head -1)
        [ -n "$second" ] && [ "$second" != "$first" ] && break
        second=''; sleep 0.1; n=$((n+1))
    done
    [ -n "$second" ] && track "$second"
    if [ -n "$second" ]; then
        ok "a crashed waybar is restarted"
    else
        no "a crashed waybar is restarted" "no new child after SIGABRT to $first"
    fi
else
    no "a crashed waybar is restarted" "supervisor never started a child"
fi
kill_all

# --- 2. SIGTERM takes the bar with it ---
# The reload path: autostart_applications TERMs the supervisor before exec'ing
# a fresh one. A child left behind here is a second bar fighting for the
# layer-shell surface.
if start_supervisor; then
    c=$child
    kill -TERM "$sup" 2>/dev/null
    sleep 1
    if alive "$c"; then
        no "SIGTERM to the supervisor takes waybar down" "child $c survived (ppid $(awk '/^PPid:/{print $2}' /proc/"$c"/status 2>/dev/null))"
    else
        ok "SIGTERM to the supervisor takes waybar down"
    fi
else
    no "SIGTERM to the supervisor takes waybar down" "supervisor never started a child"
fi
kill_all

# --- 3. SIGHUP takes the bar with it ---
# The 2026-09-15 regression, exactly. The pre-fix script trapped TERM and INT
# only, so a HUP killed the supervisor and left waybar running with PPid 1 --
# a bar that looks perfect and is no longer supervised by anything.
if start_supervisor; then
    c=$child
    kill -HUP "$sup" 2>/dev/null
    sleep 1
    if alive "$c"; then
        orph=$(orphaned "$c" && echo ' and is orphaned (PPid 1)' || echo '')
        no "SIGHUP to the supervisor takes waybar down" "child $c survived$orph"
    else
        ok "SIGHUP to the supervisor takes waybar down"
    fi
else
    no "SIGHUP to the supervisor takes waybar down" "supervisor never started a child"
fi
kill_all

# --- 4. SIGKILL takes the bar with it ---
# The case no trap can cover, and the reason `setpriv --pdeathsig` is in the
# script rather than a tidier handler. The kernel does this one.
if start_supervisor; then
    c=$child
    kill -9 "$sup" 2>/dev/null
    sleep 1
    if alive "$c"; then
        orph=$(orphaned "$c" && echo ' and is orphaned (PPid 1)' || echo '')
        no "SIGKILL to the supervisor takes waybar down (pdeathsig)" "child $c survived$orph"
    else
        ok "SIGKILL to the supervisor takes waybar down (pdeathsig)"
    fi
else
    no "SIGKILL to the supervisor takes waybar down (pdeathsig)" "supervisor never started a child"
fi
kill_all

# --- 5. a bar that cannot start at all backs off ---
# A flat `sleep 1` respawns roughly ten times in ten seconds, forever, with
# nothing on screen and nothing logged anywhere a person looks.
: >"$SPAWNS"
STUB_LIFE=0 "$WBR_BIN" </dev/null >"$sandbox/out2" 2>&1 &
sup=$!; track "$sup"
sleep 10
kill -TERM "$sup" 2>/dev/null
spawns=$(wc -l <"$SPAWNS" | tr -d ' ')
if [ "$spawns" -le 6 ]; then
    ok "a bar that exits instantly is backed off, not respawned at 1Hz ($spawns starts in 10s)"
else
    no "a bar that exits instantly is backed off, not respawned at 1Hz" \
       "$spawns starts in 10s; a flat 1s retry gives ~10"
fi
kill_all

# --- 6. restarts leave a trace ---
# waybar's stderr goes to sway's tty and nothing records it. Diagnosing the
# 2026-09-15 outage needed coredump forensics because of that.
runlog="$XDG_STATE_HOME/waybar/run.log"
if [ -s "$runlog" ] && grep -q 'exited rc=' "$runlog"; then
    ok "restarts are recorded in \$XDG_STATE_HOME/waybar/run.log"
else
    no "restarts are recorded in \$XDG_STATE_HOME/waybar/run.log" \
       "$(if [ -e "$runlog" ]; then echo 'log exists but records no exit'; else echo 'no log written'; fi)"
fi

printf '\n  %d passed, %d failed\n\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
