#!/usr/bin/env python3
"""custom/herdr: how many herdr agents are blocked, waiting for an answer.

Prints waybar JSON. Zero blocked, or herdr not running, prints an empty text,
which hides the module — the bar only grows when something needs the user.
herdr's `attention` plugin sends signal 9 on every agent state change, so the
count is live; the interval in the config is only a fallback. PLAYBOOK §9.30.

`--focus` (the on-click): focus the first blocked agent in herdr, then raise
the terminal window running the herdr client.

Read-only against herdr: it lists, and on click focuses — never starts,
prompts or closes anything.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT = 2
ICON = "\U000f06a9"  # nf-md-robot


def herdr_bin():
    return shutil.which("herdr") or str(Path.home() / ".local/bin/herdr")


def herdr(*args):
    # The bar is not inside herdr, but a HERDR_* variable inherited from a
    # shell that was would point the CLI at a pane instead of the default
    # socket, so the variables that describe "where am I" are dropped.
    env = {k: v for k, v in os.environ.items()
           if k not in ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_TAB_ID",
                        "HERDR_WORKSPACE_ID")}
    try:
        out = subprocess.run([herdr_bin(), *args], capture_output=True,
                             text=True, timeout=TIMEOUT, env=env, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout).get("result") or {}
    except ValueError:
        return None


def blocked_agents():
    result = herdr("agent", "list")
    if result is None:
        return None
    return [a for a in result.get("agents", [])
            if a.get("agent_status") == "blocked"]


def workspace_labels():
    result = herdr("workspace", "list") or {}
    return {w.get("workspace_id"): w.get("label") or w.get("workspace_id")
            for w in result.get("workspaces", [])}


def render():
    blocked = blocked_agents()
    if not blocked:
        return {"text": ""}
    labels = workspace_labels()
    lines = []
    for agent in blocked:
        where = labels.get(agent.get("workspace_id"), agent.get("workspace_id", "?"))
        title = (agent.get("terminal_title_stripped") or "").strip()
        name = agent.get("display_agent") or agent.get("agent") or "agent"
        lines.append(f"{where} · {name}" + (f" — {title}" if title else ""))
    count = len(blocked)
    head = f"{count} agent{'s' if count != 1 else ''} waiting for you"
    return {"text": f"{ICON}\n{count}", "class": "blocked",
            "tooltip": head + "\n" + "\n".join(lines) + "\n\nClick: go to the first"}


def focus_first():
    blocked = blocked_agents()
    if not blocked:
        return
    herdr("agent", "focus", blocked[0]["pane_id"])
    # Raise the window hosting a herdr client: walk each sway window's pid
    # down to a `herdr` descendant.
    clients = set()
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if (proc / "comm").read_text().strip() == "herdr":
                clients.add(int(proc.name))
        except OSError:
            continue
    parents = set()
    for pid in clients:
        while pid > 1 and pid not in parents:
            parents.add(pid)
            try:
                stat = Path(f"/proc/{pid}/stat").read_text()
            except OSError:
                break
            pid = int(stat.rsplit(")", 1)[1].split()[1])
    try:
        tree = subprocess.run(["swaymsg", "-t", "get_tree", "-r"],
                              capture_output=True, text=True, timeout=TIMEOUT)
        nodes = [json.loads(tree.stdout)]
    except (OSError, subprocess.SubprocessError, ValueError):
        return
    while nodes:
        node = nodes.pop()
        if node.get("pid") in parents and node.get("type") in ("con", "floating_con"):
            subprocess.run(["swaymsg", f"[con_id={node['id']}]", "focus"],
                           capture_output=True, timeout=TIMEOUT)
            return
        nodes.extend(node.get("nodes", []) + node.get("floating_nodes", []))


def main(argv):
    if "--focus" in argv:
        focus_first()
        return
    print(json.dumps(render(), ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
