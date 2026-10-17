#!/bin/sh
# Sandboxed tests for the power policy: `sway/.config/sway/scripts/idle.sh`,
# its keep-awake override `awake.sh`, and the lid-close handler `lid.sh`.
#
# Never touches the live desktop: `swayidle`, `pkill`, `powerprofilesctl`,
# `swaymsg`, `pgrep`, `fuzzel` and `notify-send` are logging stubs at the front
# of PATH, the AC state and the keep-awake deadline are files under the
# sandbox, lid.sh's lock is a stub, and the only process this file kills is the
# idle.sh it started, by PID. The `pkill` stub is the important one -- idle.sh
# runs `pkill -x swayidle` on every power switch, and the real one would kill
# the live session's swayidle (§9.29); the real powerprofilesctl would switch
# the machine's profile, and a real swaymsg would turn the laptop panel off.
#
# Also asserts the bug this suite was written for: inhibit-sleep-on-ac.service
# held a logind `idle` inhibitor, swayidle >= 1.8 answers that by disabling every
# timeout, and the screen never blanked or locked on AC (§9.26).
#
# Point IDLE_BIN, AWAKE_BIN or LID_BIN at another copy to check the assertions
# can still fail.

set -u

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
IDLE_BIN=${IDLE_BIN:-$REPO/sway/.config/sway/scripts/idle.sh}
AWAKE_BIN=${AWAKE_BIN:-$REPO/sway/.config/sway/scripts/awake.sh}
LID_BIN=${LID_BIN:-$REPO/sway/.config/sway/scripts/lid.sh}
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
# Before the first run, not just the keep-awake checks: unset, idle.sh would
# read the live session's deadline and every policy check would see no timeouts.
export IDLE_AWAKE_FILE="$sandbox/awake-until"
export LID_LOCK="$sandbox/lock.sh"

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
# `swaymsg -t get_outputs` answers $OUTPUTS (and exits $SWAYMSG_RC); anything
# else is only logged.
cat >"$sandbox/bin/swaymsg" <<'STUB'
#!/bin/sh
line=swaymsg; for a in "$@"; do line="$line|$a"; done
printf '%s\n' "$line" >>"$LOG"
if [ "${1:-}" = -t ] && [ "${2:-}" = get_outputs ]; then
    [ -n "${OUTPUTS:-}" ] && printf '%s\n' "$OUTPUTS"
    exit "${SWAYMSG_RC:-0}"
fi
STUB
cat >"$sandbox/bin/pgrep" <<'STUB'
#!/bin/sh
line=pgrep; for a in "$@"; do line="$line|$a"; done
printf '%s\n' "$line" >>"$LOG"
exit "${PGREP_RC:-1}"
STUB
# The rows offered go to fuzzel_in; the pick is $FUZZEL_OUT, exit $FUZZEL_RC.
cat >"$sandbox/bin/fuzzel" <<'STUB'
#!/bin/sh
cat >"$(dirname "$LOG")/fuzzel_in"
[ -n "${FUZZEL_OUT:-}" ] && printf '%s\n' "$FUZZEL_OUT"
exit "${FUZZEL_RC:-0}"
STUB
cat >"$sandbox/bin/notify-send" <<'STUB'
#!/bin/sh
line=notify-send; for a in "$@"; do line="$line|$a"; done
printf '%s\n' "$line" >>"$LOG"
STUB
cat >"$sandbox/lock.sh" <<'STUB'
#!/bin/sh
line=lock; for a in "$@"; do line="$line|$a"; done
printf '%s\n' "$line" >>"$LOG"
STUB
chmod +x "$sandbox/bin/"* "$sandbox/lock.sh"

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
wait_swayidle() {   # until the log holds $1 swayidle runs, ~5 s at most
    i=0
    while [ "$(grep -c '^swayidle' "$LOG")" -lt "$1" ] && [ $i -lt 50 ]; do
        sleep 0.1; i=$((i+1))
    done
}
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

AWAKE=$IDLE_AWAKE_FILE
now() { date +%s; }
awake_want="swayidle|-w|before-sleep|$LOCK"

echo "idle.sh keep-awake"

echo $(( $(now) + 3600 )) >"$AWAKE"
run 1
got=$(call 1); prof=$(profile 1); stop
[ "$got" = "$awake_want" ] && [ "$prof" = "powerprofilesctl|set|performance" ] \
    && ok "keep-awake on AC: no timeouts, still locks before sleep, profile as usual" \
    || no "keep-awake on AC: no timeouts, still locks before sleep, profile as usual" "got: $got / $prof"

run 0
got=$(call 1); prof=$(profile 1); stop
[ "$got" = "$awake_want" ] && [ "$prof" = "powerprofilesctl|set|balanced" ] \
    && ok "keep-awake on battery: no idle suspend either" \
    || no "keep-awake on battery: no idle suspend either" "got: $got / $prof"

echo $(( $(now) - 1 )) >"$AWAKE"
run 0
got=$(call 1); stop
[ "$got" = "$bat_want" ] && [ ! -e "$AWAKE" ] \
    && ok "an expired keep-awake gives the normal policy back, and is deleted" \
    || no "an expired keep-awake gives the normal policy back, and is deleted" \
          "got: $got; file $( [ -e "$AWAKE" ] && echo kept || echo gone)"

echo soon >"$AWAKE"
run 0
got=$(call 1); stop
[ "$got" = "$bat_want" ] && ok "a garbled keep-awake deadline is ignored: fail toward locking" \
    || no "a garbled keep-awake deadline is ignored: fail toward locking" "got: $got"

# A 30s poll, so only the signal can explain a change inside the 5s wait.
rm -f "$AWAKE"
IDLE_POLL=30
run 0
echo $(( $(now) + 3600 )) >"$AWAKE"
kill -USR1 "$pid" 2>/dev/null
wait_swayidle 2
got=$(call 2); nprof=$(grep -c '^powerprofilesctl' "$LOG"); stop
IDLE_POLL=0.1
[ "$got" = "$awake_want" ] && ok "USR1 (from awake.sh) applies keep-awake at once, not at the next poll" \
    || no "USR1 (from awake.sh) applies keep-awake at once, not at the next poll" "got: $got"
[ "$nprof" = 1 ] && ok "switching keep-awake leaves the power profile alone" \
    || no "switching keep-awake leaves the power profile alone" "$nprof profile switches"

echo $(( $(now) + 2 )) >"$AWAKE"
run 0
wait_swayidle 2
first=$(call 1); got=$(call 2); stop
[ "$first" = "$awake_want" ] && [ "$got" = "$bat_want" ] && [ ! -e "$AWAKE" ] \
    && ok "keep-awake ends by itself at its deadline" \
    || no "keep-awake ends by itself at its deadline" "got: $first -> $got"
rm -f "$AWAKE"

echo "awake.sh"

aw() { bash "$AWAKE_BIN" "$@"; }
# Assignments before a *function* call do not reliably reach its children under
# dash, so the stubs' knobs go through env: aw_env <subcommand> VAR=value...
aw_env() { sub=$1; shift; env "$@" bash "$AWAKE_BIN" "$sub"; }
deadline_is() {   # the file holds now + $1 minutes, give or take the 5s a slow run costs
    d=$(cat "$AWAKE" 2>/dev/null) || return 1
    case $d in ''|*[!0-9]*) return 1 ;; esac
    off=$(( $(now) + $1 * 60 - d ))
    [ "$off" -ge 0 ] && [ "$off" -le 5 ]
}

: >"$LOG"
aw on && deadline_is 120 && ok "on: 2 hours by default" || no "on: 2 hours by default" "file: $(cat "$AWAKE" 2>&1)"
grep -qx 'pkill|-USR1|-x|idle.sh' "$LOG" && grep -qx 'pkill|-RTMIN+11|-x|waybar' "$LOG" \
    && ok "on: wakes idle.sh and refreshes the bar, both by exact name" \
    || no "on: wakes idle.sh and refreshes the bar, both by exact name" "$(grep '^pkill' "$LOG" | tr '\n' ' ')"

bad=''
for spec in 45:45 90m:90 1h:60 '2 hours:120' '30 min:30' '8 hours:480' 1440:1440 3H:180; do
    rm -f "$AWAKE"
    aw on "${spec%:*}" && deadline_is "${spec##*:}" || bad="$bad [${spec%:*}]"
done
[ -z "$bad" ] && ok "durations: bare minutes, or m/min/h/hour(s)" || no "durations: bare minutes, or m/min/h/hour(s)" "wrong:$bad"

bad=''
for d in 0 -5 1441 25h abc 1.5h 99999999999999999999; do
    echo sentinel >"$AWAKE"
    aw on "$d" 2>/dev/null && bad="$bad [$d accepted]"
    [ "$(cat "$AWAKE")" = sentinel ] || bad="$bad [$d changed the file]"
done
[ -z "$bad" ] && ok "out-of-range or garbled durations are refused and change nothing" \
    || no "out-of-range or garbled durations are refused and change nothing" "$bad"

aw on 30; aw off
[ ! -e "$AWAKE" ] && ok "off ends it" || no "off ends it"

aw toggle; deadline_is 120 && { aw toggle; [ ! -e "$AWAKE" ]; } \
    && ok "toggle: 2 hours on, then off" || no "toggle: 2 hours on, then off"

field() { python3 -I -c 'import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])' "$1" "$2" 2>&1; }
s=$(aw status)
[ "$(field "$s" alt)" = deactivated ] && ok "status: off reads deactivated" || no "status: off reads deactivated" "$s"
aw on 90; s=$(aw status)
[ "$(field "$s" alt)" = activated ] && case $(field "$s" tooltip) in *"1h 30m left"*) true ;; *) false ;; esac \
    && ok "status: on reads activated, with the time left" || no "status: on reads activated, with the time left" "$s"
echo $(( $(now) - 1 )) >"$AWAKE"; s=$(aw status)
[ "$(field "$s" alt)" = deactivated ] && ok "status: an expired deadline reads deactivated" \
    || no "status: an expired deadline reads deactivated" "$s"

rm -f "$AWAKE"
aw_env pick FUZZEL_OUT='2 hours' && deadline_is 120 && ! grep -q '^Stop' "$sandbox/fuzzel_in" \
    && ok "pick: a listed time; no stop row while off" || no "pick: a listed time; no stop row while off" "$(cat "$sandbox/fuzzel_in")"
aw_env pick FUZZEL_OUT=45m && deadline_is 45 && ok "pick: a typed time" || no "pick: a typed time"
aw on 60
aw_env pick FUZZEL_OUT= FUZZEL_RC=1 && deadline_is 60 \
    && ok "pick: Esc exits 0 and changes nothing" || no "pick: Esc exits 0 and changes nothing"
aw_env pick FUZZEL_OUT='Stop keeping awake' && grep -q '^Stop keeping awake$' "$sandbox/fuzzel_in" && [ ! -e "$AWAKE" ] \
    && ok "pick: while on, it offers stop" || no "pick: while on, it offers stop"
: >"$LOG"
aw_env pick FUZZEL_OUT=soon && [ ! -e "$AWAKE" ] && grep -q '^notify-send' "$LOG" \
    && ok "pick: a nonsense time says so and changes nothing" || no "pick: a nonsense time says so and changes nothing"

echo "lid.sh"

one='[{"name":"eDP-1","active":true}]'
two='[{"name":"eDP-1","active":true},{"name":"DP-1","active":true}]'
dark='[{"name":"eDP-1","active":true},{"name":"DP-1","active":false}]'
lid() { : >"$LOG"; env "$@" bash "$LID_BIN" close; }
panel_off() { grep -qx 'swaymsg|output|eDP-1|disable' "$LOG"; }
locked() { grep -qx 'lock|-f' "$LOG"; }

lid OUTPUTS="$one"; panel_off && locked && ok "lid closed, no other display: panel off and locked" \
    || no "lid closed, no other display: panel off and locked" "$(tr '\n' ' ' <"$LOG")"
lid OUTPUTS="$two"; panel_off && ! locked && ok "lid closed with another display on: panel off, not locked" \
    || no "lid closed with another display on: panel off, not locked" "$(tr '\n' ' ' <"$LOG")"
lid OUTPUTS="$dark"; panel_off && locked && ok "a display that is attached but off does not count" \
    || no "a display that is attached but off does not count" "$(tr '\n' ' ' <"$LOG")"
lid OUTPUTS= SWAYMSG_RC=1; panel_off && locked && ok "sway cannot list outputs: lock anyway" \
    || no "sway cannot list outputs: lock anyway" "$(tr '\n' ' ' <"$LOG")"
lid OUTPUTS="$one" PGREP_RC=0; panel_off && ! locked && ok "already locked: no second swaylock" \
    || no "already locked: no second swaylock" "$(tr '\n' ' ' <"$LOG")"

grep -qx 'bindswitch --reload --locked lid:on exec ~/.config/sway/scripts/lid.sh close' \
        "$REPO/sway/.config/sway/config.d/input" \
    && ok "sway's lid:on binding runs lid.sh" || no "sway's lid:on binding runs lid.sh"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
