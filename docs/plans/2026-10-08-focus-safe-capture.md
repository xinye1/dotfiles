# Focus-safe Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Screenshots taken at the keypress and cropped afterwards in satty, so a focus change can
no longer close the claude widget's tooltip or pause termtris before the picture is taken; plus
OCR, QR and screen recording, in the Print keys and the command palette.

**Architecture:** One Python tool, `capture.py`, replaces the three `screenshot_*.sh`. It always
runs `grim` first, then opens satty fullscreen on the shot. OCR/QR crop the shot and read the crop.
Recording runs wf-recorder detached, tracked by a pid file, with a waybar dot on signal 10.

**Tech Stack:** Python 3.14 stdlib; grim, satty 0.22, slurp, tesseract, zbarimg, wf-recorder,
wl-copy, sway, waybar.

**Spec:** `docs/specs/2026-10-08-focus-safe-capture-design.md`. Repo rules: `CLAUDE.md`, `PLAYBOOK.md`.

## Global Constraints

- grim runs before any picker (satty or slurp) in every screenshot, OCR and QR mode.
- A cancelled pick exits 0; failures notify critically (`notify-send -u critical -a capture`).
- Shots go to `~/Pictures/Screenshots/<YYYY-MM-DD_HH-MM-SS>.png`, recordings to
  `~/Videos/Recordings/<ts>.mp4`, and runtime files to `$XDG_RUNTIME_DIR/capture/`.
- waybar signal 10, always `pkill -RTMIN+10 -x waybar` (`-x` is load-bearing, PLAYBOOK §9.29).
- No literal hex anywhere (`check_hex.py`); waybar colours via `@critical`.
- Tests never touch the desktop: every external tool is a stub on PATH.
- Packages need Xinye's sudo: `satty tesseract tesseract-data-eng wf-recorder`; swappy removed after merge.
- Commit trailer:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01K3ULXJat1nthjNCUBQVarU
  ```

## Review Focus

1. **Two outputs connected.** Only the focused output is shot, so grim gets `-o <focused>`
   (`test_region_opens_satty_fullscreen_with_crop_on_the_shot`; the stub lists two outputs).
2. **Esc in satty** must save nothing and raise no toast (`test_enter_saves_and_esc_saves_nothing_silently`).
3. **A stale pid file** after a recorder crash must not keep the waybar dot lit
   (`test_a_stale_pid_reads_as_idle_and_is_removed`).
4. **A second Record while recording** must not start a second wf-recorder (`test_a_second_start_is_refused`).
5. **Palette rows that forget `--after-palette`** would put the palette in the shot (`MenuRowsTest`).

---

### Task 1: Probe satty and wf-recorder on this machine (`[needs-prototype]`)

**Files:** none committed. Findings go in the ledger and may adjust two constants in Task 2.

- [ ] **Step 1: Confirm the packages are installed** (Xinye runs the install; never `sudo` from here).

Run: `pacman -Q satty tesseract tesseract-data-eng wf-recorder`
Expected: four version lines. If any is missing, STOP and ask Xinye to run
`sudo pacman -S satty tesseract tesseract-data-eng wf-recorder`.

- [ ] **Step 2: satty's flag syntax.** Run `satty --help` and record: whether `--actions-on-enter`
takes a comma-separated list (`save-to-clipboard,save-to-file,exit`) or a repeated flag, and whether
`--fullscreen` takes a value. If the list form differs, Task 2's `SATTY_ENTER` constant, the
`save-to-file,exit` literal in `read_region()`, and the two test assertions naming those strings
change to match.

- [ ] **Step 3: satty fullscreen and Esc** (needs Xinye at the keyboard). Ask Xinye to run
`grim /tmp/p.png && satty --filename /tmp/p.png --fullscreen; echo "exit $?"`, press Esc, and report
the exit code, and whether the window covered the whole screen at scale 2. `capture.py` returns 0
after satty whatever satty's code is (`edit()` returns 0), so only a fullscreen problem matters, and
that is cosmetic: ledger it and continue.

- [ ] **Step 4: wf-recorder's encoder.** Run
`timeout -s INT 3 wf-recorder -c h264_vaapi -d /dev/dri/renderD128 -o eDP-1 -f /tmp/p.mp4; ls -l /tmp/p.mp4`.
Expected: a non-empty file. If it fails, set Task 2's `RECORD_CODEC` to
`["-c", "libx264", "-p", "preset=ultrafast"]` and re-run with that. Then delete `/tmp/p.png /tmp/p.mp4`.

---

### Task 2: `capture.py` and its suite

**Files:**
- Create: `sway/.config/sway/scripts/capture.py` (executable)
- Create: `tests/capture_test.py`
- Modify: `tests/theme_test.sh` (after the `menu_test.py` line)

**Interfaces:** Produces the CLI that Task 3 binds: `capture.py region|window|display [--after-palette]
[--delay N]`, `ocr|qr [--after-palette]`, `record region|display`, `record-stop`, `record-toggle`,
`record-status [--quiet | --idle]` (waybar JSON, or exit 0 while recording / while idle).

- [ ] **Step 1: Write the suite** as `tests/capture_test.py`:

```python
"""Tests for sway/.config/sway/scripts/capture.py (stdlib unittest).

Design: docs/specs/2026-10-08-focus-safe-capture-design.md. Every tool capture.py
runs -- grim, satty, slurp, swaymsg, tesseract, zbarimg, wf-recorder, wl-copy,
notify-send, pkill -- is a logging stub on PATH, and HOME/XDG_RUNTIME_DIR are
throwaway, so nothing here reaches the desktop. The log records call ORDER,
which is the point: the bug this tool fixes is grim running after a picker.

CAPTURE_BIN points the suite at another copy (the mutation check).
"""
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CAPTURE = Path(os.environ.get("CAPTURE_BIN", REPO / "sway/.config/sway/scripts/capture.py"))

STUB = r'''#!/usr/bin/env python3
# A logging stand-in for the tools capture.py runs. STUB_<NAME> env vars script it.
import json, os, signal, sys, time
name = os.path.basename(sys.argv[0]); args = sys.argv[1:]
reads = name in ("wl-copy",)
data = sys.stdin.buffer.read() if reads else b""
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps({"name": name, "argv": args, "stdin": data.decode("utf-8", "replace"),
                          "t": time.monotonic()}) + "\n")
mode = os.environ.get("STUB_" + name.upper().replace("-", "_"), "")
if name == "grim":
    if mode == "fail":
        sys.stderr.write("grim: no output\n"); sys.exit(1)
    open(args[-1], "wb").write(b"PNG")
elif name == "swaymsg":
    kind = args[args.index("-t") + 1]
    if kind == "get_outputs":
        print(json.dumps([{"name": "HDMI-A-1", "focused": False}, {"name": "eDP-1", "focused": True}]))
    else:
        print(os.environ.get("STUB_TREE", "{}"))
elif name == "satty":
    if mode == "enter":
        open(args[args.index("--output-filename") + 1], "wb").write(b"PNG")
elif name == "slurp":
    if mode == "esc":
        sys.exit(1)
    print("10,20 300x200")
elif name in ("tesseract", "zbarimg"):
    sys.stdout.write(mode)
elif name == "wf-recorder":
    def stop(*_):
        open(args[args.index("-f") + 1], "wb").write(b"MP4"); sys.exit(0)
    signal.signal(signal.SIGINT, stop)
    while True:
        time.sleep(0.05)
'''

TOOLS = ("grim", "swaymsg", "satty", "slurp", "tesseract", "zbarimg", "wf-recorder",
         "wl-copy", "notify-send", "pkill")

TREE = json.dumps({"type": "root", "nodes": [{"type": "output", "nodes": [{
    "type": "workspace", "nodes": [{"type": "con", "focused": False, "rect": {"x": 0, "y": 0, "width": 9, "height": 9}},
                                   {"type": "con", "focused": True,
                                    "rect": {"x": 40, "y": 50, "width": 800, "height": 600}}],
    "floating_nodes": []}]}]})


class Sandbox:
    def __init__(self, test, tools=TOOLS):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home, self.bin, self.run = self.root / "home", self.root / "bin", self.root / "run"
        for d in (self.home, self.bin, self.run):
            d.mkdir()
        for name in tools:
            stub = self.bin / name
            stub.write_text(STUB)
            stub.chmod(0o755)
        self.log = self.root / "log.jsonl"
        self.log.write_text("")

    def env(self, **extra):
        env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin",
               "XDG_RUNTIME_DIR": str(self.run), "WAYLAND_DISPLAY": "wayland-test",
               "STUB_LOG": str(self.log), "STUB_TREE": TREE}
        env.update(extra)
        return {k: v for k, v in env.items() if v is not None}

    def capture(self, *args, wait=True, **extra):
        self.log.write_text("")
        if not wait:
            return subprocess.Popen([sys.executable, str(CAPTURE), *args], env=self.env(**extra),
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return subprocess.run([sys.executable, str(CAPTURE), *args], env=self.env(**extra),
                              capture_output=True, text=True, timeout=30)

    def calls(self, name=None):
        rows = [json.loads(l) for l in self.log.read_text().splitlines()]
        return [r for r in rows if name is None or r["name"] == name]

    def order(self):
        return [c["name"] for c in self.calls() if c["name"] not in ("swaymsg", "notify-send", "pkill")]

    def shots(self):
        d = self.home / "Pictures" / "Screenshots"
        return sorted(p.name for p in d.glob("*.png")) if d.exists() else []


class ShootFirstTest(unittest.TestCase):
    """K1: the bug. grim must run before any picker, in every mode."""

    def test_grim_runs_before_satty_and_slurp_in_every_mode(self):
        for mode, extra in (("region", {}), ("window", {}), ("display", {}),
                            ("ocr", {"STUB_SATTY": "enter", "STUB_TESSERACT": "x"}),
                            ("qr", {"STUB_SATTY": "enter", "STUB_ZBARIMG": "x"})):
            with self.subTest(mode):
                sb = Sandbox(self)
                r = sb.capture(mode, **extra)
                self.assertEqual(r.returncode, 0, r.stderr)
                order = sb.order()
                self.assertEqual(order[0], "grim", order)
                self.assertNotIn("slurp", order)


class ScreenshotTest(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(self)

    def test_region_opens_satty_fullscreen_with_crop_on_the_shot(self):  # K3
        self.sb.capture("region")
        [grim], [satty] = self.sb.calls("grim"), self.sb.calls("satty")
        self.assertEqual(grim["argv"][:2], ["-o", "eDP-1"])
        a = satty["argv"]
        self.assertEqual(a[a.index("--filename") + 1], grim["argv"][-1])
        for flag in ("--fullscreen", "--initial-tool"):
            self.assertIn(flag, a)
        self.assertEqual(a[a.index("--initial-tool") + 1], "crop")
        self.assertEqual(a[a.index("--copy-command") + 1], "wl-copy")
        out = a[a.index("--output-filename") + 1]
        self.assertTrue(out.startswith(str(self.sb.home / "Pictures/Screenshots/")), out)
        self.assertIn("save-to-clipboard,save-to-file,exit", a)

    def test_display_and_window_do_not_start_in_crop(self):  # K3
        for mode in ("display", "window"):
            with self.subTest(mode):
                self.sb.capture(mode)
                [satty] = self.sb.calls("satty")
                self.assertNotIn("--initial-tool", satty["argv"])

    def test_window_shoots_the_focused_rect(self):  # K2
        self.sb.capture("window")
        [grim] = self.sb.calls("grim")
        self.assertEqual(grim["argv"][:2], ["-g", "40,50 800x600"])

    def test_window_with_nothing_focused_shoots_the_output_and_says_so(self):  # K2
        self.sb.capture("window", STUB_TREE=json.dumps({"type": "root", "focused": True, "nodes": []}))
        [grim] = self.sb.calls("grim")
        self.assertEqual(grim["argv"][:2], ["-o", "eDP-1"])
        [note] = self.sb.calls("notify-send")
        self.assertIn("no focused window", note["argv"][4])

    def test_enter_saves_and_esc_saves_nothing_silently(self):  # K4
        r = self.sb.capture("region", STUB_SATTY="enter")
        self.assertEqual((r.returncode, len(self.sb.shots())), (0, 1))
        r = self.sb.capture("region", STUB_SATTY="")
        self.assertEqual((r.returncode, len(self.sb.shots()), self.sb.calls("notify-send")), (0, 1, []))

    def test_the_runtime_shot_is_removed(self):
        self.sb.capture("display")
        self.assertEqual(list((self.sb.run / "capture").glob("shot-*")), [])

    def test_grim_failure_notifies(self):
        r = self.sb.capture("region", STUB_GRIM="fail")
        self.assertEqual(r.returncode, 1)
        [note] = self.sb.calls("notify-send")
        self.assertIn("grim failed", note["argv"][4])
        self.assertEqual(self.sb.calls("satty"), [])

    def test_without_satty_the_shot_goes_to_the_clipboard(self):  # K7
        sb = Sandbox(self, tools=[t for t in TOOLS if t != "satty"])
        r = sb.capture("region")
        self.assertEqual(r.returncode, 0, r.stderr)
        [copy] = sb.calls("wl-copy")
        self.assertEqual((copy["argv"], copy["stdin"]), (["--type", "image/png"], "PNG"))
        [note] = sb.calls("notify-send")
        self.assertIn("satty is not installed", note["argv"][4])

    def test_delay_waits_then_shoots(self):
        start = time.monotonic()
        self.sb.capture("display", "--delay", "1")
        self.assertGreaterEqual(time.monotonic() - start, 1.0)
        [note] = self.sb.calls("notify-send")
        self.assertIn("Capturing in 1 s", note["argv"][4])


class AfterPaletteTest(unittest.TestCase):  # K8
    def test_waits_for_the_palette_fuzzel_to_let_go(self):
        sb = Sandbox(self)
        lock = sb.run / "fuzzel-wayland-test.lock"
        fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        released = []
        def release():
            released.append(time.monotonic())
            os.close(fd)
        timer = threading.Timer(0.6, release)
        timer.start()
        self.addCleanup(timer.join)
        sb.capture("display", "--after-palette")
        [grim] = sb.calls("grim")
        self.assertGreater(grim["t"], released[0])


class ReadRegionTest(unittest.TestCase):  # K5
    def setUp(self):
        self.sb = Sandbox(self)

    def test_ocr_copies_the_text_and_shows_its_first_line(self):
        r = self.sb.capture("ocr", STUB_SATTY="enter", STUB_TESSERACT="hello world\nsecond\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        [copy] = self.sb.calls("wl-copy")
        self.assertEqual(copy["stdin"], "hello world\nsecond")
        [note] = self.sb.calls("notify-send")
        self.assertEqual(note["argv"][4:], ["Copied text", "hello world"])
        [satty] = self.sb.calls("satty")
        self.assertIn("save-to-file,exit", satty["argv"])
        self.assertNotIn("--copy-command", satty["argv"])

    def test_ocr_with_no_text_leaves_the_clipboard_alone(self):
        r = self.sb.capture("ocr", STUB_SATTY="enter", STUB_TESSERACT="  \n")
        self.assertEqual((r.returncode, self.sb.calls("wl-copy")), (0, []))
        [note] = self.sb.calls("notify-send")
        self.assertEqual(note["argv"][1], "normal")
        self.assertIn("no text found", note["argv"][4])

    def test_qr_copies_the_decoded_text(self):
        self.sb.capture("qr", STUB_SATTY="enter", STUB_ZBARIMG="https://example.org\n")
        [copy] = self.sb.calls("wl-copy")
        self.assertEqual(copy["stdin"], "https://example.org")

    def test_esc_in_the_crop_reads_nothing(self):
        r = self.sb.capture("ocr", STUB_SATTY="", STUB_TESSERACT="x")
        self.assertEqual((r.returncode, self.sb.calls("tesseract"), self.sb.calls("notify-send")),
                         (0, [], []))

    def test_missing_reader_names_the_package(self):
        sb = Sandbox(self, tools=[t for t in TOOLS if t != "tesseract"])
        r = sb.capture("ocr")
        self.assertEqual(r.returncode, 1)
        [note] = sb.calls("notify-send")
        self.assertIn("tesseract is not installed", note["argv"][4])
        self.assertEqual(sb.calls("grim"), [])


class RecordTest(unittest.TestCase):  # K6
    def setUp(self):
        self.sb = Sandbox(self)

    def status(self):
        r = self.sb.capture("record-status")
        return json.loads(r.stdout)

    def test_start_status_stop(self):
        r = self.sb.capture("record", "display")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.sb.calls("pkill")[0]["argv"], ["-RTMIN+10", "-x", "waybar"])
        time.sleep(0.3)
        self.assertEqual(self.status()["class"], "recording")
        self.assertEqual(self.sb.capture("record-status", "--quiet").returncode, 0)
        self.assertEqual(self.sb.capture("record-status", "--idle").returncode, 1)
        r = self.sb.capture("record-stop")
        self.assertEqual(r.returncode, 0, r.stderr)
        [note] = self.sb.calls("notify-send")
        self.assertEqual(note["argv"][4], "Recording saved")
        self.assertTrue(Path(note["argv"][5]).exists())
        self.assertEqual(self.status(), {"text": ""})
        self.assertEqual(self.sb.capture("record-status", "--quiet").returncode, 1)
        self.assertEqual(self.sb.capture("record-status", "--idle").returncode, 0)

    def test_region_uses_slurp_and_esc_records_nothing(self):
        r = self.sb.capture("record", "region", STUB_SLURP="esc")
        self.assertEqual((r.returncode, self.sb.calls("wf-recorder")), (0, []))
        self.sb.capture("record", "region")
        time.sleep(0.3)
        [rec] = self.sb.calls("wf-recorder")
        self.assertIn("-g", rec["argv"])
        self.assertEqual(rec["argv"][rec["argv"].index("-g") + 1], "10,20 300x200")
        self.sb.capture("record-stop")

    def test_a_second_start_is_refused(self):
        self.sb.capture("record", "display")
        time.sleep(0.3)
        r = self.sb.capture("record", "display")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.sb.calls("wf-recorder"), [])
        self.sb.capture("record-stop")

    def test_toggle_starts_then_stops(self):
        self.sb.capture("record-toggle")
        time.sleep(0.3)
        self.assertEqual(self.status()["class"], "recording")
        self.sb.capture("record-toggle")
        self.assertEqual(self.status(), {"text": ""})

    def test_a_stale_pid_reads_as_idle_and_is_removed(self):
        gone = subprocess.Popen(["true"])
        gone.wait()
        pidfile = self.sb.run / "capture" / "recording.pid"
        pidfile.parent.mkdir(parents=True)
        pidfile.write_text(f"{gone.pid}\n/x.mp4\n")
        self.assertEqual(self.status(), {"text": ""})
        self.assertFalse(pidfile.exists())


class MenuRowsTest(unittest.TestCase):
    """The palette rows must name capture.py with --after-palette (or a delay)."""

    def test_every_capture_screenshot_row_waits_for_the_palette(self):
        import tomllib
        rows = tomllib.loads((REPO / "sway/.config/sway/menu.toml").read_text())["action"]
        shots = [r for r in rows if "capture.py" in r["run"] and
                 r["run"].split()[1] in ("region", "window", "display", "ocr", "qr")]
        self.assertGreaterEqual(len(shots), 6)
        for row in shots:
            with self.subTest(row["label"]):
                self.assertIn("--after-palette", row["run"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it and watch it fail.**

Run: `python3 tests/capture_test.py`
Expected: every test fails or errors, because `capture.py` does not exist.

- [ ] **Step 3: Write `sway/.config/sway/scripts/capture.py`** (adjust `SATTY_ENTER` / `RECORD_CODEC`
per the Task 1 ledger lines), then `chmod +x` it:

```python
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
```

- [ ] **Step 4: Run it.**

Run: `python3 tests/capture_test.py -v`
Expected: 21 `ok` and one FAIL, `MenuRowsTest` (the palette rows arrive in Task 3). Any other
failure is a code problem.

- [ ] **Step 5: Hook into theme_test.sh.** After `python3 "$REPO/tests/menu_test.py" 2>/dev/null`, add:

```sh

# Focus-safe capture (capture.py): stubs only; a failure aborts. Its first
# assertion is the bug it fixes -- grim must run before any picker.
python3 "$REPO/tests/capture_test.py" 2>/dev/null
```

Do not run `theme_test.sh` yet: `MenuRowsTest` is red until Task 3, and theme_test would abort on it.

- [ ] **Step 6: Commit** `capture.py`, `tests/capture_test.py`, `tests/theme_test.sh` with
`feat(capture): capture.py — shoot at the keypress, crop in satty; OCR, QR, recording` and the trailer.

---

### Task 3: Wire it in: palette rows, keys, waybar; retire the shell scripts

**Files:**
- Modify: `sway/.config/sway/menu.toml` (replace from `# --- Capture ---` up to `# --- Clipboard ---`)
- Modify: `sway/.config/sway/config.d/default` (the `# Screenshots` block, ~lines 332-343)
- Modify: `waybar/.config/waybar/config` (`modules-right`, new `custom/recording`)
- Modify: `waybar/.config/waybar/style.css` (both module selector lists, plus one rule)
- Modify: `tests/menu_test.py` (delete `class CaptureCancelTest`)
- Delete: `sway/.config/sway/scripts/screenshot_region.sh`, `screenshot_window.sh`, `screenshot_display.sh`

- [ ] **Step 1: Palette rows.** Replace the Capture block of `menu.toml` with:

```toml
# --- Capture (capture.py) ---
# The shot is taken first -- for these rows, the moment the palette has gone --
# and cropped afterwards in satty, so nothing a focus change does can spoil it
# (docs/specs/2026-10-08-focus-safe-capture-design.md). Print, Ctrl+Print and
# Shift+Print do the same without a palette in between.

[[action]]
group = "Capture"
label = "Region"
icon = "applets-screenshooter"
keywords = ["screenshot", "crop"]
run = "~/.config/sway/scripts/capture.py region --after-palette"

[[action]]
group = "Capture"
label = "Focused window"
icon = "applets-screenshooter"
keywords = ["screenshot"]
run = "~/.config/sway/scripts/capture.py window --after-palette"

[[action]]
group = "Capture"
label = "Display"
icon = "applets-screenshooter"
keywords = ["screenshot"]
run = "~/.config/sway/scripts/capture.py display --after-palette"

[[action]]
group = "Capture"
label = "Display in 5 s"
icon = "alarm-clock"
keywords = ["screenshot", "timer", "delay"]
run = "~/.config/sway/scripts/capture.py display --after-palette --delay 5"

[[action]]
group = "Capture"
label = "Text from region (OCR)"
icon = "edit-find"
keywords = ["ocr", "copy text"]
run = "~/.config/sway/scripts/capture.py ocr --after-palette"

[[action]]
group = "Capture"
label = "QR code from region"
icon = "view-barcode-qr"
keywords = ["qr", "barcode"]
run = "~/.config/sway/scripts/capture.py qr --after-palette"

[[action]]
group = "Capture"
label = "Record region"
icon = "media-record"
keywords = ["video", "screencast"]
when = "~/.config/sway/scripts/capture.py record-status --idle"
run = "~/.config/sway/scripts/capture.py record region"

[[action]]
group = "Capture"
label = "Record display"
icon = "media-record"
keywords = ["video", "screencast"]
when = "~/.config/sway/scripts/capture.py record-status --idle"
run = "~/.config/sway/scripts/capture.py record display"

[[action]]
group = "Capture"
label = "Stop recording"
icon = "media-playback-stop"
keywords = ["video", "screencast"]
when = "~/.config/sway/scripts/capture.py record-status --quiet"
run = "~/.config/sway/scripts/capture.py record-stop"
```

- [ ] **Step 2: Retire `CaptureCancelTest`** in `tests/menu_test.py`: delete the whole class. It
exercised the shell scripts deleted below; `capture_test.py`'s
`test_enter_saves_and_esc_saves_nothing_silently` and
`test_region_uses_slurp_and_esc_records_nothing` now hold the same contract (a cancel exits 0).

- [ ] **Step 3: Keys.** Replace the `# Screenshots` block's bindings (keep the section header) with:

```
    # Shot first, at the keypress, then cropped in satty: a Print key moves no
    # focus, so a tooltip stays open and termtris keeps playing until the shot
    # is taken (capture.py; docs/specs/2026-10-08-focus-safe-capture-design.md).
    bindsym print exec ~/.config/sway/scripts/capture.py region
    # The focused window, instantly (no picking)
    bindsym Ctrl+Print exec ~/.config/sway/scripts/capture.py window
    # The focused display
    bindsym Shift+Print exec ~/.config/sway/scripts/capture.py display
    # Start a region recording, or stop the one running (waybar shows a red dot)
    bindsym $mod+Print exec ~/.config/sway/scripts/capture.py record-toggle
```

(Ctrl+Shift+Print is removed: Enter in satty already copies.)

- [ ] **Step 4: waybar.** In `modules-right`, insert `"custom/recording",` before `"custom/herdr",`.
Add the module after `custom/herdr`'s block:

```json
    // Recording indicator: a red dot while capture.py records, nothing otherwise.
    // capture.py pokes signal 10 on start and stop; the interval catches a
    // recorder that died (capture.py removes its stale pid file).
    "custom/recording": {
        "exec": "~/.config/sway/scripts/capture.py record-status",
        "return-type": "json",
        "interval": 10,
        "signal": 10,
        "exec-on-event": false,
        "format": "{}",
        "on-click": "~/.config/sway/scripts/capture.py record-stop"
    },
```

In `style.css`, add `#custom-recording,` after `#custom-herdr,` in **both** module selector lists
(the padding list and the background/border/box-shadow list; `check_waybar_paint.py` reads the
modules from the config and fails on one missing from the second list), and add next to the
`#custom-herdr.*` rules:

```css
#custom-recording.recording { color: @critical; }
```

- [ ] **Step 5: Delete the scripts and find leftovers.**

```bash
git rm -q sway/.config/sway/scripts/screenshot_region.sh sway/.config/sway/scripts/screenshot_window.sh sway/.config/sway/scripts/screenshot_display.sh
git grep -n 'screenshot_\(region\|window\|display\)' -- ':!docs/'
```
Expected: only PLAYBOOK.md (~490 and ~871), which Task 4 rewrites.

- [ ] **Step 6: Run the suites.**

Run: `python3 tests/capture_test.py && python3 tests/menu_test.py && python3 tests/check_hex.py . && sh tests/theme_test.sh`
Expected: all green; capture 22 tests; theme_test PASS.

- [ ] **Step 7: Apply and verify (§9.29).**

```bash
sway --validate -c ~/.config/sway/config && swaymsg reload
pgrep -xc swayidle; pgrep -xc waybar_run.sh            # 1 and 1
sup=$(pgrep -x waybar_run.sh); for p in $(pgrep -x waybar); do awk '/^PPid/{print $2}' /proc/$p/status; done   # each == $sup
sh tests/check_consumers.sh                            # PASS, incl. waybar paint and menu --check
python3 waybar/.config/waybar/scripts/keyhint.py --print | grep -i print
```
Expected: validate silent; counts 1/1; PPids match; consumers PASS; keyhint lists Print, Ctrl+Print,
Shift+Print and Super+Print with capture.py.

- [ ] **Step 8: Commit** `sway/.config/sway`, `waybar/.config/waybar`, `tests/menu_test.py` (use
`git add -A` on those paths for the deletions) with
`feat(capture): Print keys, palette rows and waybar dot use capture.py; retire screenshot_*.sh`.

---

### Task 4: Docs, packages, mutation proof, smoke

**Files:** `PLAYBOOK.md`, `CLAUDE.md`, `packages.txt`

- [ ] **Step 1: packages.txt.** Remove `swappy`; add `satty`, `tesseract`, `tesseract-data-eng`,
`wf-recorder`, keeping the file's alphabetical order.

- [ ] **Step 2: PLAYBOOK.** Rewrite the ~490 table row to:
`| Screenshot | Print / Ctrl+Print / Shift+Print | Region / focused window / display. Shot first at the keypress, then cropped in satty (capture.py) — §9.32 |`.
Rewrite the ~871 sentence to say the shell scripts were replaced by `capture.py`, which reads
`theme.gen.env` the same way for slurp's recording box. Append a new
`### 9.32 Capture: shoot first, select on the freeze` that holds: the spec §0 cause (slurp's overlay
takes the keyboard and covers waybar; grim used to run after it); the rule "grim before any picker";
the palette's `--after-palette` wait; recording's pid file and signal 10; and the smoke list below.

- [ ] **Step 3: CLAUDE.md.** Add `python3 tests/capture_test.py # focus-safe capture; also run by theme_test.sh`
to the suite list, and a Verify paragraph: "**Run `tests/capture_test.py` after any edit to
`capture.py`.** Every tool it runs is a stub that logs call order; its first assertion is the bug it
exists for: grim before any picker. `CAPTURE_BIN` points it at a copy for mutation checks (§9.32)."

- [ ] **Step 4: Mutation proof.** Make a copy of capture.py for each mutant below. The suite must
FAIL on every copy (`CAPTURE_BIN=<copy> python3 tests/capture_test.py`):
  - **slurp-first:** insert `subprocess.run(["slurp"], capture_output=True)` before `if not shoot(mode, shot):` in `screenshot()`
  - **no-palette-wait:** replace the `if "--after-palette" in rest:` block with `pass`
  - **stale-pid-kept:** in `recording()`, drop the `pidfile().unlink(missing_ok=True)` before `return None`
  - **focus-rect-ignored:** `rect = None` in place of `rect = focused_rect()`

- [ ] **Step 5: Run everything and commit.**

Run: `python3 tests/capture_test.py && python3 tests/menu_test.py && sh tests/theme_test.sh && sh tests/check_consumers.sh`
Commit `PLAYBOOK.md CLAUDE.md packages.txt` with `docs(capture): PLAYBOOK §9.32, CLAUDE.md test line, packages`.

- [ ] **Step 6: Manual smoke (Xinye).**
  1. Hover the claude widget so its tooltip opens, press Print, crop, Enter: the tooltip is in the pasted image.
  2. In a termtris game, press Ctrl+Print: the bricks are in the image; the game paused only after.
  3. Super+Space → Capture › Text from region (OCR) on some terminal text → paste it.
  4. Super+Print, wait 5 s, Super+Print: a notification gives the mp4 path; the waybar dot came and went.
  5. After merge: `sudo pacman -Rns swappy`.
