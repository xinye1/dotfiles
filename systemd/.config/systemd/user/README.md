# tp-backup systemd units

Backup regime for the trading-platform-v2 box. Design and recovery procedure live in that
repo — `docs/superpowers/specs/2026-08-24-local-backup-regime-design.md` and
`docs/runbooks/local-backup-restore.md`.

## Enable

    systemctl --user daemon-reload
    systemctl --user enable --now tp-backup-daily.timer tp-backup-substrate.timer \
                                  tp-backup-check.timer tp-backup-watchdog.timer

## Machine-local config is NOT in this repo

`~/.config/tp-backup/config` holds the repository host, key paths and the **ntfy topic** —
an alert credential. **This repository is public**, so that file must never be committed.
Create it from `config.example` in this directory, mode 600.

`~/.config/tp-backup/restic-password` likewise: it is the only thing that can decrypt the
backups, it lives in Bitwarden, and losing it is unrecoverable.

## Sharadar licence: raw vendor data never enters this repository

The Sharadar Personal Use licence requires deleting ALL raw Sharadar data (downloads, bulk
files, caches, extracts) within 30 days of cancelling. This repository is reached with an
APPEND-ONLY key and this box holds no maintenance key to prune it (trading-platform-v2 issue
752), so raw Sharadar data must never be written into a snapshot in the first place — there is
no way to take it back out afterwards. Every `restic_ro backup` call in `tp-backup` (vault/daily,
substrate, media) carries a shared `LICENCE_EXCLUDES` array — `--exclude $HOME/data/sharadar`,
`--exclude-if-present .sharadar-licence-extract`, `--exclude-caches` — and `restic_ro` itself
refuses (loudly) to run a `backup` invocation that does not carry it, so a future tier cannot
forget it. `git_capture` (the tier-2 untracked-file tar) separately refuses any file under
`$HOME/data/sharadar` or under a directory carrying the `.sharadar-licence-extract` marker,
logging a skip count rather than the paths. See `tests/tp_backup_test.sh`.

The weekly substrate tier (`tp-backup substrate`) also now includes
`$HOME/repos/trading-platform-v2/research/ws2_edge/.cache_ws2` (an EODHD-era edge-search cache,
confirmed by WS2 to hold no raw Sharadar data — issue 752 — and irreplaceable since the vendor
relationship that produced it is retired). It gets the same missing/empty refusal as the media
tier's source: present-but-empty must fail loudly rather than record a vacuous snapshot as a
success.

# herdr-session-backup

Hourly copy of herdr's `~/.config/herdr/session.json` into `~/.local/state/herdr-backup/` when it
changed; keeps 48; refuses (exit 1) to copy a session with no workspaces, so a wiped session cannot
rotate the good copies out. Not part of the tp-backup regime above. PLAYBOOK §9.30 has the restore.

    systemctl --user daemon-reload
    systemctl --user enable --now herdr-session-backup.timer
