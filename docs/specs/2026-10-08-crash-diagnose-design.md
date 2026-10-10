# Crash → Claude diagnosis — design

**Date:** 2026-10-08 · **Status:** approved in grill · **Scope:** notice crashes of the user's own
processes, build an evidence report on request, and open Claude on it in herdr.

## §0 Background

Omarchy 4 raises a toast when a process dumps core and hands the crash to a coding agent
(`omarchy-agent-crash`). Reviewers called it "a genuinely novel bit of OS design". Omarchy launches
that agent with permission prompts reduced or bypassed. The migration research
(`2026-09-25-omarchy-migration-research.md` §3.5, "Agent posture") lists keeping this machine's own
agent posture (Claude launched through herdr, under its own permission settings) as something
Omarchy lacks. So this is the same feature, minus the bypass.

**There is real material:** `coredumpctl list` (2026-10-08) shows waybar aborting with SIGABRT on
2026-09-26, 09-27 and 10-02, uv's CPython 3.12 dying with SIGILL twice, and a root-owned headless
chromium segfault. systemd-coredump is active. The user (in `wheel`) can read the coredump journal
entries (`MESSAGE_ID=fc2e22bc6ee647b6b90729ab34a250b1`). `gdb` is installed, and `DEBUGINFOD_URLS`
points at Arch's debuginfod.

Unlike the palette and capture, this is **not sway-specific**. It is expected to survive the Omarchy
migration, replacing Omarchy's crash hook with this posture.

## §1 Terms

- **Crash** — a systemd-coredump journal entry (`MESSAGE_ID=fc2e22bc…`) whose `COREDUMP_UID` is the
  user's own uid.
- **Report** — `~/.local/state/crash-reports/<ts>_<exe>_<pid>/report.md`, built on request from the crash.
- **Coalescing** — collapsing repeat crashes of one executable into one notification.

## §2 Decisions (grill, 2026-10-08)

| # | Question | Decision |
|---|---|---|
| X1 | Trigger | **Notify + palette.** A watcher toasts each new crash of the user's processes, with a "Diagnose with Claude" action; the palette row **Dev › Diagnose a crash…** picks any recent one. Claude never starts unless the user clicks or picks. Rejected: palette only; fully automatic (an agent per crash) |
| X2 | Posture | **Script builds the report; Claude diagnoses and proposes** under the user's normal permission settings, told not to change any file without asking. Rejected: read-only diagnosis; Claude gathering the evidence itself (a permission prompt per step) |
| X3 | Shape | One tool, `bin/.local/bin/crash-diagnose` (`watch` / `list` / `diagnose <pid>`), and `crash-watch.service` (systemd user). At most one toast per executable per 30 min. The report is built on click (gdb ≤ 90 s). A herdr tab, falling back to kitty. Keep the newest 20 reports |

## §3 Architecture

```
crash-watch.service ─ ExecStart=crash-diagnose watch
  └ journalctl -f -n0 -o json MESSAGE_ID=fc2e22bc6ee647b6b90729ab34a250b1
      each entry:
        COREDUMP_UID != os.getuid()            → ignore
        same COREDUMP_EXE toasted < 30 min ago → bump its count, replace that toast (notify-send -r <id>)
        else → notify-send -u normal -a crash -A "default=Diagnose with Claude" --wait
               "Crash: <comm> (<signal>)" "pid <pid> · <n>th since <first date>"
               (each toast's --wait runs in its own thread; the watcher keeps reading)
               clicked → spawn `crash-diagnose diagnose <pid>` detached

crash-diagnose list      → coredumpctl --json=short list, own uid, newest first, max 20:
                           "<pid>  <MM-DD HH:MM>  <comm>  <signal>"   (palette `choices`)
crash-diagnose diagnose <pid | a list line>   (takes the leading pid)
  1. notify "Preparing crash report for <comm>…"
  2. report.md:
       - summary: exe, comm, signal, time, package (from COREDUMP_PACKAGE_JSON, else pacman -Qo <exe>)
       - history: this exe's crashes (coredumpctl list <exe>)
       - backtrace: `coredumpctl info <pid>` (timeout 90 s; gdb + debuginfod give symbols)
       - journal: `journalctl --since <t-2min> --until <t+2min>` for that user's session
       - a "missing" line for anything that could not be gathered, and why
     NEVER included: COREDUMP_ENVIRON (the process environment — tokens), the core file itself
  3. prune ~/.local/state/crash-reports/ to the newest 20
  4. herdr tab create --label "crash: <comm>" --cwd <report dir> --focus  → pane id (§6 probe)
     herdr pane run <pane> claude "<PROMPT>"
     no herdr / failure → kitty --directory <report dir> claude "<PROMPT>"
```

**PROMPT** (fixed text; the tests pin it):

> Read report.md in this directory: a crash on this machine. Find the most likely cause, say how
> confident you are and why, and propose a fix. This machine's configuration lives in
> ~/repos/dotfiles; read its CLAUDE.md first if the crash involves it. Do not change any file or
> run anything that changes system state without asking me first.

## §4 Components

| Path | Status | Purpose |
|---|---|---|
| `bin/.local/bin/crash-diagnose` | new | Python stdlib; `watch`, `list`, `diagnose` |
| `systemd/.config/systemd/user/crash-watch.service` | new | `ExecStart=%h/.local/bin/crash-diagnose watch`, `Restart=on-failure`, `WantedBy=default.target` |
| `sway/.config/sway/menu.toml` | edit | `Dev › Diagnose a crash…`: `choices = "crash-diagnose list"`, `run = "crash-diagnose diagnose {choice}"` |
| `tests/crash_test.py` | new | §6 |
| `tests/check_consumers.sh` | edit | `crash-watch.service` is active |
| `PLAYBOOK.md` §9 (new), `CLAUDE.md`, `systemd/.config/systemd/user/README.md` | edit | Docs, the test line, the unit list |

No new packages.

## §5 Error handling

| Situation | Behaviour |
|---|---|
| Symbols unavailable (offline) or gdb past 90 s | Report written with "no symbolised backtrace" plus the raw `coredumpctl info`; Claude still launches |
| Core file gone (rotated) | Report holds the journal entry; says so |
| herdr not running or `tab create` fails | kitty fallback; if that fails too, a critical notification with the report path |
| `claude` missing from the action PATH | Critical notification naming it; the report is still written and its path given |
| The watcher's journalctl exits | Service `Restart=on-failure`; `check_consumers.sh` asserts `systemctl --user is-active crash-watch` |
| Toast dismissed | Nothing; the crash remains in the palette list |
| A crash during report building of another | Independent; each `diagnose` is its own process |

## §6 Testing

**Probe first (`[needs-prototype]`, plan Task 1):** record in the ledger
- whether mako runs `-A default=…` on a left click and `notify-send --wait` then prints `default`
- the JSON `herdr tab create` prints (the field holding the new pane id)
- how long `coredumpctl info` takes on a real waybar core, with debuginfod

**`tests/crash_test.py`** (stdlib unittest; stubs on PATH; recorded journal JSON fixtures with
`COREDUMP_ENVIRON` present, so D4 can prove it is dropped):

| # | Asserts |
|---|---|
| D1 | Entries with another uid are ignored |
| D2 | A second crash of the same exe within 30 min replaces the toast with an updated count; after 30 min it is a new toast |
| D3 | A `default` reply from `notify-send --wait` spawns `diagnose <pid>` |
| D4 | report.md has the summary, history, backtrace and journal sections; **never** any `COREDUMP_ENVIRON` value; "missing" lines when coredumpctl times out or the core is gone |
| D5 | herdr call shape (label, cwd, focus, then pane run with the prompt); kitty fallback when herdr fails |
| D6 | The prompt is exactly the §3 text |
| D7 | `list` formatting, and `diagnose` accepting a whole `list` line |
| D8 | Retention keeps the newest 20 |

Mutations: removing the uid filter must turn D1 red, removing the coalesce window D2, and
including the environ D4.

## §7 Rollout

Branch `feat/crash-diagnose`, after capture merges. Then
`systemctl --user daemon-reload && systemctl --user enable --now crash-watch.service`. The systemd
user package is unfolded (PLAYBOOK §5.2), so the new unit file needs `stow -R systemd`.

**Manual smoke:** `sleep 60 & kill -SEGV $!` (a harmless crash of the user's own process) → toast
→ click → a herdr tab opens with Claude reading the report.

## §8 Honest caveats

- **The report goes to Claude**, which means Anthropic's API. Backtraces, command lines and journal
  lines are included; the process environment is not. A secret passed on a command line would be.
- **Backtraces show frames, not argument values** (final-review ruling, 2026-10-09). gdb's default
  `print frame-arguments scalars` prints a `char *` argument's contents, which scrub() cannot know,
  so the gdb run sets `print frame-arguments presence`: every frame keeps its function name and
  its arguments show as `...`. The crash-time stack never had argument values.
- **debuginfod is network access** at click time, not at crash time. Offline reports are less
  useful, but still produced.
- **Root and system-service crashes are out of scope** (uid filter). The chromium segfault in the
  list is one.
- **One toast per executable per 30 min** can hide a storm. The count in the replaced toast is the
  signal.
