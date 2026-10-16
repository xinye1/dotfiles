#!/bin/sh
# Sandboxed tests for `sway/.config/sway/scripts/idle.sh`, the power policy.
#
# Never touches the live desktop: `swayidle`, `pkill` and `powerprofilesctl`
# are logging stubs at the front of PATH, the AC state is a file under the sandbox, and the
# only process this file kills is the idle.sh it started, by PID. The `pkill`
# stub is the important one -- idle.sh runs `pkill -x swayidle` on every power
# switch, and the real one would kill the live session's swayidle (§9.29); the
# real powerprofilesctl would switch the machine's profile.
#
# Also asserts the bug this suite was written for: inhibit-sleep-on-ac.service
# held a logind `idle` inhibitor, swayidle >= 1.8 answers that by disabling every
# timeout, and the screen never blanked or locked on AC (§9.26).
#
# Point IDLE_BIN at another copy to check the assertions can still fail.

set -u

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
IDLE_BIN=${IDLE_BIN:-$REPO/sway/.config/sway/scripts/idle.sh}
UNIT=$REPO/systemd-system/etc/systemd/system/inhibit-sleep-on-ac.service

pass=0; fail=0
ok() { pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
no() { fail=$((fail+1)); printf '  FAIL  %s\n' "$1"; [ $# -lt 2 ] || printf '        %s\n' "$2"; }

sandbox=$(mktemp -d)
# Kill before deleting: an idle.sh outliving its sandbox would find the REAL
# pkill and swayidle on the rest of PATH.
trap 'stop; rm -rf "$sandbox"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

pid=''
stop() {
    [ -n "$pid" ] || return 0
    kill -9 "$pid" 2>/dev/null
    wait "$pid" 2>/dev/null || true
    pid=''
}

mkdir -p "$sandbox/bin"
export PATH="$sandbox/bin:$PATH"
export LOG="$sandbox/log"
export IDLE_AC_ONLINE="$sandbox/ac_online" IDLE_POLL=0.1

# One line per call: the tool name, then its arguments joined by `|`, so a
# quoted command ('swaymsg "output * dpms off"') stays one field. Each line is
# one write: idle.sh backgrounds swayidle, so stubs log concurrently.
cat >"$sandbox/bin/swayidle" <<'STUB'
#!/bin/sh
line=swayidle; for a in "$@"; do line="$line|$a"; done
printf '%s\n' "$line" >>"$LOG"
STUB
cat >"$sandbox/bin/pkill" <<'STUB'
#!/bin/sh
line=pkill; for a in "$@"; do line="$line|$a"; done
printf '%s\n' "$line" >>"$LOG"
STUB
cat >"$sandbox/bin/powerprofilesctl" <<'STUB'
#!/bin/sh
line=powerprofilesctl; for a in "$@"; do line="$line|$a"; done
printf '%s\n' "$line" >>"$LOG"
STUB
chmod +x "$sandbox/bin/"*

# run <ac_online or "missing"> [bin]; waits for the first policy to be
# applied and leaves idle.sh running (call stop after).
run() {
    : >"$LOG"
    if [ "$1" = missing ]; then rm -f "$IDLE_AC_ONLINE"; else echo "$1" >"$IDLE_AC_ONLINE"; fi
    bash "${2:-$IDLE_BIN}" & pid=$!
    wait_lines 1
}
wait_lines() {   # until the log holds $1 swayidle runs and profile switches, ~5 s at most
    i=0
    while { [ "$(grep -c '^swayidle' "$LOG")" -lt "$1" ] \
            || [ "$(grep -c '^powerprofilesctl' "$LOG")" -lt "$1" ]; } && [ $i -lt 50 ]; do
        sleep 0.1; i=$((i+1))
    done
}
# swayidle is backgrounded, so its line can land after the profile switch's:
# only "the Nth pkill came before the Nth swayidle" is an ordering to assert.
kills_first() { awk -F'|' '$1=="pkill"{k++} $1=="swayidle"{if(++s>k)bad=1} END{exit bad}' "$LOG"; }
call() { grep '^swayidle' "$LOG" | sed -n "${1}p"; }
profile() { grep '^powerprofilesctl' "$LOG" | sed -n "${1}p"; }

DPMS='timeout|%s|swaymsg "output * dpms off"|resume|swaymsg "output * dpms on"'
LOCK='~/.config/sway/scripts/lock.sh -f'
ac_want="swayidle|-w|$(printf "$DPMS" 180)|timeout|300|$LOCK|before-sleep|$LOCK"
bat_want="swayidle|-w|$(printf "$DPMS" 60)|timeout|120|$LOCK|timeout|900|systemctl suspend|before-sleep|$LOCK"

echo "idle.sh policy"

run 1
got=$(call 1); prof=$(profile 1); stop
[ "$got" = "$ac_want" ] && ok "AC: screen off 180, lock 300, never sleeps" \
    || no "AC: screen off 180, lock 300, never sleeps" "got: $got"
[ "$prof" = "powerprofilesctl|set|performance" ] && ok "AC: performance profile" \
    || no "AC: performance profile" "got: $prof"

run 0
got=$(call 1); prof=$(profile 1); stop
[ "$got" = "$bat_want" ] && ok "battery: screen off 60, lock 120, suspend 900" \
    || no "battery: screen off 60, lock 120, suspend 900" "got: $got"
[ "$prof" = "powerprofilesctl|set|balanced" ] && ok "battery: balanced profile" \
    || no "battery: balanced profile" "got: $prof"
case $(grep '^swayidle' "$LOG") in
    *hibernate*) no "no hibernation anywhere (decided 2026-10-17)" ;;
    *) ok "no hibernation anywhere (decided 2026-10-17)" ;;
esac

run missing
got=$(call 1); stop
[ "$got" = "$ac_want" ] && ok "unreadable AC state falls back to the AC policy" \
    || no "unreadable AC state falls back to the AC policy" "got: $got"

run 1
echo 0 >"$IDLE_AC_ONLINE"; wait_lines 2
sleep 0.5   # five more polls with no change: none of them may reapply
got=$(call 2); prof=$(profile 2); stop
[ "$got" = "$bat_want" ] && [ "$prof" = "powerprofilesctl|set|balanced" ] \
    && ok "unplugging switches to the battery policy live" \
    || no "unplugging switches to the battery policy live" "got: $got / $prof"
counts=$(cut -d'|' -f1 "$LOG" | sort | uniq -c | tr -s ' \n' ' ')
kills_first && [ "$counts" = " 2 pkill 2 powerprofilesctl 2 swayidle " ] \
    && ok "each switch kills the old swayidle first, and only a switch reapplies" \
    || no "each switch kills the old swayidle first, and only a switch reapplies" "got:$counts"

sed 's/^AC_SCREEN_OFF=180;   BAT_SCREEN_OFF=60$/AC_SCREEN_OFF=180;   BAT_SCREEN_OFF=0/' \
    "$IDLE_BIN" >"$sandbox/zero.sh"
run 0 "$sandbox/zero.sh"
got=$(call 1); stop
case $got in
    *dpms*) no "a 0 timeout means never" "got: $got" ;;
    *) grep -q 'BAT_SCREEN_OFF=0' "$sandbox/zero.sh" && ok "a 0 timeout means never" \
           || no "a 0 timeout means never" "the sed no longer matches idle.sh's policy block" ;;
esac

case $(grep "^swayidle" "$LOG") in
    *idlehint*) no "no idlehint: logind's IdleAction never races this policy" ;;
    *) ok "no idlehint: logind's IdleAction never races this policy" ;;
esac

what=$(sed -n 's/^ExecStart=.*--what=\([^ ]*\).*/\1/p' "$UNIT")
case ":$what:" in
    ::) no "inhibit-sleep-on-ac.service: --what found" "no --what= on an ExecStart line" ;;
    *:idle:*) no "inhibit-sleep-on-ac.service holds no idle inhibitor" \
                  "--what=$what: swayidle disables every timeout while it is held" ;;
    *:sleep:*) ok "inhibit-sleep-on-ac.service holds no idle inhibitor (--what=$what)" ;;
    *) no "inhibit-sleep-on-ac.service still blocks sleep" "--what=$what" ;;
esac

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
