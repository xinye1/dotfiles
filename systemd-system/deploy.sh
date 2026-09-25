#!/usr/bin/env bash
#
# systemd-system/deploy.sh — installs everything under systemd-system/ onto
# this machine: first the never-sleep-on-AC inhibitor (a unit and the udev
# rule that starts/stops it on plug/unplug), then the jellyfin-state-dump
# script, its config, and its three units (.service, .timer, the OnFailure=
# alerter). This is the canonical, only procedure for deploying this tree —
# see README.md and PLAYBOOK.md §5.2, which point here rather than
# duplicating the steps.
#
# Usage:  sudo systemd-system/deploy.sh     (run from the repo root)
#     or: sudo bash /path/to/systemd-system/deploy.sh
#
# Idempotent: safe to re-run after `git pull`ing repo changes. Re-running
# refreshes the unit files and the script; it deliberately leaves an
# already-present /etc/jellyfin-state-dump.conf's VALUES untouched, but
# warns loudly if they've drifted from this machine's current tp-backup
# config or still hold the example placeholder.
#
# Why this is a script and not another stow package: systemd-system/ mirrors
# /etc/systemd/system and /usr/local/bin, not $HOME. This repo's .stowrc
# pins --target=~ for every package, so stowing it would silently link to
# ~/etc/systemd/system instead (exit 0, installing nothing systemd reads).
# See PLAYBOOK.md §5.2.
#
# Why the script and config live outside the stow-managed `bin` package:
# jellyfin-state-dump.service runs as root and both ExecStart's and
# source's files. A root service trusting a script or config the login
# user can write is a straight line from "anything running as that user"
# to root at the next timer firing. This deploy script honours that same
# rule for itself: it extracts NTFY_TOPIC/NTFY_SERVER from the user's
# tp-backup config by parsing text, never by sourcing (executing) it.

set -Eeuo pipefail

STAGE="start"
on_err() {
    echo "deploy: FAILED at stage '$STAGE' (line $1). System state: whatever the" >&2
    echo "deploy: previous stage(s) completed is in place; nothing after '$STAGE' ran." >&2
    if systemctl is-active --quiet jellyfin-state-dump.timer 2>/dev/null; then :; else
        echo "deploy: jellyfin-state-dump.timer is currently STOPPED (this script stops" >&2
        echo "deploy: it for the duration of the install). Fix the failure above, then" >&2
        echo "deploy: re-run this script to reinstall and re-arm it." >&2
    fi
}
trap 'on_err $LINENO' ERR

[[ $EUID -eq 0 ]] || { echo "deploy: must run as root — sudo bash $0" >&2; exit 1; }

STAGE="resolve owner"
# sudo resets $HOME to root's by default, so resolve the invoking user's
# home explicitly rather than trusting $HOME inside this script.
OWNER="${SUDO_USER:-xinye}"
# Every artifact this script installs hardcodes "xinye" (the script itself,
# ReadWritePaths= in the unit). A dynamically-resolved OWNER that disagreed
# would deploy a config read from one user's files into a service that
# writes another user's home -- so assert they match rather than trusting
# the derivation.
if [[ "$OWNER" != "xinye" ]]; then
    echo "deploy: resolved owner '$OWNER' != 'xinye', which is hardcoded into the" >&2
    echo "deploy: installed script and unit. Refusing rather than deploying a mismatch." >&2
    exit 1
fi
OWNER_HOME=$(getent passwd "$OWNER" | cut -d: -f6) || true
if [[ -z "${OWNER_HOME:-}" || ! -d "$OWNER_HOME" ]]; then
    echo "deploy: cannot resolve a home directory for user '$OWNER'" >&2
    exit 1
fi

REPO="$OWNER_HOME/repos/dotfiles"
SRC="$REPO/systemd-system"
TPB_CONF="$OWNER_HOME/.config/tp-backup/config"

SERVICE_SRC="$SRC/etc/systemd/system/jellyfin-state-dump.service"
TIMER_SRC="$SRC/etc/systemd/system/jellyfin-state-dump.timer"
FAILED_SRC="$SRC/etc/systemd/system/jellyfin-state-dump-failed.service"
SCRIPT_SRC="$SRC/usr/local/bin/jellyfin-state-dump"
CONF_EXAMPLE="$SRC/etc/jellyfin-state-dump.conf.example"  # sanity-checked below, not installed —
                                                            # this script seeds the real config by
                                                            # extracting values, not by copying this
INHIBIT_UNIT_SRC="$SRC/etc/systemd/system/inhibit-sleep-on-ac.service"
INHIBIT_RULE_SRC="$SRC/etc/udev/rules.d/99-inhibit-sleep-on-ac.rules"
INHIBIT_UNIT=/etc/systemd/system/inhibit-sleep-on-ac.service
INHIBIT_RULE=/etc/udev/rules.d/99-inhibit-sleep-on-ac.rules
AC_ONLINE=/sys/class/power_supply/AC/online

STAGE="check inhibitor sources"
# Only the inhibitor's own sources are checked here: a missing jellyfin file
# must not stop the sleep policy from landing (they're checked after it).
for f in "$INHIBIT_UNIT_SRC" "$INHIBIT_RULE_SRC"; do
    [[ -e "$f" ]] || { echo "deploy: expected file missing: $f (is $REPO up to date?)" >&2; exit 1; }
done
if command -v git >/dev/null && git -C "$REPO" rev-parse HEAD >/dev/null 2>&1; then
    echo "deploy: installing from $REPO @ $(git -C "$REPO" rev-parse --short HEAD)" \
         "$(git -C "$REPO" diff --quiet -- systemd-system 2>/dev/null || echo '(systemd-system has local changes)')"
fi

# --- never sleep on AC ------------------------------------------------------
# This machine is a server while it is plugged in: tp2's nightly jobs, Jellyfin
# and the family site all assume it stays up. inhibit-sleep-on-ac.service holds
# a logind *block* inhibitor for sleep, idle AND handle-lid-switch while AC is
# online; the udev rule starts/stops it on plug/unplug. handle-lid-switch is a
# separate inhibitor class from sleep -- the unit once covered only sleep:idle
# and the box slept 23 h through a nightly with the guard "active" the whole
# time (trading-platform-v2 docs/runbooks/automation-nightly-watchdogs.md).
# Installed FIRST, before anything jellyfin-related can fail, because this is
# the part whose absence costs a night.
STAGE="install sleep inhibitor"
inhibit_unit_changed=0
cmp -s "$INHIBIT_UNIT_SRC" "$INHIBIT_UNIT" 2>/dev/null || inhibit_unit_changed=1
echo "deploy: installing sleep inhibitor -> $INHIBIT_UNIT, $INHIBIT_RULE"
install -m 644 -o root -g root "$INHIBIT_UNIT_SRC" "$INHIBIT_UNIT"
install -m 644 -o root -g root "$INHIBIT_RULE_SRC" "$INHIBIT_RULE"
systemctl daemon-reload
udevadm control --reload
systemctl enable inhibit-sleep-on-ac.service
if [[ "$(cat "$AC_ONLINE" 2>/dev/null)" == 1 ]]; then
    # Restart only when the unit's content actually changed: a restart drops
    # the block inhibitor for a moment, which is pointless if nothing new
    # would be picked up.
    if (( inhibit_unit_changed )) && systemctl is-active --quiet inhibit-sleep-on-ac.service; then
        systemctl restart inhibit-sleep-on-ac.service
    else
        systemctl start inhibit-sleep-on-ac.service
    fi
fi

STAGE="verify: sleep inhibitor"
# The unit is Type=simple: `systemctl start` returns once systemd-inhibit is
# forked, before it has registered its lock with logind over D-Bus (and a
# stop likewise returns before logind drops it). Poll for up to 5 s rather
# than judge one instant.
ac_inhibitor_held() {
    systemd-inhibit --list --no-legend --no-pager \
        | grep -E '^ac-power[[:space:]].*sleep:idle:handle-lid-switch[[:space:]].*[[:space:]]block$' >/dev/null
}
any_ac_inhibitor() {
    systemd-inhibit --list --no-legend --no-pager | grep -E '^ac-power[[:space:]]' >/dev/null
}
wait_until() {   # $1 = predicate command; true once it holds, false after ~5 s
    local _
    for _ in {1..20}; do "$@" && return 0; sleep 0.25; done
    return 1
}
cmp -s "$INHIBIT_UNIT_SRC" "$INHIBIT_UNIT" \
    || { echo "deploy: $INHIBIT_UNIT does not match the repo copy" >&2; exit 1; }
cmp -s "$INHIBIT_RULE_SRC" "$INHIBIT_RULE" \
    || { echo "deploy: $INHIBIT_RULE does not match the repo copy" >&2; exit 1; }
echo "  inhibitor unit + udev rule match the repo: OK"
systemctl is-enabled --quiet inhibit-sleep-on-ac.service \
    || { echo "deploy: inhibit-sleep-on-ac.service is not enabled" >&2; exit 1; }
echo "  inhibit-sleep-on-ac.service enabled: OK"
if [[ "$(cat "$AC_ONLINE" 2>/dev/null)" == 1 ]]; then
    # Assert the OUTCOME logind holds, not that the unit is active: the 23 h
    # sleep happened with the unit active. The inhibitor must be a block over
    # the lid switch too.
    wait_until ac_inhibitor_held \
        || { echo "deploy: on AC, but logind holds no ac-power block inhibitor over" >&2
             echo "deploy: sleep:idle:handle-lid-switch -- the machine CAN sleep" >&2; exit 1; }
    echo "  on AC: logind holds the ac-power block inhibitor over sleep:idle:handle-lid-switch: OK"
else
    # On battery the machine SHOULD be able to sleep. udev stops the unit on
    # unplug, but a unit left active (a missed event, a manual start) would
    # keep the block -- ExecCondition only runs at start. Stop it, then assert
    # the outcome here too.
    systemctl stop inhibit-sleep-on-ac.service
    if ! wait_until eval '! any_ac_inhibitor'; then
        echo "deploy: on battery, but logind still holds an ac-power inhibitor" >&2; exit 1
    fi
    echo "  on battery: no ac-power inhibitor held (udev starts it when AC returns): OK"
fi

STAGE="check jellyfin sources"
for f in "$SERVICE_SRC" "$TIMER_SRC" "$FAILED_SRC" "$SCRIPT_SRC" "$CONF_EXAMPLE"; do
    [[ -e "$f" ]] || { echo "deploy: expected file missing: $f (is $REPO up to date?)" >&2; exit 1; }
done

STAGE="stop timer for the duration of the install"
# On a re-run (script, config and units already deployed and the timer
# already enabled+active), installing the three in sequence otherwise means
# a fire between any two of those steps runs a MISMATCHED combination --
# new script against the not-yet-updated unit or config, or vice versa. The
# timer is stopped only for the handful of `install`/write calls below and
# re-armed at the end regardless of outcome; a failure anywhere in between
# leaves it stopped (loudly reported by STAGE) rather than silently running
# a mismatch. `|| true`: on a first-ever deploy the unit doesn't exist yet,
# and "not loaded" is not a reason to abort.
systemctl stop jellyfin-state-dump.timer 2>/dev/null || true

# --- extract NTFY_TOPIC / NTFY_SERVER WITHOUT sourcing (never execute a
# file the login user can write, as root -- the exact rule the migration
# to this deploy tree exists to enforce, applied to itself) -------------
extract_kv() {   # $1 = key, $2 = file
    grep -E "^[[:space:]]*${1}=" "$2" | tail -1 \
        | sed -E "s/^[[:space:]]*${1}=[\"']?([^\"']*)[\"']?[[:space:]]*(#.*)?$/\1/"
}
STAGE="read tp-backup config"
[[ -r "$TPB_CONF" ]] || { echo "deploy: cannot read $TPB_CONF to seed NTFY config" >&2; exit 1; }
# `|| true` on both: pipefail makes extract_kv report the grep miss even
# though sed (its last stage) succeeds on empty input, and under set -e a
# missing NTFY_SERVER would abort HERE, before the :-https://ntfy.sh default
# on the next line ever gets a chance to apply. NTFY_TOPIC being genuinely
# absent is still caught, explicitly, by the -n check below.
NTFY_TOPIC_VAL=$(extract_kv NTFY_TOPIC "$TPB_CONF" || true)
NTFY_SERVER_VAL=$(extract_kv NTFY_SERVER "$TPB_CONF" || true)
NTFY_SERVER_VAL="${NTFY_SERVER_VAL:-https://ntfy.sh}"
[[ -n "$NTFY_TOPIC_VAL" ]] || { echo "deploy: NTFY_TOPIC not found in $TPB_CONF" >&2; exit 1; }
[[ "$NTFY_TOPIC_VAL" =~ ^[A-Za-z0-9_-]+$ ]] \
    || { echo "deploy: NTFY_TOPIC in $TPB_CONF has unexpected characters, refusing to trust it" >&2; exit 1; }
[[ "$NTFY_SERVER_VAL" =~ ^https?://[A-Za-z0-9_.-]+(/.*)?$ ]] \
    || { echo "deploy: NTFY_SERVER in $TPB_CONF doesn't look like a URL, refusing to trust it" >&2; exit 1; }

STAGE="install script"
echo "deploy: installing script -> /usr/local/bin/jellyfin-state-dump"
install -m 755 -o root -g root "$SCRIPT_SRC" /usr/local/bin/jellyfin-state-dump

STAGE="write config"
CONF=/etc/jellyfin-state-dump.conf
if [[ -e "$CONF" ]]; then
    existing_topic=$(extract_kv NTFY_TOPIC "$CONF" || true)
    if [[ "$existing_topic" == '<your-topic>' ]]; then
        echo "deploy: WARNING: $CONF still holds the example placeholder — failures are silent" >&2
    elif [[ "$existing_topic" != "$NTFY_TOPIC_VAL" ]]; then
        echo "deploy: WARNING: $CONF's NTFY_TOPIC differs from $TPB_CONF's current value." >&2
        echo "deploy: leaving it as-is (may be deliberate) — delete $CONF first to reseed." >&2
    else
        echo "deploy: $CONF already exists and matches — leaving it alone"
    fi
else
    echo "deploy: seeding $CONF from this machine's tp-backup config"
    ( umask 077; printf 'NTFY_TOPIC="%s"\nNTFY_SERVER="%s"\n' "$NTFY_TOPIC_VAL" "$NTFY_SERVER_VAL" > "$CONF" )
    chown root:root "$CONF"
    chmod 600 "$CONF"
fi

STAGE="install units"
echo "deploy: installing unit files -> /etc/systemd/system/"
install -m 644 -o root -g root "$SERVICE_SRC" "$TIMER_SRC" "$FAILED_SRC" /etc/systemd/system/

STAGE="reload + enable"
systemctl daemon-reload
# --now: re-arms the timer this script stopped above, not just the enable
# symlink. Reaching this line means every install/write before it
# succeeded; a failure at any earlier stage leaves the timer stopped
# instead, by design -- see the "stop timer" stage above.
systemctl enable --now jellyfin-state-dump.timer

STAGE="verify: loaded unit"
echo
echo "deploy: verifying the LOADED unit (not just the file on disk)"
loaded_exec=$(systemctl show -p ExecStart --value jellyfin-state-dump.service)
[[ "$loaded_exec" == *"/usr/local/bin/jellyfin-state-dump"* ]] \
    || { echo "deploy: loaded ExecStart does not reference the new path: $loaded_exec" >&2; exit 1; }
echo "  loaded ExecStart references the new path: OK"

STAGE="verify: ownership"
[[ "$(stat -c %U /usr/local/bin/jellyfin-state-dump)" == root ]] \
    || { echo "deploy: /usr/local/bin/jellyfin-state-dump is not root-owned" >&2; exit 1; }
echo "  script root-owned: OK"
[[ "$(stat -c %U:%a "$CONF")" == "root:600" ]] \
    || { echo "deploy: $CONF is not root-owned mode 600" >&2; exit 1; }
echo "  config root-owned, mode 600: OK"

STAGE="verify: functional run"
echo "deploy: triggering the service once now to prove it actually runs from the"
echo "deploy: new path under ProtectSystem=strict, rather than waiting for the"
echo "deploy: timer and finding out at 02:00 whether this deploy actually worked."
systemctl start jellyfin-state-dump.service
result=$(systemctl show -p Result --value jellyfin-state-dump.service)
if [[ "$result" != "success" ]]; then
    echo "deploy: the test run did not succeed (Result=$result)." >&2
    echo "deploy: journalctl -u jellyfin-state-dump.service -n 50 --no-pager" >&2
    exit 1
fi
echo "  test run: success"

echo
systemctl is-enabled jellyfin-state-dump.timer
systemctl list-timers jellyfin-state-dump.timer --no-pager
echo "deploy: done"
