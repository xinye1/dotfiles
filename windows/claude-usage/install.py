#!/usr/bin/env python3
"""Install, update or remove the Claude usage tray on the Windows host.

Run from inside WSL, in the distro whose ~/.claude the tray should report on:

    python3 windows/claude-usage/install.py               # install or update
    python3 windows/claude-usage/install.py --palette gruvbox
    python3 windows/claude-usage/install.py --uninstall
    python3 windows/claude-usage/install.py --status | --start | --stop

Operational cheat sheet: README.md beside this file. What it does
(PLAYBOOK §9.31): copies ClaudeUsageTray.ps1 to
%LOCALAPPDATA%\\ClaudeUsage, writes config.json beside it — this distro, the
python3 and claude_usage.py the tray runs through `wsl.exe --exec`, and the
palette's roles rendered from palettes.toml, so the repo itself carries no hex
— puts a shortcut in the Startup folder, and restarts the tray so the update
takes effect. Re-running it is the update procedure after a `git pull` that
touches the tray script; Python-side changes need nothing, because the tray
runs claude_usage.py straight from this checkout.

Stdlib only, like claude_usage.py.
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
TRAY_PS1 = HERE / "ClaudeUsageTray.ps1"
COLLECTOR = REPO / "waybar" / ".config" / "waybar" / "scripts" / "claude_usage.py"
PALETTES = REPO / "palettes.toml"
DEFAULT_PALETTE = "nord"      # the repo's default and original (PLAYBOOK §3)
APP_DIR = "ClaudeUsage"       # under %LOCALAPPDATA%
SHORTCUT = "Claude Usage.lnk"
EXIT_EVENT = r"Local\ClaudeUsageTray.Exit"   # ClaudeUsageTray.ps1 listens on it
# Every file the tray or this script creates in APP_DIR: --uninstall removes
# exactly these and then the directory only if that left it empty.
OWNED = ("ClaudeUsageTray.ps1", "config.json", "last.json", "notify.json",
         "icon.png", "tray.log", "tray.log.1")
TOAST_NAME = "Claude usage"   # the tray's $ToastName; --uninstall finds its keys by it


def active_palette(env):
    """The palette `theme` last applied on this machine, else the default.

    `theme` keeps it in $XDG_STATE_HOME/theme/palette (PLAYBOOK §3.3). Inside
    WSL that file usually does not exist — `theme` runs on the sway desktop —
    so the default is the normal case here, not a fallback for a broken one.
    """
    state = Path(env.get("XDG_STATE_HOME") or Path(env.get("HOME", "~")).expanduser() / ".local" / "state")
    try:
        name = (state / "theme" / "palette").read_text().strip()
    except OSError:
        return DEFAULT_PALETTE
    return name or DEFAULT_PALETTE


def palette_roles(path, name):
    """The palette's top-level roles (bg, fg, indicator, ...) as {role: hex}.

    Sub-tables such as `[nord.ansi]` are the terminal ramp, not roles, and
    are left out. An unknown name is an error naming the choices, the same
    courtesy `theme` extends.
    """
    with open(path, "rb") as fh:
        table = tomllib.load(fh)
    if name not in table:
        raise SystemExit(f"install: no palette {name!r} in {path} "
                         f"(choices: {', '.join(sorted(table))})")
    return {k: v for k, v in table[name].items() if isinstance(v, str)}


def build_config(distro, python, script, interval, palette, roles, notify=True):
    return {"distro": distro, "python": python, "script": str(script),
            "interval": interval, "notify": notify, "palette": palette,
            "theme": roles}


def default_python():
    """The interpreter the tray runs claude_usage.py with.

    /usr/bin/python3 when it exists, deliberately not sys.executable: an
    installer run from inside an activated venv would otherwise pin the tray
    to that venv, and it would break the day the venv is deleted.
    """
    return "/usr/bin/python3" if Path("/usr/bin/python3").exists() else (
        shutil.which("python3") or sys.executable)


def ps_literal(s):
    """A PowerShell single-quoted string literal: nothing inside expands."""
    return "'" + str(s).replace("'", "''") + "'"


def tray_command_args(ps1_windows_path):
    """powershell.exe's arguments, as the Startup shortcut passes them.

    The shortcut targets conhost.exe rather than powershell.exe. With the
    default terminal set to Windows Terminal (or "let Windows decide", which
    is the same thing on Windows 11), powershell.exe started from a shortcut
    opens a Terminal window that `-WindowStyle Hidden` cannot hide; conhost
    keeps it in the classic console, which `-WindowStyle Hidden` can.
    `conhost --headless` would hide it entirely but is refused (access denied)
    on managed machines, and a compiled hidden launcher is exactly what
    antivirus flags — both tried, PLAYBOOK §9.31.
    """
    return ("powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden "
            f'-File "{ps1_windows_path}"')


def stop_snippet():
    """PowerShell that asks a running tray to exit, then makes sure.

    Signalling the tray's named event lets it remove its own icon; a killed
    process leaves a ghost icon in the notification area until hovered.
    """
    return f"""
$ev = $null
if ([Threading.EventWaitHandle]::TryOpenExisting({ps_literal(EXIT_EVENT)}, [ref]$ev)) {{ [void]$ev.Set(); $ev.Dispose() }}
$deadline = (Get-Date).AddSeconds(5)
do {{
    $left = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
              Where-Object {{ $_.CommandLine -like '*ClaudeUsageTray.ps1*' }})
    if ($left.Count -eq 0) {{ break }}
    Start-Sleep -Milliseconds 200
}} while ((Get-Date) -lt $deadline)
foreach ($p in $left) {{ Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }}
"""


def install_snippet(lnk, app_dir, ps1, start):
    s = stop_snippet() + f"""
$sh = New-Object -ComObject WScript.Shell
$l = $sh.CreateShortcut({ps_literal(lnk)})
$l.TargetPath = Join-Path $env:SystemRoot 'System32\\conhost.exe'
$l.Arguments = {ps_literal(tray_command_args(ps1))}
$l.WorkingDirectory = {ps_literal(app_dir)}
$l.WindowStyle = 7
$l.Description = 'Claude Code usage in the notification area (dotfiles windows/claude-usage)'
$l.Save()
"""
    if start:
        s += f"Start-Process -FilePath {ps_literal(lnk)}\n"
    return s


def uninstall_snippet(lnk):
    """Remove the shortcut, and the toast names the tray registered — found by
    their DisplayName, so a key some other program owns is never touched."""
    return f"""
Remove-Item -LiteralPath {ps_literal(lnk)} -ErrorAction SilentlyContinue
Get-ChildItem 'HKCU:\\Software\\Classes\\AppUserModelId' -ErrorAction SilentlyContinue |
    Where-Object {{ $_.PSChildName -like 'Microsoft.Explorer.Notification.*' -and
                   $_.GetValue('DisplayName') -eq {ps_literal(TOAST_NAME)} }} |
    Remove-Item -Recurse -Force
"""


def status_snippet():
    return """
@(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
  Where-Object { $_.CommandLine -like '*ClaudeUsageTray.ps1*' }) | ForEach-Object { "pid=$($_.ProcessId)" }
"""


def status_report(ps_out, app):
    """Plain-language state from the process list and the files in APP_DIR."""
    pids = [l.split("=", 1)[1] for l in ps_out.splitlines() if l.startswith("pid=")]
    lines = [f"tray: {'running, pid ' + ', '.join(pids) if pids else 'not running'}"]
    if not (app / "config.json").exists():
        lines.append("install: not installed")
        return "\n".join(lines)
    try:
        cfg = json.loads((app / "config.json").read_text())
        lines.append(f"config: distro {cfg.get('distro')!r}, every {cfg.get('interval')}s, "
                     f"notifications {'on' if cfg.get('notify', True) else 'off'}, "
                     f"palette {cfg.get('palette')!r}")
    except (OSError, ValueError) as e:
        lines.append(f"config: unreadable ({e})")
    log = app / "tray.log"
    if log.exists():
        lines.append("log (last 5):")
        lines += ["  " + l for l in log.read_text(errors="replace").splitlines()[-5:]]
    return "\n".join(lines)


def run_powershell(script):
    """Run a PowerShell script on the host. -EncodedCommand, because quoting a
    script through wsl -> powershell.exe's command-line parser is a bug farm."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                        "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                       capture_output=True, text=True, cwd="/mnt/c")
    if r.returncode != 0:
        raise SystemExit(f"install: powershell.exe failed ({r.returncode}):\n{r.stderr.strip()}")
    return r.stdout.replace("\r", "")


def windows_folders():
    out = run_powershell("[Environment]::GetFolderPath('LocalApplicationData'); "
                         "[Environment]::GetFolderPath('Startup')")
    local, startup = [l for l in out.splitlines() if l.strip()][:2]
    return local.strip(), startup.strip()


def to_wsl(path):
    return Path(subprocess.run(["wslpath", "-u", path], capture_output=True,
                               text=True, check=True).stdout.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--palette", help="palette from palettes.toml "
                    "(default: the one `theme` last applied, else nord)")
    ap.add_argument("--interval", type=int, default=60,
                    help="seconds between collector runs (default 60; the API "
                    "itself is still fetched at most every 300s)")
    ap.add_argument("--python", default=None, help="python3 inside WSL")
    ap.add_argument("--no-notify", action="store_true",
                    help="no toasts at 70/90/100%% or on a limit's reset")
    ap.add_argument("--no-start", action="store_true", help="install without starting")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--uninstall", action="store_true",
                      help="stop the tray; remove its shortcut, files and toast name")
    mode.add_argument("--start", action="store_true", help="start the installed tray")
    mode.add_argument("--stop", action="store_true", help="stop the tray (it returns at next logon)")
    mode.add_argument("--status", action="store_true", help="is it running, and the log's tail")
    args = ap.parse_args(argv)

    distro = os.environ.get("WSL_DISTRO_NAME")
    if not distro or not shutil.which("powershell.exe"):
        raise SystemExit("install: run this inside WSL with Windows interop enabled "
                         "(WSL_DISTRO_NAME unset or powershell.exe not on PATH)")
    if args.interval < 15:
        raise SystemExit("install: --interval below 15s would only burn CPU; the "
                         "API is cached for 300s regardless")

    local, startup = windows_folders()
    app_win = f"{local}\\{APP_DIR}"
    lnk_win = f"{startup}\\{SHORTCUT}"
    app = to_wsl(local) / APP_DIR

    if args.stop:
        run_powershell(stop_snippet())
        print("install: tray stopped; it starts again at next logon (or --start)")
        return
    if args.start:
        if not (app / TRAY_PS1.name).exists():
            raise SystemExit("install: not installed; run install.py without flags first")
        run_powershell(f"Start-Process -FilePath {ps_literal(lnk_win)}\n")
        print("install: tray started")
        return
    if args.status:
        print(status_report(run_powershell(status_snippet()), app))
        return
    if args.uninstall:
        run_powershell(stop_snippet() + uninstall_snippet(lnk_win))
        for name in OWNED:
            (app / name).unlink(missing_ok=True)
        try:
            app.rmdir()
        except OSError:
            pass   # something we did not create is in there: leave it
        print(f"install: removed the tray, its shortcut and {app_win}")
        return

    palette = args.palette or active_palette(os.environ)
    config = build_config(distro, args.python or default_python(), COLLECTOR,
                          args.interval, palette, palette_roles(PALETTES, palette),
                          notify=not args.no_notify)
    app.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TRAY_PS1, app / TRAY_PS1.name)
    (app / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    ps1_win = f"{app_win}\\{TRAY_PS1.name}"
    run_powershell(install_snippet(lnk_win, app_win, ps1_win, not args.no_start))
    print(f"install: tray script and config in {app_win}")
    print(f"install: starts at logon via {lnk_win}")
    print(f"install: reports on WSL distro {distro!r} with palette {palette!r}"
          + ("" if args.no_start else "; started"))
    print("install: notifications " + ("off" if args.no_notify else
          "on (70/90/100% and resets; right-click > Send test notification)"))
    print("install: a new icon starts in the overflow (^): drag it onto the taskbar once, or "
          "the tray moves itself out after your next sign-in (README.md)")


if __name__ == "__main__":
    main()
