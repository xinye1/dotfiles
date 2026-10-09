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
  capture.py record-stop | record-toggle | record-status

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
RECORD_CODEC = ["-c", "h264_vaapi"]
RECORD_SETTLE = 0.3  # how long wf-recorder gets to die on a bad GPU/option before we call it started
# satty: Enter copies and saves, then exits; Esc just exits (its default).
SATTY_ENTER = ["--actions-on-enter", "save-to-clipboard,save-to-file,exit"]


def render_node():
    """The first /dev/dri/renderD* node, else renderD128 (CAPTURE_DRI_DIR is the test seam)."""
    dri = Path(os.environ.get("CAPTURE_DRI_DIR", "/dev/dri"))
    nodes = sorted(dri.glob("renderD*"))
    return str(nodes[0]) if nodes else "/dev/dri/renderD128"


def home():
    return Path(os.environ["HOME"])


def runtime():
    d = Path(os.environ["XDG_RUNTIME_DIR"]) / "capture"
    d.mkdir(parents=True, exist_ok=True)
    return d


def stamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def notify(summary, body="", urgency="critical", expire_ms=None):
    expire = ["-t", str(expire_ms)] if expire_ms else []
    try:
        subprocess.run(["notify-send", "-u", urgency, "-a", "capture", *expire, summary, body],
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
    fell_back = False
    if mode == "window":
        rect = focused_rect()
        if rect:
            return run_grim(["-g", rect], path)
        fell_back = True
    output = focused_output()
    if not output:
        notify("Capture: no focused output", "nothing was captured")
        return False
    if not run_grim(["-o", output], path):
        return False
    if fell_back:  # after grim, or the toast lands in the very picture
        notify("Capture: no focused window", "captured the whole display instead", "normal")
    return True


def run_grim(args, path):
    r = subprocess.run(["grim", *args, str(path)], stderr=subprocess.PIPE, text=True)
    if r.returncode != 0 or not path.exists():
        notify("Capture: grim failed", (r.stderr or "").strip()[-300:])
        return False
    return True


def run_satty(argv):
    """Run satty; a non-zero exit is a failure worth a toast. Esc is satty's
    `exit` action and exits 0, so a cancelled pick stays silent.

    stdout and stderr go to a file, never a pipe: satty's Enter runs wl-copy,
    which forks to serve the clipboard and keeps both, so whoever reads a pipe
    to EOF (this script, or the palette) hangs until the next copy. The file also keeps what satty said when a save
    fails and the user can only Esc out (satty then exits 0)."""
    logpath = runtime() / "satty.log"
    with open(logpath, "w") as log:
        r = subprocess.run(argv, stdout=log, stderr=log)
    if r.returncode != 0:
        notify("Capture: satty failed", logpath.read_text(errors="replace").strip()[-300:])
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
    return 0 if run_satty(argv) else 1


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
        if not run_satty(["satty", "--filename", str(shot), "--fullscreen", "--initial-tool", "crop",
                          "--output-filename", str(crop),
                          "--actions-on-enter", "save-to-file,exit"]):
            return 1
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
    """The process exists AND is a wf-recorder: a reused pid is a stranger,
    which must neither keep the waybar dot lit nor ever receive our SIGINT."""
    try:
        os.kill(pid, 0)
        comm = Path(f"/proc/{pid}/comm").read_text().strip()
    except (ProcessLookupError, FileNotFoundError):
        return False
    except PermissionError:
        return False
    return comm == "wf-recorder"


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
    if recording():  # one appeared while slurp had the screen
        notify("Capture: already recording", "stop it first (Super+Print)", "normal")
        return 1
    # "w": the failure toast below quotes this log's tail, so a stale run's log is not needed.
    logpath = runtime() / "recording.log"
    with open(logpath, "w") as log:
        proc = subprocess.Popen(["wf-recorder", *RECORD_CODEC, "-d", render_node(), *where,
                                 "-f", str(path)],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                start_new_session=True)
    time.sleep(RECORD_SETTLE)
    if proc.poll() is not None:
        notify("Capture: recording failed to start",
               logpath.read_text(errors="replace").strip()[-300:])
        path.unlink(missing_ok=True)
        return 1
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
    if Path(path).exists() and Path(path).stat().st_size > 0:
        notify("Recording saved", path, "normal")
        return 0
    notify("Capture: recording failed", f"no video was written to {path}")
    return 1


def record_status():
    """waybar JSON. (menu.toml's record rows test the pidfile with sh instead:
    python startup is ~60 ms per row on every palette open.)"""
    rec = recording()
    if rec:
        print(json.dumps({"text": "●", "class": "recording",
                          "tooltip": f"Recording to {rec[1]}\nSuper+Print to stop"}))
    else:
        print(json.dumps({"text": ""}))
    return 0


USAGE = ("usage: capture.py region|window|display [--after-palette] [--delay N]\n"
         "       capture.py ocr|qr [--after-palette]\n"
         "       capture.py record region|display | record-stop | record-toggle"
         " | record-status")


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
                notify(f"Capturing in {delay} s", "", "low", max((delay - 1) * 1000, 1))
                time.sleep(delay)
            return read_region(mode) if mode in ("ocr", "qr") else screenshot(mode)
        if mode == "record" and rest in (["region"], ["display"]):
            return record(rest[0])
        if mode == "record-stop" and not rest:
            return record_stop()
        if mode == "record-toggle" and not rest:
            return record_stop() if recording() else record("region")
        if mode == "record-status" and not rest:
            return record_status()
    except Exception as e:  # a key must never fail in silence
        notify("Capture failed", f"{type(e).__name__}: {e}")
        return 1
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
