#!/usr/bin/env python3
"""Tests for the Windows tray (windows/claude-usage/, PLAYBOOK §9.31).

Two halves:

- install.py's pure parts — palette selection and rendering, the config it
  writes, PowerShell quoting, the shortcut command line. Run anywhere.
- tests/claude_tray_test.ps1, driven from here with fixtures written by the
  real claude_usage.snapshot(), so the Python/PowerShell contract is tested
  across the boundary rather than against JSON written by hand. Needs
  powershell.exe — i.e. WSL with interop — and is SKIPPED elsewhere (the sway
  desktop), which unittest reports as a skip, not a pass.

Nothing here starts the tray, touches the Startup folder or %LOCALAPPDATA%.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cu = load("claude_usage", "waybar/.config/waybar/scripts/claude_usage.py")
inst = load("claude_tray_install", "windows/claude-usage/install.py")

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=timezone.utc)
LIMITS = [
    {"kind": "session", "percent": 44, "resets_at": "2026-08-22T15:13:00+00:00"},
    {"kind": "weekly_all", "percent": 41, "resets_at": "2026-08-27T10:00:00+00:00"},
    {"kind": "weekly_scoped", "percent": 70, "resets_at": "2026-08-27T10:00:00+00:00",
     "scope": {"model": {"display_name": "Fable"}}},
]


class PaletteTest(unittest.TestCase):
    def test_active_palette_reads_themes_state_file(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "theme").mkdir()
            (Path(td) / "theme" / "palette").write_text("gruvbox\n")
            self.assertEqual(inst.active_palette({"XDG_STATE_HOME": td}), "gruvbox")

    def test_active_palette_defaults_to_nord(self):
        # The normal case inside WSL: `theme` has never run there.
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(inst.active_palette({"HOME": td}), "nord")
            self.assertEqual(inst.active_palette({"HOME": td, "XDG_STATE_HOME": ""}), "nord")
            (Path(td) / "theme").mkdir()
            (Path(td) / "theme" / "palette").write_text("  \n")
            self.assertEqual(inst.active_palette({"XDG_STATE_HOME": td}), "nord")

    def test_roles_are_the_top_level_strings_of_the_real_table(self):
        for name in ("nord", "gruvbox"):
            roles = inst.palette_roles(inst.PALETTES, name)
            # Every role the tray draws with, and nothing from [*.ansi].
            for role in ("bg", "sel", "muted", "dim", "fg", "fg_bright", "accent",
                         "indicator", "warning", "critical"):
                self.assertIn(role, roles, msg=name)
            self.assertNotIn("ansi", roles)
            self.assertTrue(all(v.startswith("#") for v in roles.values()))

    def test_unknown_palette_names_the_choices(self):
        with self.assertRaises(SystemExit) as cm:
            inst.palette_roles(inst.PALETTES, "solarized")
        self.assertIn("gruvbox", str(cm.exception))
        self.assertIn("nord", str(cm.exception))


class ConfigTest(unittest.TestCase):
    def test_config_points_at_this_checkout(self):
        cfg = inst.build_config("Ubuntu", "/usr/bin/python3", inst.COLLECTOR, 60,
                                "nord", {"bg": "x"})
        self.assertEqual(json.loads(json.dumps(cfg)), cfg)
        self.assertEqual(cfg["script"], str(REPO / "waybar/.config/waybar/scripts/claude_usage.py"))
        self.assertTrue(Path(cfg["script"]).is_file())
        self.assertTrue(inst.TRAY_PS1.is_file())

    def test_notify_defaults_on_and_can_be_switched_off(self):
        on = inst.build_config("U", "p", inst.COLLECTOR, 60, "nord", {})
        off = inst.build_config("U", "p", inst.COLLECTOR, 60, "nord", {}, notify=False)
        self.assertIs(on["notify"], True)
        self.assertIs(off["notify"], False)
        # ...and the tray reads that key, defaulting on.
        self.assertIn("Get-OptionalValue $config 'notify' $true", inst.TRAY_PS1.read_text())

    def test_default_python_is_never_a_venv(self):
        if Path("/usr/bin/python3").exists():
            self.assertEqual(inst.default_python(), "/usr/bin/python3")


class PowerShellQuotingTest(unittest.TestCase):
    def test_single_quoted_literal(self):
        self.assertEqual(inst.ps_literal("C:\\Users\\O'Brien\\x"), "'C:\\Users\\O''Brien\\x'")
        self.assertEqual(inst.ps_literal("$env:X"), "'$env:X'")   # no expansion

    def test_shortcut_runs_hidden_powershell_on_the_copied_script(self):
        args = inst.tray_command_args(r"C:\Users\A B\AppData\Local\ClaudeUsage\ClaudeUsageTray.ps1")
        self.assertTrue(args.startswith("powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden"))
        self.assertTrue(args.endswith(r'-File "C:\Users\A B\AppData\Local\ClaudeUsage\ClaudeUsageTray.ps1"'))

    def test_install_snippet_targets_conhost_and_only_starts_when_asked(self):
        s = inst.install_snippet(r"C:\S\Claude Usage.lnk", r"C:\L\ClaudeUsage",
                                 r"C:\L\ClaudeUsage\ClaudeUsageTray.ps1", start=False)
        self.assertIn("System32\\conhost.exe", s)
        self.assertIn("$l.WindowStyle = 7", s)
        self.assertNotIn("Start-Process", s)
        self.assertIn(inst.EXIT_EVENT, s)          # stops the old tray first
        self.assertIn("Start-Process -FilePath 'C:\\S\\Claude Usage.lnk'",
                      inst.install_snippet(r"C:\S\Claude Usage.lnk", "a", "b", start=True))

    def test_exit_event_name_matches_the_tray(self):
        # install.py stops the tray by this name; a rename on one side only
        # would leave every update killing the tray instead of asking it.
        self.assertIn(f"'{inst.EXIT_EVENT}'", inst.TRAY_PS1.read_text())

    def test_owned_files_cover_what_the_tray_writes(self):
        text = inst.TRAY_PS1.read_text()
        for name in ("last.json", "notify.json", "tray.log"):
            self.assertIn(f"'{name}'", text)
            self.assertIn(name, inst.OWNED)

    def test_uninstall_removes_only_keys_named_by_the_tray(self):
        s = inst.uninstall_snippet(r"C:\S\Claude Usage.lnk")
        self.assertIn(r"'HKCU:\Software\Classes\AppUserModelId'", s)   # single backslashes
        self.assertIn(f"GetValue('DisplayName') -eq '{inst.TOAST_NAME}'", s)
        self.assertIn("$ToastName = '" + inst.TOAST_NAME + "'", inst.TRAY_PS1.read_text())
        self.assertIn(r"Remove-Item -LiteralPath 'C:\S\Claude Usage.lnk'", s)
        self.assertIn("icon.png", inst.OWNED)

    def test_status_report(self):
        with tempfile.TemporaryDirectory() as td:
            app = Path(td)
            self.assertEqual(inst.status_report("", app), "tray: not running\ninstall: not installed")
            (app / "config.json").write_text(json.dumps(
                inst.build_config("Ubuntu", "p", inst.COLLECTOR, 60, "nord", {})))
            (app / "tray.log").write_text("".join(f"line {n}\n" for n in range(9)))
            out = inst.status_report("pid=42\r\n".replace("\r", ""), app)
            self.assertIn("tray: running, pid 42", out)
            self.assertIn("distro 'Ubuntu', every 60s, notifications on, palette 'nord'", out)
            self.assertIn("  line 8", out)
            self.assertNotIn("line 3", out)

    def test_modes_are_exclusive(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                inst.main(["--start", "--stop"])

    def test_snapshot_schema_matches_the_tray(self):
        self.assertIn(f"$SnapshotSchema = {cu.SNAPSHOT_SCHEMA} ", inst.TRAY_PS1.read_text())


@unittest.skipUnless(shutil.which("powershell.exe") and shutil.which("wslpath"),
                     "needs Windows PowerShell through WSL interop")
class TrayPowerShellTest(unittest.TestCase):
    """Runs tests/claude_tray_test.ps1 on fixtures from the real snapshot()."""

    def fixtures(self, td):
        base = {"limits": LIMITS, "limits_fetched_at": NOW.timestamp() - 60, "limits_error": None,
                "creds_meta": {"subscriptionType": "max"},
                "days": {"2026-08-22": {"claude-fable-5": 57_700_000},
                         "2026-08-20": {"claude-opus-5": 256_200_000}}}
        snaps = {
            "full.json": cu.snapshot(base, NOW),
            "stale.json": cu.snapshot(dict(base, limits_error="HTTP 429", days={}), NOW),
            "empty.json": cu.snapshot({"limits_error": "not logged in"}, NOW),
            "bad_schema.json": dict(cu.snapshot(base, NOW), schema=99),
        }
        for name, snap in snaps.items():
            (Path(td) / name).write_text(json.dumps(snap))

    def test_powershell_suite(self):
        # Day buckets are local-midnight: pin this side's zone so the fixture's
        # "today" is 2026-08-22 wherever the suite runs. NOW is noon UTC, so
        # the Windows side agrees in any zone within 11 hours of UTC.
        saved = os.environ.get("TZ")
        self.addCleanup(lambda: (os.environ.pop("TZ", None) if saved is None
                                 else os.environ.__setitem__("TZ", saved), time.tzset()))
        os.environ["TZ"] = "UTC"
        time.tzset()
        with tempfile.TemporaryDirectory() as td:
            self.fixtures(td)
            win = lambda p: subprocess.run(["wslpath", "-w", str(p)], capture_output=True,
                                           text=True, check=True).stdout.strip()
            r = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", win(REPO / "tests" / "claude_tray_test.ps1"),
                 "-FixtureDir", win(td), "-Now", repr(NOW.timestamp())],
                capture_output=True, text=True, cwd="/mnt/c", timeout=180)
            out = (r.stdout + r.stderr).replace("\r", "")
            self.assertEqual(r.returncode, 0, msg="\n" + out)
            self.assertRegex(out, r"\d+ passed, 0 failed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
