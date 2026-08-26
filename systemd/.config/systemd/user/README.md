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
