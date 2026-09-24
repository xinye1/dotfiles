#!/usr/bin/env python3
"""custom/herdr: herdr's agents at a glance, loud only when one is blocked.

Prints waybar JSON:
- herdr not running  -> empty text, which hides the module;
- nothing blocked    -> the number of agents *working*, class `quiet` (dim) —
                        always there, so a glance shows the module is alive;
- anything blocked   -> the number *blocked*, class `blocked` (critical).
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


def agents():
    result = herdr("agent", "list")
    if result is None:
        return None
    return result.get("agents", [])


def blocked_agents():
    listed = agents()
    if listed is None:
        return None
    return [a for a in listed if a.get("agent_status") == "blocked"]


def workspace_labels():
    result = herdr("workspace", "list") or {}
    return {w.get("workspace_id"): w.get("label") or w.get("workspace_id")
            for w in result.get("workspaces", [])}


def describe(agent, labels):
    where = labels.get(agent.get("workspace_id"), agent.get("workspace_id", "?"))
    title = (agent.get("terminal_title_stripped") or "").strip()
    name = agent.get("display_agent") or agent.get("agent") or "agent"
    return f"{where} · {name}" + (f" — {title}" if title else "")


def plural(n, word):
    return f"{n} {word}{'s' if n != 1 else ''}"


def render():
    listed = agents()
    if listed is None:
        return {"text": ""}
    blocked = [a for a in listed if a.get("agent_status") == "blocked"]
    working = [a for a in listed if a.get("agent_status") == "working"]
    labels = workspace_labels() if (blocked or working) else {}
    if blocked:
        lines = [plural(len(blocked), "agent") + " waiting for you"]
        lines += [describe(a, labels) for a in blocked]
        lines += ["", "Click: go to the first"]
        return {"text": f"{ICON}\n{len(blocked)}", "class": "blocked",
                "tooltip": "\n".join(lines)}
    lines = [f"herdr: {plural(len(listed), 'agent')}, {len(working)} working, none blocked"]
    lines += [describe(a, labels) for a in working]
    return {"text": f"{ICON}\n{len(working)}", "class": "quiet",
            "tooltip": "\n".join(lines)}


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
