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
    if mode == "fail":
        sys.stderr.write("satty: boom\n"); sys.exit(1)
    if mode == "enter":
        open(args[args.index("--output-filename") + 1], "wb").write(b"PNG")
elif name == "slurp":
    if mode == "esc":
        sys.exit(1)
    if os.environ.get("STUB_SLURP_PIDFILE"):  # a rival recorder appears while the user picks
        open(os.environ["STUB_SLURP_PIDFILE"], "w").write(os.environ["STUB_SLURP_PIDDATA"])
    print("10,20 300x200")
elif name in ("tesseract", "zbarimg"):
    sys.stdout.write(mode)
elif name == "wf-recorder":
    if mode == "fail":
        sys.stderr.write("wf-recorder: no gpu\n"); sys.exit(1)
    def stop(*_):
        if mode != "nofile":
            open(args[args.index("-f") + 1], "wb").write(b"MP4")
        sys.exit(0)
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
            # An absolute interpreter, so the stubs need nothing from /usr/bin.
            stub.write_text(STUB.replace("#!/usr/bin/env python3", f"#!{sys.executable}", 1))
            stub.chmod(0o755)
        self.log = self.root / "log.jsonl"
        self.log.write_text("")

    def env(self, **extra):
        # PATH is the stub directory ONLY. With /usr/bin on it, an installed
        # satty or tesseract answered the "not installed" tests -- real satty
        # ran inside the suite, and the tests passed only while it was absent.
        env = {"HOME": str(self.home), "PATH": str(self.bin),
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


class SandboxTest(unittest.TestCase):
    def test_the_sandbox_path_holds_only_stubs(self):
        sb = Sandbox(self)
        self.assertEqual(sb.env()["PATH"], str(sb.bin))
        r = subprocess.run(["/bin/sh", "-c", "command -v satty tesseract zbarimg wf-recorder"],
                           env=dict(sb.env(), PATH=str(sb.bin)), capture_output=True, text=True)
        for line in r.stdout.split():
            self.assertTrue(line.startswith(str(sb.bin)), line)


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

    def test_the_no_window_toast_comes_after_grim(self):  # finding 6
        self.sb.capture("window", STUB_TREE=json.dumps({"type": "root", "nodes": []}))
        names = [c["name"] for c in self.sb.calls() if c["name"] in ("grim", "notify-send")]
        self.assertEqual(names, ["grim", "notify-send"])
        self.sb.capture("window", STUB_TREE=json.dumps({"type": "root", "nodes": []}), STUB_GRIM="fail")
        [note] = self.sb.calls("notify-send")
        self.assertIn("grim failed", note["argv"][4])

    def test_enter_saves_and_esc_saves_nothing_silently(self):  # K4
        r = self.sb.capture("region", STUB_SATTY="enter")
        self.assertEqual((r.returncode, len(self.sb.shots())), (0, 1))
        r = self.sb.capture("region", STUB_SATTY="")
        self.assertEqual((r.returncode, len(self.sb.shots()), self.sb.calls("notify-send")), (0, 1, []))

    def test_satty_failure_is_reported_but_esc_stays_silent(self):  # finding 2
        r = self.sb.capture("region", STUB_SATTY="fail")
        self.assertEqual(r.returncode, 1)
        [note] = self.sb.calls("notify-send")
        self.assertIn("satty failed", note["argv"][4])
        self.assertIn("boom", note["argv"][5])
        self.assertEqual(list((self.sb.run / "capture").glob("shot-*")), [])

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
        self.assertIn("Capturing in 1 s", note["argv"])

    def test_the_countdown_toast_expires_before_the_shot(self):  # finding 1
        self.sb.capture("display", "--delay", "2")
        [note] = self.sb.calls("notify-send")
        self.assertEqual(note["argv"][note["argv"].index("-t") + 1], "1000")
        self.sb.capture("display", "--delay", "1")  # never a zero (= no expiry) timeout
        [note] = self.sb.calls("notify-send")
        self.assertEqual(note["argv"][note["argv"].index("-t") + 1], "1")


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

    def test_satty_failure_in_the_crop_is_reported(self):  # finding 2
        r = self.sb.capture("ocr", STUB_SATTY="fail", STUB_TESSERACT="x")
        self.assertEqual((r.returncode, self.sb.calls("tesseract")), (1, []))
        [note] = self.sb.calls("notify-send")
        self.assertIn("satty failed", note["argv"][4])

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
        r = self.sb.capture("record-stop")
        self.assertEqual(r.returncode, 0, r.stderr)
        [note] = self.sb.calls("notify-send")
        self.assertEqual(note["argv"][4], "Recording saved")
        self.assertTrue(Path(note["argv"][5]).exists())
        self.assertEqual(self.status(), {"text": ""})

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

    def test_a_recorder_that_dies_at_once_is_reported_and_leaves_no_pidfile(self):  # finding 3
        r = self.sb.capture("record", "display", STUB_WF_RECORDER="fail")
        self.assertEqual(r.returncode, 1)
        [note] = self.sb.calls("notify-send")
        self.assertIn("recording failed", note["argv"][4].lower())
        self.assertIn("no gpu", note["argv"][5])
        self.assertFalse((self.sb.run / "capture" / "recording.pid").exists())
        self.assertEqual(self.sb.calls("pkill"), [])

    def test_stop_does_not_claim_a_save_that_left_no_file(self):  # finding 3
        self.sb.capture("record", "display", STUB_WF_RECORDER="nofile")
        time.sleep(0.3)
        r = self.sb.capture("record-stop")
        [note] = self.sb.calls("notify-send")
        self.assertNotEqual(note["argv"][4], "Recording saved")
        self.assertIn("failed", note["argv"][4].lower())
        self.assertEqual(r.returncode, 1)

    def test_a_recorder_that_appears_while_slurp_is_open_wins(self):  # finding 4
        rival = subprocess.Popen([str(self.sb.bin / "wf-recorder"), "-f", str(self.sb.root / "rival.mp4")],
                                 env=self.sb.env())
        self.addCleanup(rival.wait)
        self.addCleanup(rival.terminate)
        time.sleep(0.3)
        pidfile = self.sb.run / "capture" / "recording.pid"
        r = self.sb.capture("record", "region", STUB_SLURP_PIDFILE=str(self._mkpid(pidfile)),
                            STUB_SLURP_PIDDATA=f"{rival.pid}\n{self.sb.root}/rival.mp4\n")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.sb.calls("wf-recorder"), [])
        self.assertIn("already recording", self.sb.calls("notify-send")[0]["argv"][4])
        self.assertEqual(pidfile.read_text().split()[0], str(rival.pid))

    def _mkpid(self, pidfile):
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        return pidfile

    def test_a_reused_pid_is_not_the_recorder_and_is_never_signalled(self):  # finding 7
        stranger = subprocess.Popen(["sleep", "30"])
        self.addCleanup(stranger.wait)
        self.addCleanup(stranger.kill)
        pidfile = self.sb.run / "capture" / "recording.pid"
        pidfile.parent.mkdir(parents=True)
        pidfile.write_text(f"{stranger.pid}\n/x.mp4\n")
        self.assertEqual(self.status(), {"text": ""})
        self.assertFalse(pidfile.exists())
        pidfile.write_text(f"{stranger.pid}\n/x.mp4\n")
        self.sb.capture("record-stop")
        time.sleep(0.2)
        self.assertIsNone(stranger.poll())

    def test_the_recorder_uses_the_first_render_node(self):  # finding 9
        dri = self.sb.root / "dri"
        dri.mkdir()
        for n in ("renderD130", "renderD129", "card0"):
            (dri / n).write_text("")
        self.sb.capture("record", "display", CAPTURE_DRI_DIR=str(dri))
        time.sleep(0.3)
        [rec] = self.sb.calls("wf-recorder")
        self.assertEqual(rec["argv"][rec["argv"].index("-d") + 1], str(dri / "renderD129"))
        self.sb.capture("record-stop")

    def test_with_no_render_node_it_falls_back_to_renderD128(self):  # finding 9
        empty = self.sb.root / "nodri"
        empty.mkdir()
        self.sb.capture("record", "display", CAPTURE_DRI_DIR=str(empty))
        time.sleep(0.3)
        [rec] = self.sb.calls("wf-recorder")
        self.assertEqual(rec["argv"][rec["argv"].index("-d") + 1], "/dev/dri/renderD128")
        self.sb.capture("record-stop")

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


    def test_record_rows_gate_on_the_pidfile_without_starting_python(self):  # finding 5
        import tomllib
        rows = {r["label"]: r for r in tomllib.loads(
            (REPO / "sway/.config/sway/menu.toml").read_text())["action"]}
        sb = Sandbox(self)
        pidfile = sb.run / "capture" / "recording.pid"
        for label, shown_when_recording in (("Record region", False), ("Record display", False),
                                            ("Stop recording", True)):
            when = rows[label]["when"]
            with self.subTest(label):
                self.assertNotIn("capture.py", when)
                for recording in (False, True):
                    pidfile.parent.mkdir(exist_ok=True)
                    pidfile.unlink(missing_ok=True)
                    if recording:
                        pidfile.write_text("123\n/x.mp4\n")
                    code = subprocess.run(["/bin/sh", "-c", when], env={"XDG_RUNTIME_DIR": str(sb.run)}).returncode
                    self.assertEqual(code == 0, recording == shown_when_recording, (recording, code))


if __name__ == "__main__":
    unittest.main()
