#!/usr/bin/env python3
"""herdr `pane.agent_status_changed` hook: make "blocked" impossible to miss.

herdr runs this once per agent state change, for every pane (PLAYBOOK §9.30).

- blocked      -> one critical notification, labelled `herdr`, unless the user
                  is already looking at that pane. A pane that re-blocks
                  replaces its own notification rather than stacking another.
- anything else -> that pane's notification, if any, is withdrawn: an agent
                  that got its answer should not leave a sticky alert behind.
- always       -> poke waybar's custom/herdr module (signal 9) to recount.

Nothing here may block herdr or touch the network: every external command has
a short timeout and every failure is swallowed — a missed notification is
better than a wedged hook, and herdr caps concurrent plugin commands.
"""
import json
import os
import re
import subprocess
from pathlib import Path

TIMEOUT = 2
WAYBAR_SIGNAL = 9  # custom/herdr's "signal" in waybar/.config/waybar/config


def run(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              timeout=TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def load(name):
    try:
        return json.loads(os.environ.get(name) or "{}")
    except ValueError:
        return {}


def state_file(pane_id):
    root = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    if not root:
        return None
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", pane_id)
    return Path(root) / "notified" / safe


def ancestors(pid):
    """Yield pid and each parent up to init, from /proc."""
    seen = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        yield pid
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
        except OSError:
            return
        # comm may contain spaces or ')' — ppid is the 2nd field after the last ')'.
        pid = int(stat.rsplit(")", 1)[1].split()[1])


def herdr_window_focused():
    """True when the sway-focused window is a terminal running a herdr client."""
    tree = run(["swaymsg", "-t", "get_tree", "-r"])
    if tree is None or tree.returncode != 0:
        return False
    try:
        nodes = [json.loads(tree.stdout)]
    except ValueError:
        return False
    focused_pid = None
    while nodes:
        node = nodes.pop()
        if node.get("focused") and node.get("pid"):
            focused_pid = node["pid"]
            break
        nodes.extend(node.get("nodes", []) + node.get("floating_nodes", []))
    if focused_pid is None:
        return False
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if (proc / "comm").read_text().strip() != "herdr":
                continue
        except OSError:
            continue
        if focused_pid in ancestors(int(proc.name)):
            return True
    return False


def main():
    data = load("HERDR_PLUGIN_EVENT_JSON").get("data") or {}
    context = load("HERDR_PLUGIN_CONTEXT_JSON")
    pane_id = data.get("pane_id")
    status = data.get("agent_status")
    if not pane_id or not status:
        return
    marker = state_file(pane_id)
    previous = None
    if marker is not None and marker.exists():
        previous = marker.read_text().strip() or None

    if status == "blocked":
        looking = (context.get("focused_pane_id") == pane_id
                   and herdr_window_focused())
        if not looking:
            agent = data.get("display_agent") or data.get("agent") or "agent"
            where = context.get("workspace_label") or data.get("workspace_id") or ""
            title = (data.get("title") or "").strip()
            body = " · ".join(part for part in (where, title) if part)
            argv = ["notify-send", "--app-name=herdr", "--urgency=critical",
                    "--print-id"]
            if previous:
                argv.append(f"--replace-id={previous}")
            argv += [f"{agent} is waiting for you", body or pane_id]
            sent = run(argv)
            if sent is not None and sent.returncode == 0 and marker is not None:
                notification_id = sent.stdout.strip()
                if notification_id.isdigit():
                    marker.parent.mkdir(parents=True, exist_ok=True)
                    marker.write_text(notification_id)
    elif previous:
        run(["makoctl", "dismiss", "-n", previous])
        marker.unlink(missing_ok=True)

    run(["pkill", f"-RTMIN+{WAYBAR_SIGNAL}", "-x", "waybar"])


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — a hook must never fail loudly into herdr
        pass
