# Claude usage tray (Windows)

The waybar claude widget for the Windows host of a WSL machine: a notification-area icon showing
your highest limit percentage, a hover summary, a click-open panel (limits with pace markers,
tokens by day and by model), and toasts when a limit gets high or resets. The data comes from
`claude_usage.py --json` inside WSL; this folder only draws it. Design and rationale:
[PLAYBOOK §9.31](../../PLAYBOOK.md).

Every command below runs **inside WSL**, from the repo root (`~/repos/dotfiles`).

## Install, update, remove

```sh
python3 windows/claude-usage/install.py                    # install, or update after a git pull
python3 windows/claude-usage/install.py --uninstall        # remove everything it installed
```

Re-run the plain install after any `git pull` that touches `ClaudeUsageTray.ps1`. Changes to
`claude_usage.py` need nothing: the tray runs it straight from this checkout. Install options
(combine freely; each re-run rewrites the config):

| Option | Effect |
|---|---|
| `--palette gruvbox` | panel colours from another `palettes.toml` palette (default: the one `theme` last applied, else nord) |
| `--interval 120` | seconds between data refreshes (default 60; the API itself is still called at most every 5 min) |
| `--no-notify` | no toasts |
| `--no-start` | install without starting it now |
| `--python /path/python3` | interpreter inside WSL (default `/usr/bin/python3`) |

## Start, stop, check

```sh
python3 windows/claude-usage/install.py --status   # running? config, last 5 log lines
python3 windows/claude-usage/install.py --stop     # stop now; it comes back at next logon
python3 windows/claude-usage/install.py --start    # start it again
```

It **starts at logon** from `Claude Usage.lnk` in the Startup folder (`Win+R` → `shell:startup`).
To stop it starting at logon, run `--uninstall`, or delete that shortcut. The tray menu's **Exit**
item stops it until the next logon.

## Using it

- **Icon** — your highest limit percentage, coloured green below 70%, amber from 70%, red from
  90%. **Grey** means the number isn't current: WSL is not running, the usage API is erroring
  (for example an expired token, which clears once a Claude Code session runs in WSL), or the
  collector failed. `–` means no data yet.
- **Hover** — one line per limit, with time to reset.
- **Left-click** — the panel. Click again, press `Esc` or click elsewhere to close it.
- **Right-click** — *Refresh now* (this one will start WSL if it is stopped), *Limits were reset
  early…* (restarts the pace markers after Anthropic resets limits ahead of schedule), *Open usage
  page*, *Send test notification*, *Open log*, *Exit*.

It never starts WSL on its own. While WSL is stopped it keeps showing the last data, greyed, and
the countdowns keep running.

## Notifications

One toast when a limit first reaches **70%**, **90%** and **100%**, and one when a limit that had
reached 70% rolls over into a fresh window ("Session limit has reset"). If Anthropic resets a limit
early, it can notify again on the way back up. Several crossings at once arrive as one toast.
Clicking a toast opens the panel.

- Test: right-click → *Send test notification*.
- Turn off: re-install with `--no-notify`.
- None arriving: check Settings → System → Notifications (notifications on, Do not disturb off).
  The sender appears as **Claude usage**. Windows can take a toast or two to pick up that name.

## Keeping the icon on the taskbar

Windows 11 puts every new tray icon in the overflow (`^`). **Drag it from the overflow onto the
taskbar once.** The tray also does this itself: Windows only records the icon's setting at
sign-out, so from your next sign-in the tray sets it to show on the taskbar. If you hide it
yourself afterwards (Settings → Personalization → Taskbar → Other system tray icons), it leaves
that choice alone.

## What it puts on the Windows side

| Where | What |
|---|---|
| `%LOCALAPPDATA%\ClaudeUsage\` | `ClaudeUsageTray.ps1` (a copy), `config.json`, `last.json` (last snapshot), `notify.json` (what has been notified), `icon.png`, `tray.log` |
| `shell:startup\Claude Usage.lnk` | the logon entry |
| `HKCU\Software\Classes\AppUserModelId\Microsoft.Explorer.Notification.{…}` | the toast sender's name and icon |
| `HKCU\Control Panel\NotifyIconSettings\<id>` | Windows' own record of the icon; the tray sets `IsPromoted` once |

`--uninstall` removes the first three. The last one belongs to Windows and is left in place.

## Troubleshooting

```sh
python3 windows/claude-usage/install.py --status                 # running? recent log
python3 waybar/.config/waybar/scripts/claude_usage.py --json     # what the tray is fed
cat /mnt/c/Users/$(cmd.exe /c 'echo %USERNAME%' 2>/dev/null | tr -d '\r')/AppData/Local/ClaudeUsage/tray.log
python3 windows/claude-usage/install.py                          # restart with a fresh copy
```

- **Icon says `error: snapshot schema …`**: the tray script is older than `claude_usage.py`.
  Re-run the install.
- **Grey icon with "stale: token expired"**: Claude Code refreshes its own login token; start a
  session in WSL. The tray never touches the token.
- **A console window flashes at logon**: that's the classic console being hidden by
  `-WindowStyle Hidden`, and it's expected. Don't swap in a "silent launcher" (an exe or VBScript
  shim): Defender treats those as malware (PLAYBOOK §9.31).

## Tests

```sh
python3 tests/claude_tray_test.py    # installer logic; PowerShell half needs WSL interop, else skipped
```

To look at the panel without the tray running (in PowerShell, from this folder):

```powershell
powershell -File ClaudeUsageTray.ps1 -Snapshot snap.json -RenderPanel panel.png -RenderIcon icon.png [-Idle]
```
