#!/usr/bin/env bash
#
# tp_backup_test.sh — regression tests for the git-capture half of
# `bin/.local/bin/tp-backup`.
#
# Sandboxed, like theme_test.sh: every repo is built fresh under a throwaway
# $HOME in a temp dir, and only the `__capture` subcommand runs. That path
# touches git and the state directory and never reaches restic, ssh or the
# network, so this cannot read from or write to the real backup repository.
#
# The case that matters is the outage of 2026-08-28..09-03. An agent session had
# created a git worktree inside its scratchpad under /tmp; /tmp is tmpfs, so the
# reboot on 08-28 erased the directory while the registration survived in
# <repo>/.git/worktrees/<name>. `git -C <gone> status` exits 128, and because
# git_capture runs FIRST in cmd_daily, `set -e` killed the run before the vault
# snapshot -- for eight consecutive days, with no laptop backup taken.
#
# Point TPB_BIN at another copy to test it (used to prove these assertions can
# actually fail; see the positive control in the PR).
#
#   sh tests/tp_backup_test.sh
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TPB_BIN="${TPB_BIN:-$REPO_ROOT/bin/.local/bin/tp-backup}"

pass=0; fail=0
ok()   { printf '  ok    %s\n' "$1"; pass=$((pass + 1)); }
bad()  { printf '  FAIL  %s\n' "$1"; fail=$((fail + 1)); }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (want [$3], got [$2])"; fi; }

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT

G="git -c user.email=t@test -c user.name=test -c init.defaultBranch=main -c commit.gpgsign=false"

# ── build the sandbox ───────────────────────────────────────────────────────
FAKE_HOME="$SANDBOX/home"
mkdir -p "$FAKE_HOME/repos"

# A healthy repo with one commit.
$G init -q "$FAKE_HOME/repos/alpha"
$G -C "$FAKE_HOME/repos/alpha" commit -q --allow-empty -m "alpha init"

# A repo carrying an ORPHANED worktree registration: the worktree is created in
# a directory that is then deleted, exactly as the tmpfs wipe did to df-ssd.
$G init -q "$FAKE_HOME/repos/beta"
$G -C "$FAKE_HOME/repos/beta" commit -q --allow-empty -m "beta init"
$G -C "$FAKE_HOME/repos/beta" worktree add -q "$SANDBOX/volatile/wt" -b sidebranch
rm -rf "$SANDBOX/volatile"          # <- the reboot

# Minimal machine-local config. The capture path never uses these values, but
# the script refuses to start without a readable config.
mkdir -p "$FAKE_HOME/.config/tp-backup"
cat > "$FAKE_HOME/.config/tp-backup/config" <<'CONF'
TPB_HOST=example.invalid
TPB_REPO_PATH=backups/none
TPB_SSH_PORT=23
TPB_KEY_BACKUP=/dev/null
TPB_KEY_MAINT=/dev/null
TPB_PASSWORD_FILE=/dev/null
TPB_RESTIC=/bin/false
NTFY_TOPIC=
NTFY_SERVER=http://127.0.0.1:1
CONF

echo "tp-backup capture tests  (bin: $TPB_BIN)"

# ── run the capture ─────────────────────────────────────────────────────────
out="$SANDBOX/capture.out"
env HOME="$FAKE_HOME" XDG_STATE_HOME="$FAKE_HOME/.local/state" \
    TPB_CONF="$FAKE_HOME/.config/tp-backup/config" \
    "$TPB_BIN" __capture >"$out" 2>&1
rc=$?

CUR="$FAKE_HOME/.local/state/tp-backup/git-capture/current"

# The headline assertion: an orphaned registration must NOT fail the capture.
# Pre-fix this exited 128 and no vault snapshot was ever attempted.
check "orphaned worktree does not fail the capture" "$rc" "0"

# The healthy repo must still be captured. A crash on beta used to mean whatever
# sorted after it was never captured at all.
if [ -s "$CUR/alpha/log.txt" ]; then ok "healthy repo captured despite the orphan"
else bad "healthy repo captured despite the orphan (no alpha/log.txt)"; fi

if [ -f "$CUR/beta/branch.txt" ]; then ok "main worktree of the affected repo captured"
else bad "main worktree of the affected repo captured (no beta/branch.txt)"; fi

# "Nothing to capture" is recorded as a state, never conflated with success by
# silence: the marker names the cure.
if [ -f "$CUR/beta__wt/MISSING_WORKTREE" ]; then ok "orphan recorded as MISSING_WORKTREE"
else bad "orphan recorded as MISSING_WORKTREE (marker absent)"; fi

if grep -q 'worktree prune' "$CUR/beta__wt/MISSING_WORKTREE" 2>/dev/null
then ok "marker names the cure (git worktree prune)"
else bad "marker names the cure (git worktree prune)"; fi

if grep -q 'stale worktree registration' "$out"
then ok "stale registration warned on stderr"
else bad "stale registration warned on stderr"; fi

# A completed capture stamps its tier; the watchdog reads this to decide
# staleness, so a capture that "succeeded" without stamping would go unnoticed.
if [ -f "$FAKE_HOME/.local/state/tp-backup/last-success-git-capture" ]
then ok "git-capture tier stamped"
else bad "git-capture tier stamped"; fi

# ── the vault must survive a capture failure ────────────────────────────────
# The outage's real damage came from ordering, not from the defect: Tier 2 ran
# first under `set -e`, so a fault in an unrelated repo meant no snapshot at all.
# Here the capture is made to fail for a reason the MISSING_WORKTREE guard does
# NOT cover -- an unreadable tree -- and the assertion is that restic still ran
# and the run still reported failure afterwards.
if [ "$(id -u)" = "0" ]; then
    printf '\n  skip  vault-survives-capture-failure (running as root bypasses the mode bits)\n'
else
    H2="$SANDBOX/home2"; mkdir -p "$H2/repos"
    $G init -q "$H2/repos/gamma"
    $G -C "$H2/repos/gamma" commit -q --allow-empty -m "gamma init"
    cp -r "$FAKE_HOME/.config" "$H2/.config"
    # A real restic would need the network; /bin/true stands in for a snapshot
    # that succeeds, which is exactly what this case needs to observe.
    sed -i 's#^TPB_RESTIC=.*#TPB_RESTIC=/bin/true#' "$H2/.config/tp-backup/config"

    # Fail inside a WORKTREE, not the repo directory. `for repo in ~/repos/*/`
    # cannot even expand an unreadable repo, so mode 000 there is skipped in
    # silence and reaches no git command at all. A worktree still satisfies the
    # `-d` test (that needs the parent's execute bit, not the directory's own),
    # so the capture enters it and `git -C` fails with the same 128 the outage
    # produced -- by a route the MISSING_WORKTREE guard deliberately does not cover.
    $G -C "$H2/repos/gamma" worktree add -q "$H2/wt-locked" -b locked
    chmod 000 "$H2/wt-locked"

    env HOME="$H2" XDG_STATE_HOME="$H2/.local/state" \
        TPB_CONF="$H2/.config/tp-backup/config" \
        "$TPB_BIN" daily >"$SANDBOX/daily.out" 2>&1
    drc=$?
    chmod 755 "$H2/wt-locked"            # so the sandbox can be removed

    if [ "$drc" -ne 0 ]; then ok "capture failure still fails the run"
    else bad "capture failure still fails the run (exit $drc)"; fi

    if [ -f "$H2/.local/state/tp-backup/last-success-vault" ]
    then ok "vault snapshot taken despite the capture failure"
    else bad "vault snapshot taken despite the capture failure (no vault stamp)"; fi

    if [ ! -f "$H2/.local/state/tp-backup/last-success-git-capture" ]
    then ok "failed capture does not stamp its own tier"
    else bad "failed capture does not stamp its own tier (stamped anyway)"; fi

    # The message must say the snapshot happened, so a red unit is never read as
    # "no backup" -- the misreading this ordering change exists to prevent.
    if grep -q 'vault snapshot WAS still taken' "$SANDBOX/daily.out"
    then ok "failure message states the snapshot was still taken"
    else bad "failure message states the snapshot was still taken"; fi
fi

# ── SSD cold-storage reminder ───────────────────────────────────────────────
# The cold leg is a REMINDER, never a failure: a detached disk is the design
# working. So every case asserts the watchdog still exits 0. Folding this into
# the staleness list would make the unit red for weeks at a stretch and teach the
# operator to ignore the one alert that still speaks when the rest have gone
# quiet -- which is how the 2026-08-28 outage survived eight days.
#
# No restic needed: with the binary stubbed the freshness probe fails and falls
# back to the recorded stamp, which is the path that matters when the disk is
# absent. Presence is faked with a readable `config` file, which is precisely
# what the attached / not-attached branch keys on.
H3="$SANDBOX/home3"; S3="$H3/.local/state/tp-backup"
mkdir -p "$H3/repos" "$S3"
cp -r "$FAKE_HOME/.config" "$H3/.config"
NOW=$(date +%s)
for t in vault git-capture jellyfin substrate media check rehearsal; do echo "$NOW" > "$S3/last-success-$t"; done
FAKE_SSD="$SANDBOX/fake-ssd"; mkdir -p "$FAKE_SSD"; : > "$FAKE_SSD/config"
ABSENT_SSD="$SANDBOX/no-such-disk"

run_wd() {   # $1 = path to treat as the SSD repo
    env HOME="$H3" XDG_STATE_HOME="$H3/.local/state" \
        TPB_CONF="$H3/.config/tp-backup/config" \
        TPB_SSD_REPO="$1" TPB_SSD_MAX_H=720 \
        "$TPB_BIN" watchdog >"$SANDBOX/wd.out" 2>&1
}

echo "$NOW" > "$S3/last-success-ssd"
run_wd "$ABSENT_SSD"; rc=$?
check "fresh cold leg does not fire the reminder" "$rc" "0"
if grep -q 'cold-storage' "$SANDBOX/wd.out"; then bad "fresh cold leg stays silent (it fired anyway)"
else ok "fresh cold leg stays silent"; fi

echo "$(( NOW - 800 * 3600 ))" > "$S3/last-success-ssd"
run_wd "$ABSENT_SSD"; rc=$?
check "stale cold leg still exits 0 (reminder, not failure)" "$rc" "0"
if grep -q 'cold-storage leg is 33d old' "$SANDBOX/wd.out"; then ok "reminder reports the age in days"
else bad "reminder reports the age in days"; fi
if grep -q 'Attach the disk first' "$SANDBOX/wd.out"; then ok "absent disk tells the operator to attach it"
else bad "absent disk tells the operator to attach it"; fi

run_wd "$FAKE_SSD"; rc=$?
check "attached-but-stale still exits 0" "$rc" "0"
if grep -q 'disk is attached now' "$SANDBOX/wd.out"; then ok "attached disk says to just run the sync"
else bad "attached disk says to just run the sync"; fi

rm -f "$S3/last-success-ssd"
run_wd "$ABSENT_SSD"; rc=$?
check "never-recorded cold leg still exits 0" "$rc" "0"
if grep -q 'never been recorded' "$SANDBOX/wd.out"; then ok "never-recorded cold leg is reported, not skipped"
else bad "never-recorded cold leg is reported, not skipped"; fi

# A genuinely stale REAL tier must still fail, with the cold leg alongside it.
echo "$(( NOW - 100 * 3600 ))" > "$S3/last-success-vault"
run_wd "$ABSENT_SSD"; rc=$?
check "a real stale tier still fails the unit" "$rc" "1"
if grep -q 'STALE: vault' "$SANDBOX/wd.out"; then ok "real staleness still reported as STALE"
else bad "real staleness still reported as STALE"; fi

# ── SSD restore-drill precondition ──────────────────────────────────────────
# The full drill needs a real restic repository, so it is exercised against the
# live disk rather than here. What IS testable hermetically is the precondition,
# and it is the one that matters: asking for the cold-leg drill with no disk
# attached must fail loudly and name the cure. Falling through to the Hetzner
# repository would return a cheerful PASS that proves the wrong leg -- a drill
# reporting success for a copy it never opened is worse than no drill.
env HOME="$H3" XDG_STATE_HOME="$H3/.local/state" \
    TPB_CONF="$H3/.config/tp-backup/config" TPB_SSD_REPO="$ABSENT_SSD" \
    "$TPB_BIN" rehearsal --ssd >"$SANDBOX/reh.out" 2>&1
rc=$?
if [ "$rc" -ne 0 ]; then ok "rehearsal --ssd fails when the disk is absent"
else bad "rehearsal --ssd fails when the disk is absent (exit $rc)"; fi
if grep -q 'attach the disk' "$SANDBOX/reh.out"; then ok "absent-disk drill names the cure"
else bad "absent-disk drill names the cure"; fi
if grep -q 'rehearsal --ssd' "$SANDBOX/reh.out"; then ok "failure is attributed to the cold leg, not Hetzner"
else bad "failure is attributed to the cold leg, not Hetzner"; fi

# A mistyped flag must NOT silently run the other leg. `rehearsal --sdd` used to
# print "rehearsal(Hetzner) OK" and exit 0 -- a green cold-leg drill against a
# repository it never opened. Caught in review, reproduced against the live disk.
for badarg in --sdd --SSD -ssd ssd; do
    env HOME="$H3" XDG_STATE_HOME="$H3/.local/state" \
        TPB_CONF="$H3/.config/tp-backup/config" TPB_SSD_REPO="$ABSENT_SSD" \
        "$TPB_BIN" rehearsal "$badarg" >"$SANDBOX/bad.out" 2>&1
    rc=$?
    if [ "$rc" -eq 2 ] && grep -q 'unknown argument' "$SANDBOX/bad.out"
    then ok "rehearsal rejects '$badarg' instead of running Hetzner"
    else bad "rehearsal rejects '$badarg' (exit $rc)"; fi
    if grep -q 'rehearsal(Hetzner) OK' "$SANDBOX/bad.out"
    then bad "'$badarg' must not report a Hetzner pass"; fi
done

env HOME="$H3" XDG_STATE_HOME="$H3/.local/state" \
    TPB_CONF="$H3/.config/tp-backup/config" TPB_SSD_REPO="$ABSENT_SSD" \
    "$TPB_BIN" rehearsal --ssd extra >"$SANDBOX/bad.out" 2>&1
rc=$?
if [ "$rc" -eq 2 ] && grep -q 'too many arguments' "$SANDBOX/bad.out"
then ok "rehearsal rejects surplus arguments"
else bad "rehearsal rejects surplus arguments (exit $rc)"; fi

# ── Sharadar licence exclusions (issue 752) ─────────────────────────────────
# Personal Use licence: raw Sharadar data must be deleted within 30 days of
# cancelling, and this restic repository is APPEND-ONLY (cannot be pruned), so
# raw Sharadar data must never enter a snapshot. `restic` and `mountpoint` are
# both stubbed on PATH here -- nothing below reaches real restic, ssh or the
# network, and no real disk is mounted or unmounted. The restic stub records
# every argv it is called with (one call per invocation, one arg per line) so
# the assertions below inspect what tp-backup actually asked restic to do.
STUBBIN="$SANDBOX/stubbin"; mkdir -p "$STUBBIN"
RESTIC_LOG="$SANDBOX/restic-calls.log"

cat > "$STUBBIN/restic-stub" <<'STUB'
#!/usr/bin/env bash
{
    printf -- '--- call ---\n'
    for a in "$@"; do printf '%s\n' "$a"; done
} >> "${TPB_TEST_RESTIC_LOG:?TPB_TEST_RESTIC_LOG not set}"
exit 0
STUB
chmod +x "$STUBBIN/restic-stub"

# cmd_media's `mountpoint -q "$MNT"` needs a real mount to pass; stubbing the
# command on PATH tests the rest of the tier hermetically instead of bind-
# mounting a real filesystem.
cat > "$STUBBIN/mountpoint" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$STUBBIN/mountpoint"

H4="$SANDBOX/home4"
mkdir -p "$H4/repos" "$H4/.config/tp-backup"
cp "$FAKE_HOME/.config/tp-backup/config" "$H4/.config/tp-backup/config"
sed -i "s#^TPB_RESTIC=.*#TPB_RESTIC=$STUBBIN/restic-stub#" "$H4/.config/tp-backup/config"

# cmd_substrate's source paths are hardcoded, not overridable via env -- so the
# fake HOME must actually hold them, including the new WS2 cache this task adds.
WS2_CACHE="$H4/repos/trading-platform-v2/research/ws2_edge/.cache_ws2"
mkdir -p "$WS2_CACHE"
echo x > "$WS2_CACHE/frame.parquet"

# cmd_media's source IS overridable.
FAKE_MEDIA="$H4/media-src"; mkdir -p "$FAKE_MEDIA"; echo x > "$FAKE_MEDIA/clip.mp4"

run_tier() {   # $1 = tp-backup subcommand; truncates $RESTIC_LOG before running
    : > "$RESTIC_LOG"
    env HOME="$H4" XDG_STATE_HOME="$H4/.local/state" \
        TPB_CONF="$H4/.config/tp-backup/config" \
        TPB_MEDIA_SRC="$FAKE_MEDIA" TPB_MEDIA_MOUNT="$FAKE_MEDIA" \
        TPB_TEST_RESTIC_LOG="$RESTIC_LOG" \
        PATH="$STUBBIN:$PATH" \
        "$TPB_BIN" "$@" >"$SANDBOX/tier.out" 2>&1
}

assert_excludes() {   # $1 = label for the ok/bad line
    if grep -qxF -- "--exclude" "$RESTIC_LOG" \
       && grep -qxF -- "$H4/data/sharadar" "$RESTIC_LOG" \
       && grep -qxF -- "--exclude-if-present" "$RESTIC_LOG" \
       && grep -qxF -- ".sharadar-licence-extract" "$RESTIC_LOG" \
       && grep -qxF -- "--exclude-caches" "$RESTIC_LOG"
    then ok "$1: recorded restic argv carries all 3 licence excludes"
    else bad "$1: recorded restic argv carries all 3 licence excludes"; fi
}

run_tier daily;     rc=$?; check "daily tier runs clean under the stub"     "$rc" "0"
assert_excludes "vault/daily"

run_tier substrate; rc=$?; check "substrate tier runs clean under the stub" "$rc" "0"
assert_excludes "substrate"
if grep -qxF -- "$WS2_CACHE" "$RESTIC_LOG"
then ok "substrate argv includes the new .cache_ws2 path"
else bad "substrate argv includes the new .cache_ws2 path"; fi

run_tier media;     rc=$?; check "media tier runs clean under the stub"     "$rc" "0"
assert_excludes "media"

# ── substrate's missing/vacuous guard on the new path ───────────────────────
# A bare `restic backup` on an existing-but-empty directory exits 0 and records
# a real (if pointless) snapshot -- proved separately against real restic 0.19.1
# -- so this guard cannot rely on restic to notice an emptied cache for us.
rm -rf "$WS2_CACHE"
run_tier substrate; rc=$?
if [ "$rc" -ne 0 ] && grep -q 'missing' "$SANDBOX/tier.out"
then ok "substrate refuses a missing .cache_ws2"
else bad "substrate refuses a missing .cache_ws2 (exit $rc)"; fi

mkdir -p "$WS2_CACHE"   # present but empty
run_tier substrate; rc=$?
if [ "$rc" -ne 0 ] && grep -q 'vacuous' "$SANDBOX/tier.out"
then ok "substrate refuses an empty .cache_ws2"
else bad "substrate refuses an empty .cache_ws2 (exit $rc)"; fi
echo x > "$WS2_CACHE/frame.parquet"   # restore, in case anything runs after this block

# ── git-capture must refuse Sharadar-marked / Sharadar-root paths ───────────
H5="$SANDBOX/home5"
mkdir -p "$H5/repos" "$H5/data/sharadar"
cp -r "$H4/.config" "$H5/.config"
echo leak > "$H5/data/sharadar/leak.txt"

$G init -q "$H5/repos/delta"
$G -C "$H5/repos/delta" commit -q --allow-empty -m "delta init"
mkdir -p "$H5/repos/delta/extract"
: > "$H5/repos/delta/extract/.sharadar-licence-extract"
echo raw > "$H5/repos/delta/extract/leaked.csv"
echo ok  > "$H5/repos/delta/normal.txt"
ln -s "$H5/data/sharadar/leak.txt" "$H5/repos/delta/leaked-symlink"

env HOME="$H5" XDG_STATE_HOME="$H5/.local/state" \
    TPB_CONF="$H5/.config/tp-backup/config" \
    "$TPB_BIN" __capture >"$SANDBOX/capture5.out" 2>&1
rc=$?
check "git-capture with Sharadar-marked content still exits 0" "$rc" "0"

TARBALL="$H5/.local/state/tp-backup/git-capture/current/delta/untracked.tar.gz"
if [ -f "$TARBALL" ]; then
    TLIST="$(tar -tzf "$TARBALL" 2>/dev/null)"
    if printf '%s\n' "$TLIST" | grep -qx 'normal.txt'
    then ok "git-capture still captures a normal untracked file"
    else bad "git-capture still captures a normal untracked file"; fi

    if printf '%s\n' "$TLIST" | grep -q 'extract/leaked.csv'
    then bad "git-capture must NOT tar a file under a .sharadar-licence-extract marker"
    else ok "git-capture excludes a file under a .sharadar-licence-extract marker"; fi

    if printf '%s\n' "$TLIST" | grep -q 'leaked-symlink'
    then bad "git-capture must NOT tar a symlink resolving into \$HOME/data/sharadar"
    else ok "git-capture excludes a path resolving into \$HOME/data/sharadar"; fi
else
    bad "git-capture produced an untracked.tar.gz to inspect (file absent)"
fi

# 3, not 2: extract/leaked.csv, leaked-symlink, AND the marker file itself
# (extract/.sharadar-licence-extract is untracked too, and sits under the
# directory it marks, so it is consistently skipped along with the rest).
if grep -q 'skipped 3 untracked file' "$SANDBOX/capture5.out"
then ok "git-capture logs the skip COUNT on stderr (3 files, no paths/contents)"
else bad "git-capture logs the skip COUNT on stderr (3 files, no paths/contents)"; fi

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
