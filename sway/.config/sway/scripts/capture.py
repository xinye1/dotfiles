#!/usr/bin/env python3
"""capture — screenshots taken at the keypress, then cropped on the frozen shot.

Design: docs/specs/2026-10-08-focus-safe-capture-design.md. The old scripts ran
slurp first and grim after the selection; slurp's overlay takes the keyboard
and covers waybar, so termtris paused (it pauses on focus loss) and the claude
widget's tooltip closed before the picture was taken. Here grim always runs
first -- a Print key is a sway binding and moves no focus -- and the region is
chosen afterwards in satty, on the frozen image.

  capture.py region|window|display [--after-palette] [--delay N]
  capture.py ocr|qr [--after-palette]
  capture.py record region|display
  capture.py record-stop | record-toggle | record-status [--quiet | --idle]

A cancelled pick (Esc in satty or slurp) exits 0: the command palette raises a
failure notification on any non-zero exit (palette spec §4.2).
"""
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

FUZZEL_WAIT = 2.0
REPAINT = 0.15
WAYBAR_SIGNAL = 10
# Settled by the plan's Task 1 probe on this machine's Intel GPU.
RECORD_CODEC = ["-c", "h264_vaapi", "-d", "/dev/dri/renderD128"]
# satty: Enter copies and saves, then exits; Esc just exits (its default).
SATTY_ENTER = ["--actions-on-enter", "save-to-clipboard,save-to-file,exit"]


def home():
    return Path(os.environ["HOME"])


def runtime():
    d = Path(os.environ["XDG_RUNTIME_DIR"]) / "capture"
    d.mkdir(parents=True, exist_ok=True)
    return d


def stamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def notify(summary, body="", urgency="critical"):
    try:
        subprocess.run(["notify-send", "-u", urgency, "-a", "capture", summary, body],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass
    print(f"capture: {summary}" + (f": {body}" if body else ""), file=sys.stderr)


def have(tool):
    return shutil.which(tool) is not None


def sway(kind):
    out = subprocess.run(["swaymsg", "-r", "-t", kind], capture_output=True, text=True)
    return json.loads(out.stdout or "null")


def focused_output():
    for output in sway("get_outputs") or []:
        if output.get("focused"):
            return output["name"]
    return None


def focused_rect():
    """The focused window's rectangle as grim's "x,y wxh", or None when the
    focus is on something that is not a window (an empty workspace)."""
    stack = [sway("get_tree") or {}]
    while stack:
        node = stack.pop()
        if node.get("focused") and node.get("type") in ("con", "floating_con"):
            r = node["rect"]
            return f"{r['x']},{r['y']} {r['width']}x{r['height']}"
        stack.extend(node.get("nodes", []) + node.get("floating_nodes", []))
    return None


def wait_for_fuzzel():
    """Wait (<= FUZZEL_WAIT s) until the palette's fuzzel has let go of its
    instance lock -- it is still on screen until then -- and give sway a moment
    to repaint and return focus. Same lock as menu.py's wait_for_fuzzel."""
    runtime_dir, display = os.environ.get("XDG_RUNTIME_DIR"), os.environ.get("WAYLAND_DISPLAY")
    if runtime_dir and display:
        lock = Path(runtime_dir) / f"fuzzel-{display}.lock"
        deadline = time.monotonic() + FUZZEL_WAIT
        while time.monotonic() < deadline:
            try:
                fd = os.open(lock, os.O_RDONLY)
            except FileNotFoundError:
                break
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(0.05)
            finally:
                os.close(fd)
    time.sleep(REPAINT)


def shoot(mode, path):
    """grim, now, before anything can move focus. Returns False after notifying."""
    if mode == "window":
        rect = focused_rect()
        if rect:
            return run_grim(["-g", rect], path)
        notify("Capture: no focused window", "captured the whole display instead", "normal")
    output = focused_output()
    if not output:
        notify("Capture: no focused output", "nothing was captured")
        return False
    return run_grim(["-o", output], path)


def run_grim(args, path):
    r = subprocess.run(["grim", *args, str(path)], stderr=subprocess.PIPE, text=True)
    if r.returncode != 0 or not path.exists():
        notify("Capture: grim failed", (r.stderr or "").strip()[-300:])
        return False
    return True


def edit(shot, crop):
    """satty fullscreen on the frozen shot. Enter copies + saves; Esc exits."""
    target = home() / "Pictures" / "Screenshots"
    target.mkdir(parents=True, exist_ok=True)
    argv = ["satty", "--filename", str(shot), "--fullscreen",
            "--output-filename", str(target / f"{stamp()}.png"),
            "--copy-command", "wl-copy", *SATTY_ENTER]
    if crop:
        argv += ["--initial-tool", "crop"]
    subprocess.run(argv)
    return 0


def fallback(shot):
    """No satty: the shot goes straight to the clipboard, so the key still
    captures something."""
    notify("Capture: satty is not installed",
           "the whole screen was copied to the clipboard; install satty to crop and annotate")
    with open(shot, "rb") as f:
        subprocess.run(["wl-copy", "--type", "image/png"], stdin=f)
    return 0


def screenshot(mode):
    shot = runtime() / f"shot-{stamp()}-{os.getpid()}.png"
    try:
        if not shoot(mode, shot):
            return 1
        if not have("satty"):
            return fallback(shot)
        return edit(shot, crop=(mode == "region"))
    finally:
        shot.unlink(missing_ok=True)


def read_region(kind):
    """OCR or QR: shoot, crop in satty, read the crop."""
    tool = {"ocr": "tesseract", "qr": "zbarimg"}[kind]
    for needed in ("satty", tool):
        if not have(needed):
            notify(f"Capture: {needed} is not installed", f"install {needed} for {kind.upper()}")
            return 1
    shot = runtime() / f"shot-{stamp()}-{os.getpid()}.png"
    crop = runtime() / f"crop-{stamp()}-{os.getpid()}.png"
    try:
        if not shoot("display", shot):
            return 1
        subprocess.run(["satty", "--filename", str(shot), "--fullscreen", "--initial-tool", "crop",
                        "--output-filename", str(crop),
                        "--actions-on-enter", "save-to-file,exit"])
        if not crop.exists():
            return 0  # Esc: nothing chosen
        if kind == "ocr":
            r = subprocess.run(["tesseract", str(crop), "-", "-l", "eng"],
                               capture_output=True, text=True)
        else:
            r = subprocess.run(["zbarimg", "--raw", "-q", str(crop)], capture_output=True, text=True)
        text = r.stdout.strip()
        if not text:
            notify("Capture: no text found" if kind == "ocr" else "Capture: no QR code found",
                   "the clipboard was left alone", "normal")
            return 0
        subprocess.run(["wl-copy"], input=text, text=True)
        notify("Copied text" if kind == "ocr" else "Copied QR code", text.splitlines()[0][:120],
               "normal")
        return 0
    finally:
        shot.unlink(missing_ok=True)
        crop.unlink(missing_ok=True)


# --- recording ---

def pidfile():
    return runtime() / "recording.pid"


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def recording():
    """(pid, path) of the running recorder, or None. A pid file whose process
    is gone is removed, so the waybar dot cannot outlive the recorder."""
    try:
        pid, path = pidfile().read_text().split("\n")[:2]
        pid = int(pid)
    except (FileNotFoundError, ValueError):
        return None
    if alive(pid):
        return pid, path
    pidfile().unlink(missing_ok=True)
    return None


def signal_waybar():
    # -x is load-bearing: a pattern would also kill waybar's supervisor (PLAYBOOK §9.29).
    subprocess.run(["pkill", f"-RTMIN+{WAYBAR_SIGNAL}", "-x", "waybar"])


def theme_colours():
    env = {}
    try:
        for line in (home() / ".config/sway/theme.gen.env").read_text().splitlines():
            key, _, value = line.partition("=")
            if key.isupper() and value:
                env[key] = value
    except OSError:
        pass
    return env


def record(kind):
    if not have("wf-recorder"):
        notify("Capture: wf-recorder is not installed", "install wf-recorder to record")
        return 1
    if recording():
        notify("Capture: already recording", "stop it first (Super+Print)", "normal")
        return 1
    if kind == "region":
        c = theme_colours()
        colours = []
        if c.get("BG") and c.get("ACCENT"):
            colours = ["-b", f"{c['BG']}cc", "-c", c["ACCENT"], "-s", f"{c['ACCENT']}22"]
        r = subprocess.run(["slurp", *colours], capture_output=True, text=True)
        if r.returncode != 0 or not r.stdout.strip():
            return 0  # Esc
        where = ["-g", r.stdout.strip()]
    else:
        output = focused_output()
        if not output:
            notify("Capture: no focused output", "nothing was recorded")
            return 1
        where = ["-o", output]
    target = home() / "Videos" / "Recordings"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{stamp()}.mp4"
    log = open(runtime() / "recording.log", "w")
    proc = subprocess.Popen(["wf-recorder", *RECORD_CODEC, *where, "-f", str(path)],
                            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                            start_new_session=True)
    pidfile().write_text(f"{proc.pid}\n{path}\n")
    signal_waybar()
    return 0


def record_stop():
    rec = recording()
    if not rec:
        notify("Capture: not recording", "", "normal")
        signal_waybar()
        return 0
    pid, path = rec
    os.kill(pid, signal.SIGINT)  # wf-recorder finalises the file on SIGINT
    deadline = time.monotonic() + 10
    while alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    pidfile().unlink(missing_ok=True)
    signal_waybar()
    notify("Recording saved", path, "normal")
    return 0


def record_status(flag):
    """waybar JSON; or, for menu.toml `when` tests, an exit code: --quiet is 0
    while recording, --idle is 0 while not (a `when` cannot start with `!`)."""
    rec = recording()
    if flag == "--quiet":
        return 0 if rec else 1
    if flag == "--idle":
        return 1 if rec else 0
    if rec:
        print(json.dumps({"text": "●", "class": "recording",
                          "tooltip": f"Recording to {rec[1]}\nSuper+Print to stop"}))
    else:
        print(json.dumps({"text": ""}))
    return 0


USAGE = ("usage: capture.py region|window|display [--after-palette] [--delay N]\n"
         "       capture.py ocr|qr [--after-palette]\n"
         "       capture.py record region|display | record-stop | record-toggle"
         " | record-status [--quiet | --idle]")


def main(argv):
    if not argv:
        print(USAGE, file=sys.stderr)
        return 2
    mode, rest = argv[0], argv[1:]
    try:
        if mode in ("region", "window", "display", "ocr", "qr"):
            delay = 0
            if "--delay" in rest:
                delay = int(rest[rest.index("--delay") + 1])
            if "--after-palette" in rest:
                wait_for_fuzzel()
            if delay:
                notify(f"Capturing in {delay} s", "", "low")
                time.sleep(delay)
            return read_region(mode) if mode in ("ocr", "qr") else screenshot(mode)
        if mode == "record" and rest in (["region"], ["display"]):
            return record(rest[0])
        if mode == "record-stop" and not rest:
            return record_stop()
        if mode == "record-toggle" and not rest:
            return record_stop() if recording() else record("region")
        if mode == "record-status" and rest in ([], ["--quiet"], ["--idle"]):
            return record_status(rest[0] if rest else None)
    except Exception as e:  # a key must never fail in silence
        notify("Capture failed", f"{type(e).__name__}: {e}")
        return 1
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
