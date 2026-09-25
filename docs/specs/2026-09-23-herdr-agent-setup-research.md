# herdr for an all-Claude-Code desktop: best practices, adapted to this machine

*STORM research report · 2026-09-23 · target: herdr **0.8.0** on Arch/sway/kitty, dotfiles at `~/repos/dotfiles`*

> **Verification banner:** 33 claims checked (7 clusters × 3 refute-by-default voters) ·
> **1 killed** · **7 corrected** · **1 demoted**. Killed: a `tmux set-environment -gu HERDR_ENV`
> workaround attributed to #2134 (not in the issue). Corrected: the heap-corruption crash is
> fixed in stable 0.9.1, not "master only"; the session-wipe bug (#4320) was reproduced on 0.9.0
> only and is closed with a preview-channel fix; #3116's 0.9.1 reproduction is a different
> (OSC 7) variant; protocol v14 arrived in 0.7.0; #481 shows "completed" only because it was
> converted to a discussion; the docs version label is a selector, not a quoted string; the
> "next human contributor" count excludes a bot. Demoted: the claim that a custom
> `working` report would stick after an Esc interrupt (source reading, untested).

> **Outcome (2026-09-24, branch `feat/herdr-package`).** Built per §12, with these resolutions;
> PLAYBOOK §9.30 is the living reference, this file is the research record.
> - **Q1 validator:** a throwaway `herdr server` + `herdr server reload-config`, whose JSON lists
>   every ignored key (`"status":"applied"`, `"diagnostics":[]` when clean). In `check_consumers.sh`.
> - **Q2 legibility:** measured, not rendered — the terminal theme's `surface1` (ANSI 8) carries
>   text at 2.68:1 under gruvbox; `[theme.custom] surface1 = "black"` fixes it (7.45 / 8.45:1).
> - **Q3 event shape / focus:** captured live — `{"event":"pane_agent_status_changed","data":{…}}`;
>   `HERDR_PLUGIN_CONTEXT_JSON` carries `focused_pane_id`. **Q4:** cwd is the plugin root.
> - **Q5 prefix:** `ctrl+b` kept. tmux here is only the agents' detached job runner, which nobody
>   attaches to; interactive tmux use had already moved to herdr (follow-up research, 10 blogs +
>   HN: 0 users found who went back).
> - **Q6 upgrade:** option A — after the backup timer's first run, by clean restart; user-run.
> - **Found while building, not in the research:** the #2134 tmux leak was live on this machine
>   (fixed in `tmux.conf`), and the claude widget's `pkill -RTMIN+8 waybar` also killed the bar's
>   supervisor (fixed, and guarded in `theme_test.sh`). `min_herdr_version` is mandatory in a
>   plugin manifest; the sidebar row and `delivery = "herdr"` shipped as proposed.

Perspectives were author-built (daily-driver power user, agent orchestrator, plugin scout,
desktop integrator, skeptic). Where they agree, treat it as a strong hypothesis, not field
consensus. Every numbered citation resolves to the References list at the end; `local:` sources
are the installed binary or the `v0.8.0` tag of the herdr source, read in this session.

---

## 1. Executive summary

**Settled**

- **The web describes a different herdr than the one installed.** herdr.dev's version selector
  defaults to "Latest 0.9.1" (0.8.2 and 0.8.0 are also selectable) [6]; the binary is 0.8.0 [19].
  Versioned 0.8.0 pages exist (`herdr.dev/docs/0.8.0/…`) [1][3] and the binary's
  `--default-config` is the authority for which keys exist. Unknown keys are **ignored with a
  diagnostic**, not fatal [18] — a 0.9-only key in a 0.8.0 config silently does nothing. One
  exception: a misspelled field inside a *styled sidebar token* (`{ token = …, fg = … }`) is
  `deny_unknown_fields` and fails the parse [18].
- **0.9.1 only adds config keys over 0.8.0** (theme tokens, `theme.custom.light/dark`,
  `move_tab_*`, `resize_pane_*`, `[server]`, `pane_outer_borders`, `tab_bar_right`,
  `window_title`, `status_indicators`; `kitty_graphics` moves from `[experimental]` to
  `[terminal]`) [18, diff of `v0.8.0`/`v0.9.1` default configs]. A config written against 0.8.0
  keys survives the upgrade unchanged.
- **Claude Code's state (idle/working/blocked/done) comes from screen detection, not hooks.**
  The official Claude integration reports *session identity only* — deliberately. herdr moved
  Claude off hook-driven state because hooks "can miss permission approval results, escape
  interrupts" [27][7]. Your installed integration (v7, `SessionStart` only) is therefore
  complete, not half-installed.
- **Plugin `[[events]]` hooks can fire on `pane.agent_status_changed` in 0.8.0** — it is in
  `PLUGIN_HOOK_EVENT_KINDS` at tag `v0.8.0`, and the payload carries `pane_id` +
  `agent_status` ∈ {idle, working, blocked, done, unknown} [18]. That is the clean hook for
  routing "blocked" to mako.
- **herdr writes `config.toml` itself, in place.** The settings UI (theme, sound, toast
  delivery, border labels, panel sort, onboarding) and `herdr channel set` rewrite the file with
  `std::fs::write` [18]. Your current 7-line config is exactly that UI's output. A stow file
  symlink survives in-place writes, so those edits would land in the repo as diffs.
- **Plugins are unsandboxed code running as you** [4]; the socket gives any same-user process
  every API method, including typing into other panes [14].

**Contested / judgement calls**

- Whether to upgrade to 0.9.1 now (better Claude detection vs. open restore/wipe bugs) — §3.
- Whether to add your own Claude lifecycle hooks (the API allows it; herdr's authors walked
  away from it) — §7.2.

---

## 2. Where you are

| Item | State (local, 2026-09-23) |
|---|---|
| Binary | `~/.local/bin/herdr` 0.8.0, protocol 19, stable channel; 0.9.1 available |
| Server | running, socket `~/.config/herdr/herdr.sock` (`srw-------`) |
| Workspaces | 3 (TP Core, TP Android, General Claude); every pane is Claude Code, one in `.claude/worktrees/ws2+next` |
| Integrations | `claude: current (v7)` — `SessionStart` hook → `pane.report_agent_session` |
| Config | 7 lines: `onboarding=false`, `ui.toast.delivery="system"`, `theme.name="nord"`, `show_agent_labels_on_pane_borders=true`, `agent_panel_sort="spaces"` |
| Dotfiles | herdr config **not tracked**; `~/.config/herdr` also holds sockets, logs, `session.json`, `release-notes.json`, `.plugins.lock` |
| Terminal | `$term` is kitty (foot retired from `$mod+Return`); tmux prefix is the default `ctrl+b` |
| Plugins | none installed (no `plugins.json`) [plugin scout, local] |

**Packaging consequence.** Because herdr writes sockets, logs and `session.json` into
`~/.config/herdr`, a `herdr` stow package must stay **unfolded** — folding would put live
sockets and session state into the repo (PLAYBOOK §5.2's rule). This directory already exists
on this machine; `setup.sh` would need to pre-create it on a fresh one.

---

## 3. Upgrade 0.8.0 → 0.9.1?

**What 0.9.x buys**

- Claude detection fixes: MCP/Bash approval prompts staying `blocked`, background-agent
  activity, the spinner misread (CHANGELOG #3283, #3090, #3949) [7].
- Plugins that require it: `herdr-auto-title` declares `min_herdr_version = "0.8.2"` and herdr
  refuses to install a plugin whose minimum is newer [21][4].
- Newer config keys (see §1) [6] — none needed for the build below.
- Unloadable sessions "preserved before replacement, rather than silently overwritten.
  Recovery copies are kept in `session-backups/`" (#4125) [7].
- **Heap-corruption abort fixed** — "a row full of links can corrupt memory when it scrolls",
  "all pane children die" (#4174/#3890); the fix (PR #3906) is contained in v0.9.1 [11].
  Whether 0.8.0 carries the bug was not established.
- **Labelled desktop notifications** — the "Notify Send" app-name bug (#3638, reported on 0.8.2)
  is closed and "Released in v0.9.1" [16].

**What remains open or unreleased**

- **Session wipe (#4320):** "Completely Lost all my workspaces/tabs/panes/agents… session.json
  was explicitly cleared" — one reporter, on **0.9.0**, after a host reboot; closed with the fix
  on the **preview channel only**; the thread's 0.9.1 mention is a code reading ("The same
  classification remains in 0.9.1"), not a reproduction [10].
- **Restore into the wrong cwd (#3116, open):** originally reported on **0.8.2** ("the herdr
  server's startup cwd instead of the pane's persisted cwd") — so plausibly present on your
  0.8.0 already. A 0.9.1-on-Arch comment reproduces a *different* variant, a stale OSC 7 cwd [9].
- **Live handoff loses scrollback (#3864, open):** agents show "only an empty input box" after
  0.8.x→0.9.0; a later comment reports scrollback loss on 0.9.0→0.9.1 via a manual
  `herdr server live-handoff` [12]. Handoff is still labelled experimental.

**Tension.** 0.9.1 fixes more than it risks for this workload; the one open data-loss path
(#4320) is bounded by a backup of `session.json`, which 0.9.1 itself partly adds.

**Safe path whenever you do upgrade:** back up `session.json` first, do a clean restart rather
than a live handoff, and treat resume as best-effort (see §9). A 0.8.2 stable also exists but
carries neither the 0.9.x detection fixes nor the #3638 fix.

---

## 4. Everyday configuration

### 4.1 Prefix and direct chords

- herdr defaults to `ctrl+b` — the same as your tmux. The docs' vetted answer is a distinct
  prefix plus **`ctrl+alt` direct chords**, "one modifier family [that] is almost untouched
  everywhere", with each prefix action also bound directly, e.g.
  `focus_pane_left = ["prefix+h", "ctrl+alt+h"]` [2].
- Avoid `ctrl+alt+t`, `ctrl+alt+arrows`, `ctrl+alt+f1..f12` (Linux VT switching) and
  `ctrl+alt+l` (KDE lock) [2]. Your sway config binds no `ctrl+alt` chords (local grep).
- Users coming from tmux mostly moved herdr to `ctrl+a` (madflex: to avoid clashing with the
  remote multiplexer over SSH [24]; Finnie: screen muscle memory [25]); Classmethod chose
  `ctrl+q` [26]. Pressing the prefix twice sends it through, so `prefix+<prefix>` cannot be bound [32].
- **Decisive fact for you:** if herdr ever runs inside tmux (or you SSH into a tmux host from a
  herdr pane), `ctrl+b` collides. If neither happens, keeping `ctrl+b` is harmless.

### 4.2 Never put tmux between herdr and Claude

"Agent detection does not inspect tmux sessions launched inside a Herdr pane… Herdr sees tmux
as the pane process instead of the agent behind it" [3]. Claude must be the pane's foreground
process. Starting tmux *from* a herdr pane also leaks `HERDR_ENV=1` into the tmux server's
global environment, after which herdr refuses to launch from any session of that tmux server
(#2134, closed not-planned by a triage bot for not using the template). The issue's own
workarounds are "kill the whole tmux server and restart it from a non-herdr context" or
`experimental.allow_nested = true` [15]. Your `.bashrc` does not auto-start tmux (local grep),
so today this is a rule, not a fix.

### 4.3 Custom commands (popups)

`[[keys.command]]` with `type = "popup"` opens a session-modal terminal; commands get
`HERDR_ACTIVE_PANE_CWD` and "Shell commands run from the focused pane's working directory";
"Popup commands do not receive HERDR_PANE_ID" [1]. Bind under `prefix+alt+…` — `prefix+g` is
the default `goto`, a clash Classmethod hit [26]. Candidates on this machine: `yazi` (installed)
and a `git diff`/`gh pr view` pager; `lazygit` is **not** installed.

### 4.4 Sidebar and UI

- `[ui.sidebar.agents.rows_by_agent] claude = [...]` exists in 0.8.0 with the
  `terminal_title_stripped` token [19] — Claude Code's own terminal title (its task summary)
  in the sidebar, no hooks needed.
- `hide_tab_bar_when_single_tab`, `prompt_new_tab_name`, `next_agent`/`previous_agent`
  (unset by default), `last_pane` (unset by default) are all 0.8.0 keys [19].
- `agent_panel_sort = "priority"` turns the agent panel into an attention queue instead of
  grouping by space [19] — the relevant mode when several Claude panes may be blocked at once.

### 4.5 Worktrees — two conventions collide

herdr creates checkouts under `[worktrees] directory` (default `~/.herdr/worktrees`) as
`<directory>/<repo>/<branch-slug>`, grouped under the source workspace; closing the group
"does not delete checkout folders or branches", and removal runs `git worktree remove` but
"Branches are not deleted" [1]. Claude Code's own worktrees live in `<repo>/.claude/worktrees`
(your TP Core WS2 pane). `directory` is a single global path, so it cannot point *into* each
repo. herdr's `worktree open` adopts an existing checkout [19]. Built-in worktree creation does
not copy gitignored files such as `.env`; the `herdr-worktreeinclude` plugin exists for that [23].

---

## 5. Theming under the nord ⇄ gruvbox switch

**Facts (v0.8.0 source) [18]**

- Built-ins include `nord`, `gruvbox`, and `terminal` (which uses the host terminal's colours —
  `panel_bg: Color::Reset`).
- `[theme.custom]` accepts exactly 16 tokens in 0.8.0: `accent, panel_bg, surface0, surface1,
  surface_dim, overlay0, overlay1, text, subtext0, mauve, green, yellow, red, blue, teal, peach`.
  0.9.1 documents extra tokens (`sidebar_bg`, `active_row_bg`, `selection_bg`) absent from the
  0.8.0 binary [6][desktop-integrator strings check].
- Layering: built-in → `[theme.custom]` → `[theme.custom.light|dark]` [1].
- `herdr server reload-config` applies theme changes without restarting panes [1].
- The settings UI's theme picker writes `[theme] name` into `config.toml` in place [18].

**Options**

| Option | How switching works | Cost |
|---|---|---|
| **A. `name = "terminal"`** | kitty already renders the palette's 16-colour ramp from `palettes.toml`; herdr inherits it. kitty reloads on SIGUSR1 during `theme`. | No template, no hex, config stays a tracked file. Less control over individual UI roles. |
| B. `[theme.custom]` template from roles | `theme` renders it, then `herdr server reload-config`. | `config.toml` is read at a hardcoded path (or `HERDR_CONFIG_PATH` [18]) — it would join the structural hardcoded-path list CLAUDE.md says is "not growing", and the UI's in-place writes would be lost at the next render. |
| C. switch `name = "nord"/"gruvbox"` | `theme` edits the tracked file | Violates "switching is not a repo change". Rejected. |

**Tension.** A matches the repo's invariants; B matches the repo's *style* (roles, not
built-ins). The `muted`/`dim` legibility rule (§3.1) applies to whatever herdr paints dim text
with — verify A by rendering under both palettes.

---

## 6. Notifications into mako

- `delivery = "system"` on Linux runs `notify-send` with no app name up to 0.8.2 —
  notifications show as "Notify Send" (#3638, fixed in 0.9.1) [16]; the 0.8.0 binary has no
  `--urgency`/`--app-name` strings [desktop integrator]. On 0.8.0 mako cannot tell herdr apart,
  and on no version does anything mark "blocked" as urgent.
- `delivery = "terminal"` emits OSC 99; kitty/foot turn it into a desktop notification, but
  herdr sets no urgency field and foot suppresses notifications while its window has focus [31].
- **The clean route:** a small local plugin with
  `[[events]] on = "pane.agent_status_changed"`, reading `HERDR_PLUGIN_EVENT_JSON`, calling
  `notify-send -a herdr -u critical …` only when `agent_status == "blocked"` [18][4]. Pair it
  with `delivery = "herdr"` (in-app toasts) or `"off"` so desktop notifications are not doubled.
- herdr's own toasts fire for background workspaces; a plugin hook fires on *every* status
  change, including the pane you are looking at. Filtering is the plugin's job (§Implementation
  Brief, open question Q3).

---

## 7. Making herdr work better with Claude

### 7.1 Display-only metadata (safe)

`herdr pane report-metadata --source <ID> <PANE> --token NAME=VALUE --ttl-ms N` feeds `$name`
tokens to sidebar rows; `workspace report-metadata` feeds space rows. "Metadata reports are
display-only… `working`, `blocked`, `idle`, waits, notifications, and rollups still come from
semantic state." Limits: ≤16 tokens per report, ≤32 per pane, TTL 1 ms–24 h; tokens are not
restored after a server restart [5][19]. A Claude hook can push, e.g., a `$task` token without
any risk to state accuracy. `terminal_title_stripped` (§4.4) already covers most of this for free.

### 7.2 Reporting lifecycle state yourself (the biggest tension)

- **For:** `herdr pane report-agent --source custom:… --state idle|working|blocked|unknown`
  exists in 0.8.0 [19]; CHANGELOG 0.6.7 says "custom socket integrations can still report
  state" [7]. In `recompute_effective_state`, a custom source's state beats the screen
  fallback; an on-screen blocker overrides it only when the screen reading is no older than
  the hook report, the hook's state is not already `blocked`, and the hook's agent label
  matches the detected agent (and never for the six built-in full-lifecycle sources) [18].
- **Against:** herdr's docs say Claude-style hooks "can miss permission approval results,
  escape interrupts, or other transitions. For those agents, Herdr still uses screen manifest
  detection" [27].

> **Contested signal — monitor, don't assert:** by the code path above, a
> `UserPromptSubmit → working` report could stick after an Esc interrupt until a `Stop` hook or
> `release-agent` clears it. This is a source reading, not an observed failure.
- **Also against:** open screen-detection bugs cut both ways — idle during an MCP call (#3090),
  working while idle (#3414), stale busy title outranking the blocked dialog (#3467), spinner
  read as idle (#4376), `agent explain` and `agent list` disagreeing (#3993) [13]. Neither
  source of truth is reliable alone.
- **Resolving experiment:** in a throwaway named session, add a `custom:claude` reporter, then
  Esc-interrupt mid-turn, approve/deny a permission prompt, and run `/clear`; compare
  `herdr agent explain` against reality.

### 7.3 Letting one Claude drive others

herdr ships an agent skill (`herdr --skill`) that teaches an agent to split a sibling pane,
`agent start <name> --kind …`, `agent prompt … --wait`, and read results [19]. Rules worth
keeping: `agent prompt --wait` returns `agent_prompt_stalled` if nothing happens in 5 s and
"does not track individual turns" — a coordinator must read output before re-prompting or it
double-sends [28]; `agent wait` takes one target, so fan-out needs a barrier script [30];
long Claude replies live on the alternate screen, so the documented fallback is "write your
answer to a temp file" [28][19]. Your Claude sessions do **not** have the herdr skill today
(`~/.claude/skills` has no `herdr` entry).

---

## 8. Plugins

| Plugin | What it adds | Signal (2026-09-23) | Fit |
|---|---|---|---|
| `persiyanov/herdr-reviewr` | review pane beside an agent: diff scopes incl. "last turn", line comments sent back to the agent, read-only PR view; auto-opens on new worktrees | 761★, pushed today, CI, releases [20] | Best match for review-heavy Claude work; its build step curls a release binary checked only against a same-release `.sha256` |
| `kryptamine/herdr-auto-title` | names tabs/panes from branch or agent task (Go ≥1.24 build) | 213★, pushed today [21] | Needs herdr ≥ 0.8.2 |
| `alexarthurs/herdr-sidebar` | file explorer + git SCM pane | 378★ [22] | Overlaps yazi |
| `serhii-chernenko/herdr-worktreeinclude` | copies `.worktreeinclude`-listed ignored files into new worktrees | [23] | Only if you adopt herdr worktrees |

Mechanics: manifest `herdr-plugin.toml`; `herdr plugin install <gh> --ref <rev>` pins a
revision; there is no `plugin update` ("reinstall from GitHub") [4]. `herdr plugin link <dir>`
registers a local plugin [19] — the route for a plugin kept in this repo. Trust model, verbatim:
herdr "does not review or sandbox what a plugin does"; the marketplace "Listings aren't
reviewed" [4].

---

## 9. Risks and failure modes

- **Restore resumes the wrong conversation after `/clear` or `/resume`** — #1653 is open;
  first reported with the v5 hook on 0.7.4 and later reproduced with the **v7** hook (the one
  installed here) on 0.7.5 [8]. Your server log shows 5 `report_agent_session` errors on
  2026-08-07/08 [local log].
- **Socket = full control.** "Any process with access to `herdr.sock` still gets full RPC
  access to all API methods in stable" (#3727, closed not-planned, consolidated into Ideas
  discussion #514; #481 shows "completed" only because it was converted to that discussion —
  no fix shipped) [14]. One prompt-injected Claude pane can type into every other pane. Perms
  are `0600`, so the boundary is your user.
- **Remote detection manifests change behaviour at runtime.** herdr fetches
  `herdr.dev/agent-detection/index.toml` and "applies valid per-agent rule updates
  automatically without requiring a Herdr restart" [7][skeptic source read].
  `update.manifest_check = false` pins detection to the binary.
- **Churn.** Client/server protocol v5 (0.5.9) → v8 (0.6.0) → v14 (0.7.0) → v19 (0.8.0) →
  v22 (0.9.1), with intermediate bumps; 39 stable releases from 0.4.7 (2026-04-10) to 0.9.1
  (2026-09-16); top-level `wait`/`agent send` replaced in 0.7.5; `--no-session` removed in
  0.9.0 [7][18]. Heavy scripting against the CLI will need maintenance.
- **Bus factor.** One core maintainer: 1259 commits vs. 97 for the next human contributor
  (a triage bot sits between them at 120) [GitHub contributors API] [29].

---

## 10. Contradiction map

| Clash | Side A | Side B | Evidence quality | Resolving question |
|---|---|---|---|---|
| Upgrade now | 0.9.1 fixes Claude detection, the heap crash and notification labels [7][11][16] | #4320 wipe fix is preview-only; handoff loses scrollback [10][12] | Official changelog + triaged issues (high) | Does #4320's fix reach stable 0.9.2? (Backups bound the risk either way.) |
| Claude state source | custom hooks can override screen [7][source] | authors demoted hooks on purpose [27] | Source code vs. documented design (both high) | The Esc / approval / `/clear` experiment (§7.2) |
| Theme | `terminal` keeps repo invariants | role template keeps repo style | Local source (high) | Does `terminal` pass the `dim` legibility floor in both palettes? |
| Notifications | built-in `system` is zero-code | plugin hook gives labelled, critical, blocked-only | Local source + issue #3638 (high) | Can the hook cheaply tell whether the pane is focused? |

**Universal agreement:** check every key against the installed binary, not the website.

**Blind spot → frontier question:** no perspective asked where *attention* should surface on
this desktop. herdr's sidebar, mako and the waybar Claude widget each show a slice. Should
waybar show herdr's count of blocked agents, fed from the same event hook, so there's one
glanceable "who needs me" signal?

---

## 11. Claim-safety guide

| Assert | Caveat | Avoid |
|---|---|---|
| 0.8.0 accepts only the keys in `herdr --default-config`; unknown keys are ignored | 0.9.x detection is better for Claude — but not bug-free | "Hooks make Claude state accurate" |
| Plugin hooks receive `pane.agent_status_changed` in 0.8.0 | resume-on-restore is usually right; wrong after `/clear` in reported cases | "Plugins are safe once installed from the marketplace" |
| herdr writes `config.toml` in place from its settings UI | `terminal` theme legibility is untested here | "Upgrading with `--handoff` is seamless" |
| Any same-user process can drive every pane via the socket | | |

---

## 12. Implementation Brief

*For a coding agent working in `~/repos/dotfiles`. Read `CLAUDE.md` and PLAYBOOK §5.2, §5.3,
§3.1 and §9.29 first. Items resting on a demoted claim are marked ⚠.*

### 12.1 Objective & scope

Bring herdr under the dotfiles repo and extend it for an all-Claude-Code desktop: a tracked
config, palette-following colours, an attention signal routed to mako only when an agent is
**blocked**, Claude-aware sidebar rows, session backups, docs and a consumer check.

- **In scope:** a new `herdr` stow package; one local herdr plugin kept in the repo; a
  `systemd` user timer; README/PLAYBOOK/CLAUDE.md entries; a `check_consumers.sh` check.
- **Out of scope:** upgrading the binary (a separate, user-run step — D1), third-party plugins
  (D5), custom lifecycle-state reporting for Claude (D4), changes to `~/.claude/settings.json`,
  and the xl-skills repo.

### 12.2 Requirements

| # | Requirement | Tag |
|---|---|---|
| R1 | New package `herdr/.config/herdr/config.toml`, adopted from the live file (PLAYBOOK §5.3); `~/.config/herdr` stays **unfolded** | must |
| R2 | Every key exists in `herdr --default-config` of the installed binary; no 0.9-only key | must |
| R3 | No hex anywhere in the package (`theme.name = "terminal"`, D2); `theme_test.sh`'s hex guard covers the new files | must |
| R4 | `setup.sh` fold-guard list gains `$HOME/.config/herdr` | must |
| R5 | README package table + PLAYBOOK §5.2 row stating: unfolded because herdr writes sockets, logs, `session.json`, `plugins.json`, `plugins/`; the settings UI rewrites `config.toml` **in place**, so those edits show up as repo diffs — commit or revert, like §9.1 | must |
| R6 | A local plugin (`attention`) hooks `pane.agent_status_changed`, and on `blocked` sends `notify-send -a herdr -u critical`; it never touches the network, exits in well under a second, and never blocks herdr | should |
| R7 | The plugin skips the pane the user is looking at, and does not re-notify for the same blocked episode | should |
| R8 | `ui.toast.delivery` moves from `"system"` to `"herdr"` so blocked alerts are not doubled | should |
| R9 | Claude sidebar row via `[ui.sidebar.agents.rows_by_agent] claude = …` with `terminal_title_stripped` (plain tokens only — styled tokens fail hard on typos) | should |
| R10 | Keys: `ctrl+alt+h/j/k/l` direct pane focus alongside prefix bindings; bind `next_agent`/`previous_agent` and `last_pane`; `yazi` popup on `prefix+alt+y`; prefix per D7 | should |
| R11 | `systemd` user timer that copies `~/.config/herdr/session.json` to `$XDG_STATE_HOME/herdr-backup/` with rotation (keep N) | should |
| R12 | CLAUDE.md gotchas: never bare `herdr` / `herdr server stop` from a test; settings UI writes the tracked file; never run tmux between herdr and Claude | must |
| R13 | `check_consumers.sh` asks herdr whether it accepts the config (see Q1) | should |
| R14 | waybar shows a count of blocked herdr agents, fed by the same hook | could |

### 12.3 Key decisions (mini-ADRs)

| ID | Decision | Rejected | Evidence |
|---|---|---|---|
| D1 | **Build against 0.8.0 keys; upgrade to 0.9.1 as a separate user-run step** after R11 exists, via clean restart, not live handoff | Upgrading first; staying on 0.8.0 indefinitely | 0.9.1 only adds keys (§1); fixes detection/crash/labels [7][11][16]; #4320 preview-only [10]; handoff loses scrollback [12] — conf 8 |
| D2 | `theme.name = "terminal"` — herdr inherits kitty's palette-rendered ANSI ramp; no template | `[theme.custom]` template (hardcoded-path render list, clobbers UI writes); switching `name` (switch becomes a repo change) | [18] `state.rs`, `config_io.rs`; CLAUDE.md conventions — conf 8. ⚠ legibility untested (Q2) |
| D3 | Blocked-only notifications via a local plugin `[[events]]` hook | Built-in `system` delivery (unlabelled on 0.8.0, no urgency); OSC 99 `terminal` delivery (no urgency, focus-suppressed in foot) | [18] `PLUGIN_HOOK_EVENT_KINDS`; [16][31] — conf 9 |
| D4 | **No** custom lifecycle reporting for Claude; keep the official v7 integration (session identity) | `report-agent` from Claude hooks | Authors' design [27]; ⚠ stuck-`working` risk (demoted); open detection bugs either way [13] — conf 7 |
| D5 | No third-party plugins in this build; `herdr-reviewr` is an opt-in trial, installed with `--ref <tag>` after reading its install preview | Installing auto-title (needs ≥0.8.2), sidebar (overlaps yazi) | [4][20][21] — conf 9 |
| D6 | Keep Claude Code's `.claude/worktrees`; don't set `[worktrees] directory`; bind `open_worktree` to adopt existing checkouts | Moving to `~/.herdr/worktrees` | [1] — conf 7 |
| D7 | Prefix: **UNRESOLVED — user decision.** `ctrl+b` if herdr never runs inside tmux and you never ssh into tmux hosts from herdr; else `ctrl+a` | — | [2][24][25] |

### 12.4 Constraints & assumptions

- The repo lives at `~/repos/dotfiles`; `.stowrc` pins the target. Run `stow -n -v herdr` before
  `stow herdr`. Stow exits 0 on wrong links — verify with `readlink`.
- The live file must be moved into the package before stowing (adoption), or stow conflicts.
- Plugin source must **not** live under `~/.config/herdr/plugins/` — herdr owns that path
  (`plugin_paths.rs`: `config_dir().join("plugins")`) [18].
- Assumes kitty stays `$term`; `terminal` theme under foot shows foot's colours, which do not
  live-reload.
- Assumes the plugin hook runs as the user with `HERDR_BIN_PATH`, `HERDR_WORKSPACE_ID`,
  `HERDR_PANE_ID` and `HERDR_PLUGIN_EVENT_JSON` in its environment [18 `runtime.rs`].

### 12.5 Shapes

Package layout:

```text
herdr/
└── .config/herdr/
    ├── config.toml                      # tracked, file-symlinked (dir unfolded)
    └── local-plugins/attention/         # folded subdir is fine: herdr never writes here
        ├── herdr-plugin.toml
        └── notify.sh
systemd/.config/systemd/user/herdr-session-backup.{service,timer}
```

Plugin manifest (fields from `RawPluginManifest` at `v0.8.0` [18]):

```toml
id = "local.attention"
name = "Attention"
version = "0.1.0"
description = "Critical mako notification when an agent is blocked"

[[events]]
on = "pane.agent_status_changed"
command = ["sh", "notify.sh"]   # runs with cwd = plugin_root (command_for_argv_in_dir)
```

Event payload in `HERDR_PLUGIN_EVENT_JSON` — fields sit under `data`, tagged by `type` [18
`events.rs`; C2 voters]:

```json
{"event": "pane_agent_status_changed",
 "data": {"type": "pane_agent_status_changed", "pane_id": "w1:p2", "workspace_id": "w1",
          "agent_status": "blocked", "agent": "claude", "title": "…"}}
```

Shape read from `EventEnvelope` + `EventData` (`#[serde(tag = "type", rename_all = "snake_case")]`)
at `v0.8.0`; still capture one real event before writing the parser (Q3). herdr caps
concurrent plugin commands (`MAX_PLUGIN_COMMANDS_IN_FLIGHT`) and logs a failure past it — the
hook must exit fast.

Config sketch (0.8.0 keys only; values are proposals):

```toml
onboarding = false

[theme]
name = "terminal"
auto_switch = false

[keys]
# prefix = D7
focus_pane_left  = ["prefix+h", "ctrl+alt+h"]
focus_pane_down  = ["prefix+j", "ctrl+alt+j"]
focus_pane_up    = ["prefix+k", "ctrl+alt+k"]
focus_pane_right = ["prefix+l", "ctrl+alt+l"]   # safe on sway: no ctrl+alt bindings (local grep)
open_worktree = "prefix+alt+o"

[[keys.command]]
key = "prefix+alt+y"
type = "popup"
command = "yazi"
width = "85%"
height = "85%"

[ui]
show_agent_labels_on_pane_borders = true
agent_panel_sort = "spaces"

[ui.toast]
delivery = "herdr"

[ui.sidebar.agents.rows_by_agent]
claude = [["state_icon", "workspace", "tab"], ["terminal_title_stripped"]]
```

`next_agent`, `previous_agent` and `last_pane` default to unset; the key names are confirmed,
but **chords are UNRESOLVED** — pick free ones after reading `herdr --default-config` for
clashes, then check the reload diagnostics (Q1).

### 12.6 Interfaces

- `herdr plugin link <dir>` / `unlink` / `list` / `log` (0.8.0) [19].
- `herdr server reload-config` — applies most settings live [1]. Run it only from the user's
  shell, never from a test against the live server.
- `notify-send -a herdr -u critical <summary> <body>`; optional mako rule `[app-name=herdr]` in
  `mako/.config/mako/config` (colours through the existing template roles only).
- `herdr pane get <id>` / `herdr pane current` for the focus check (R7) — which field says
  "focused" is UNRESOLVED (Q3).

### 12.7 Gotchas & failure modes

| Trap | Detect / prevent |
|---|---|
| Settings UI rewrites the tracked `config.toml` | `git status` after touching herdr's settings; commit or revert |
| A 0.9-only key in config does nothing on 0.8.0 | Reload diagnostics say "unknown config key …; ignoring key" |
| Typo inside a styled sidebar token fails the **whole** parse | Use plain token strings only (R9) |
| tmux between herdr and Claude breaks detection; tmux started from herdr poisons its env | Rule in CLAUDE.md (R12) |
| Hook fires for the focused pane too → notification spam | R7 filter; `blocked` only |
| Tests that `pkill`/stop by name hit the live desktop (the §9.29 lesson) | Tests use a named throwaway session and kill only PIDs they started |
| Resume after `/clear` reopens the wrong conversation (#1653) | Don't trust auto-resume for panes that ran `/clear` or `/resume` |
| Any pane can drive any other via the socket | Don't give agents unattended herdr-control permissions you would not give a shell |

### 12.8 Open questions blocking implementation

| # | Question | Resolving step |
|---|---|---|
| Q1 | What is the non-live validator for `config.toml` (the `mako --config` equivalent)? | Try `HERDR_CONFIG_PATH=<tmp> XDG_CONFIG_HOME=<tmp> herdr --session herdr-check …` in a throwaway session, read the diagnostics, then stop **that** session by name only |
| Q2 | Does `name = "terminal"` meet the `dim` 4.5:1 floor in both palettes? | Render under nord and gruvbox, screenshot, measure (PLAYBOOK §9.28) |
| Q3 | Exact `HERDR_PLUGIN_EVENT_JSON` shape, and how to tell whether a pane is focused | Link a plugin whose hook writes `$HERDR_PLUGIN_EVENT_JSON` to a file in a throwaway session |
| Q4 | ~~Is an `[[events]] command` run relative to `plugin_root`?~~ **Resolved:** yes — `command_for_argv_in_dir(&program, &args, &plugin_root)` [18] | — |
| Q5 | Prefix (D7) | User |
| Q6 | Upgrade timing (D1): now, or wait for #4320 in stable | User |

### 12.9 Build sequence

1. Branch `feat/herdr-package` (repo convention: branch → PR → CodeRabbit → merge).
2. Resolve Q1 (validator) and Q3 (event capture, focus field) in a named throwaway session.
3. Create `herdr/.config/herdr/config.toml` from the live file plus §12.5; `git mv`-style
   adoption per PLAYBOOK §5.3; `stow -n -v herdr`, then `stow herdr`; `readlink` check.
4. Add `~/.config/herdr` to `setup.sh`'s fold-guard list; README row; PLAYBOOK §5.2 row.
5. Write `local-plugins/attention/`; `herdr plugin link`; trigger a blocked prompt in a spare
   pane; confirm exactly one critical mako notification, and none for the focused pane.
6. Flip `ui.toast.delivery` to `"herdr"`; `herdr server reload-config` from your own shell.
7. `herdr-session-backup` service + timer in the `systemd` package; enable it; check a copy lands.
8. Theme: set `name = "terminal"`, then `theme gruvbox` → `theme nord`; check Q2 by rendering.
9. Add a herdr check to `tests/check_consumers.sh` (Q1's validator; `skip` when herdr is absent).
10. CLAUDE.md gotchas + a PLAYBOOK §9.30 "herdr" section.
11. Run `sh tests/theme_test.sh` and `sh tests/check_consumers.sh`; ship.
12. *(User, separately)* upgrade to 0.9.1 per D1, after step 7 has run at least once.

---

## References

1. herdr docs 0.8.0 — Configuration. https://herdr.dev/docs/0.8.0/configuration/
2. herdr docs — Keyboard. https://herdr.dev/docs/keyboard/
3. herdr docs 0.8.0 — Agents. https://herdr.dev/docs/0.8.0/agents/
4. herdr docs — Plugins (and 0.8.0 variant); plugin marketplace. https://herdr.dev/docs/plugins/ · https://herdr.dev/docs/0.8.0/plugins/ · https://herdr.dev/plugins/
5. herdr docs — Socket API. https://herdr.dev/docs/socket-api/
6. herdr docs — Config reference (0.9.1). https://herdr.dev/docs/config-reference/
7. herdrdev/herdr CHANGELOG.md. https://github.com/herdrdev/herdr/blob/master/CHANGELOG.md
8. Issue #1653 (restore resumes pre-`/clear` session); #4059 dup. https://github.com/herdrdev/herdr/issues/1653
9. Issue #3116 (restore in server startup cwd). https://github.com/herdrdev/herdr/issues/3116
10. Issue #4320 (session.json cleared). https://github.com/herdrdev/herdr/issues/4320
11. Issues #4174 / #3890 (heap corruption abort). https://github.com/herdrdev/herdr/issues/4174
12. Issue #3864 (handoff loses scrollback). https://github.com/herdrdev/herdr/issues/3864
13. Issues #3090, #3414, #3467, #4376, #3993 (Claude state detection). https://github.com/herdrdev/herdr/issues/3090
14. Issue #3727 / #481 → discussion #514 (socket access). https://github.com/herdrdev/herdr/issues/3727
15. Issue #2134 (HERDR_ENV leaks into tmux). https://github.com/herdrdev/herdr/issues/2134
16. Issue #3638 (notify-send app name). https://github.com/herdrdev/herdr/issues/3638
17. Issue #4555 (herdr inside tmux redraw loop, 0.9.1/WSL2). https://github.com/herdrdev/herdr/issues/4555
18. local: herdr source at tag `v0.8.0` — `src/api/schema/events.rs` (`PLUGIN_HOOK_EVENT_KINDS`), `src/config/theme.rs` (`CustomThemeColors`), `src/app/config_io.rs` (`update_config_file`), `src/config/io.rs` (unknown-key diagnostics), `src/config.rs` (`HERDR_CONFIG_PATH`).
19. local: herdr 0.8.0 binary — `--help`, `--default-config`, `--skill`, `pane report-metadata|report-agent --help`, `plugin --help`, `worktree --help`, `api schema --json`.
20. persiyanov/herdr-reviewr. https://github.com/persiyanov/herdr-reviewr
21. kryptamine/herdr-auto-title. https://github.com/kryptamine/herdr-auto-title
22. alexarthurs/herdr-sidebar. https://github.com/alexarthurs/herdr-sidebar
23. serhii-chernenko/herdr-worktreeinclude. https://github.com/serhii-chernenko/herdr-worktreeinclude
24. madflex — Trying herdr instead of tmux. https://madflex.de/trying-herdr-instead-of-tmux/
25. Josh Finnie — Switching to herdr. https://www.joshfinnie.com/blog/switching-to-herdr/
26. Classmethod — herdr as a tmux replacement. https://dev.classmethod.jp/en/articles/herdr-tmux-replacement/
27. herdr docs (next) — Integrations; `src/detect/mod.rs` `full_lifecycle_hook_authority()`. https://github.com/herdrdev/herdr/tree/master/docs
28. herdr docs — Agent automation. https://herdr.dev/docs/agent-automation/
29. bitdoze — Herdr review (weak: ~0.7.3, contradicts session restore). https://www.bitdoze.com/herdr-agent-multiplexer/
30. Rianico/harness-zkx issue #92 (fan-out barrier). https://github.com/Rianico/harness-zkx/issues/92
31. local: `man foot.ini`, desktop-notifications section (OSC 99, `${urgency}`, focus inhibition).
32. herdr discussion #862 (double prefix). https://github.com/herdrdev/herdr/discussions/862
