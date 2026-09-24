#!/usr/bin/env python3
"""custom/herdr: herdr's agents at a glance, loudest when one needs you.

Prints waybar JSON: one number under the robot icon, picked by priority
(high to low):
- any agent *blocked*  -> that count, class `blocked` (critical, red) — this
                          also covers multiple-choice question dialogs, which
                          herdr already reports as `blocked`;
- else any agent *done* -> that count, class `waiting` (`@warning`) — `done`
                          means an agent finished its turn while you were NOT
                          looking at that tab. It clears to `idle` (and drops
                          out of this count) the instant you *view* the tab —
                          whether or not you've actually answered — or goes
                          straight to `idle` if you were already watching
                          when it finished. So `done` is a lower bound on
                          "there's an answer waiting", not an exact count;
- else                  -> the count of agents *working*, class `quiet`
                          (`@dim`) — always shown while herdr runs, so a
                          glance proves the module is alive;
- herdr not running     -> empty text, which hides the module.

Tooltip: one section per non-empty status among blocked / done / idle /
working, each headed by its count and one line per agent (`describe`). idle
is headed "seen, not answered yet" — herdr can't tell "viewed and answered"
from "viewed and still ignored", so every idle agent is listed rather than
guessed at.

herdr's `attention` plugin pokes the bar (signal 9) on every
`pane.agent_status_changed` event, so blocked/working/done transitions are
live. Viewing a pane — which is what clears `done` to `idle` — is *not* such
an event (herdr's client marks the tab seen locally, no event fires), so
nothing pokes the bar for it: the interval in the config (5s) is what
actually clears a stale "waiting". PLAYBOOK §9.30.

`--focus` (the on-click): focus the first blocked agent; if none, the first
done agent; then raise the terminal window running the herdr client.

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


def by_status(listed, status):
    return [a for a in listed if a.get("agent_status") == status]


def focus_target(listed):
    """The agent `--focus` should jump to: the first blocked one (a decision
    is needed), else the first done one (an answer is waiting), else None."""
    blocked = by_status(listed, "blocked")
    if blocked:
        return blocked[0]
    done = by_status(listed, "done")
    if done:
        return done[0]
    return None


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


def section(agents_of_status, header, labels):
    return [header] + [describe(a, labels) for a in agents_of_status]


def render():
    listed = agents()
    if listed is None:
        return {"text": ""}
    blocked = by_status(listed, "blocked")
    done = by_status(listed, "done")
    idle = by_status(listed, "idle")
    working = by_status(listed, "working")
    # Only fetch labels when something will actually be described.
    labels = workspace_labels() if (blocked or done or idle or working) else {}

    sections = []
    if blocked:
        sections.append(section(
            blocked, plural(len(blocked), "agent") + " blocked — needs a decision", labels))
    if done:
        sections.append(section(
            done, plural(len(done), "session") + " waiting for your answer", labels))
    if idle:
        sections.append(section(
            idle, plural(len(idle), "agent") + " seen, not answered yet", labels))
    if working:
        sections.append(section(
            working, plural(len(working), "agent") + " working", labels))

    if not sections:
        lines = [f"herdr: {plural(len(listed), 'agent')}"]
    else:
        lines = []
        for s in sections:
            if lines:
                lines.append("")
            lines.extend(s)
        if blocked:
            lines += ["", "Click: go to the first blocked"]
        elif done:
            lines += ["", "Click: go to the first waiting"]
    tooltip = "\n".join(lines)

    if blocked:
        return {"text": f"{ICON}\n{len(blocked)}", "class": "blocked", "tooltip": tooltip}
    if done:
        return {"text": f"{ICON}\n{len(done)}", "class": "waiting", "tooltip": tooltip}
    return {"text": f"{ICON}\n{len(working)}", "class": "quiet", "tooltip": tooltip}


def focus_first():
    listed = agents()
    if listed is None:
        return
    target = focus_target(listed)
    if target is None:
        return
    herdr("agent", "focus", target["pane_id"])
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
