# Claude usage waybar widget — design

**Date:** 2026-08-22 · **Status:** approved (post adversarial review r1) · **Scope:** Claude Code
only (multi-agent tabs like Omarchy Quattro's are explicitly out of scope for now)

## §0 Background

Replicates the content of Omarchy 4 "Quattro"'s agent status widget — plan limits with reset
countdowns, tokens by day, tokens by model — for this repo's vertical waybar. Quattro renders its
panel in Quickshell (Omarchy 4 dropped waybar entirely); here the panel becomes a rich Pango hover
tooltip, the lightest option available to waybar. Prior art surveyed and rejected:
[claudebar](https://github.com/mryll/claudebar) (Bash, limits only, horizontal-bar oriented,
*writes* OAuth token refreshes into `~/.claude/.credentials.json`) and
[ai-usagebar](https://github.com/akitaonrails/ai-usagebar) (Rust, multi-provider, heaviest to
adapt). Decision: build our own (user-approved), because neither does the token charts, both fight
the 45px vertical bar, and read-only credential access is a hard requirement here.

Hard requirements from the user: extremely lightweight; 5-minute refresh; manual refresh
(tooltip-only design ⇒ left-click the bar icon, deliberately chosen over the original
`r`-in-popup idea); `nf-cod-claude` (U+EC82) as the icon; bar shows session %, weekly %, and
Fable-weekly % stacked.

## §1 Terms

- **Session limit** — the 5-hour rolling usage window (`kind: "session"` in the API).
- **Weekly limit** — the 7-day all-models window (`kind: "weekly_all"`).
- **Scoped weekly limit** — a per-model 7-day window (`kind: "weekly_scoped"`, labelled from
  `scope.model.display_name`; currently "Fable" on this account).
- **Stale** — UI state when limits could not be refreshed (expired token, network, 429/5xx);
  last-known data shown, marked with age.

## §2 Architecture

One Python 3 stdlib-only script: `waybar/.config/waybar/scripts/claude_usage.py` in the dotfiles
waybar package (package is folded — the new file appears in `~/.config/waybar/scripts/` without
restow; underscore name so the test suite can import it as a module). No daemon, no popup, no
third-party deps.

Waybar wiring (`config`):

```jsonc
"custom/claude": {
    "exec": "~/.config/waybar/scripts/claude_usage.py",
    "return-type": "json",
    "interval": 300,
    "signal": 8,             // signal 1 is taken by custom/keyboard-layout
    "exec-on-event": false,  // default true would race a third process on every click
    "format": "{}",
    "justify": "center",
    "on-click": "~/.config/waybar/scripts/claude_usage.py --refresh; pkill -RTMIN+8 waybar"
}
```

Module sits in `modules-right`, between `custom/network` and `clock`. The click path forces a
fetch, writes state, then signals waybar; the re-exec'd module reads the just-written cache, so no
double fetch. Concurrency: every run takes an exclusive `flock` on the state file for its whole
read-modify-write; a `--refresh` result can therefore never be clobbered by a slower interval run
that started earlier. `--refresh` is debounced: if the last *forced* fetch was under 30s ago it
reuses the cache (click-spamming must not be able to 429 the widget into staleness).

## §3 Data sources

### §3.1 Limits — OAuth usage API

`GET https://api.anthropic.com/api/oauth/usage` with headers `Authorization: Bearer <accessToken>`
and `anthropic-beta: oauth-2025-04-20`, with a 5-second connect/read timeout. Token from
`~/.claude/.credentials.json` (`claudeAiOauth.accessToken`, `.expiresAt` ms-epoch), **read-only —
this widget never refreshes or writes the token**; Claude Code's own daemon rotates it. If
`expiresAt` has passed, skip the call (stale path).

The endpoint is undocumented with aggressive rate limits — never call more often than every 300s
(cache TTL), except an explicit `--refresh`, itself debounced to 30s (§2).

Consume the generic `limits[]` array, not the legacy top-level fields (verified live 2026-08-22):

```json
{ "limits": [
  { "kind": "session",       "group": "session", "percent": 44, "severity": "normal",
    "resets_at": "2026-08-22T03:20:00+00:00", "scope": null, "is_active": false },
  { "kind": "weekly_all",    "group": "weekly",  "percent": 41, "...": "..." },
  { "kind": "weekly_scoped", "group": "weekly",  "percent": 70,
    "resets_at": "...", "scope": { "model": { "display_name": "Fable" } }, "is_active": true }
] }
```

Row selection: **every `limits[]` entry, always, in API order** — `is_active` is ignored so the
bar height never jitters. Row label: `session` → "Session", `weekly_all` → "Weekly",
`weekly_scoped` → `"{display_name} Wk"`. Unknown kinds render with their raw `kind` rather than
being dropped.

### §3.2 Token charts — Claude Code JSONL logs

Source: `~/.claude/projects/**/*.jsonl` (265MB / 402 files at design time, 202 of them within the
8-day mtime window — full reparse per tick is prohibited). Each relevant line has `timestamp`,
`message.model`, `message.usage.{input_tokens, output_tokens, cache_creation_input_tokens,
cache_read_input_tokens}`, `message.id`, `requestId`.

Incremental aggregation per tick:

- Per-file state `{size, mtime, offset}`: unchanged files skipped; grown files read from stored
  `offset`; shrunk/replaced files (size < offset) re-read from 0. State entries for files that no
  longer exist are dropped.
- Files with mtime older than 8 days are never opened (their lines are already in the aggregates).
- Cheap `'"usage"'` substring prefilter before `json.loads` on each line; malformed lines skipped.
- Dedup by `(message.id, requestId)` in **one global seen-set over all lines regardless of source
  file**. Duplication is dominated by the *within-file* case — one line per content block, each
  repeating the full usage object (measured: 396 usage lines → 201 distinct ids in a single file);
  cross-file duplication from session resumes is the smaller effect. Duplicate lines carry
  byte-identical usage, so first-seen wins. Seen-set entries carry the message timestamp and are
  pruned past 8 days.
- Aggregate: `(local-date, model) → tokens` where tokens = input + output + cache_creation +
  cache_read (matches Quattro's headline numbers; user chose this over input+output only).
  Days split at **local midnight**; model chart window = last 7 days; aggregate rows older than
  8 days are pruned. All three state structures are therefore bounded.

Missing/corrupt state ⇒ silent full rebuild. During a rebuild, lines are pre-screened by locating
`"timestamp"` from the **end** of the line (`line.rfind`) — the field sits near the end of Claude
Code's JSONL lines, after the potentially huge `message` object — and skipping lines older than
8 days before full parse. The rebuild runs inside one waybar exec: the module is blank until it
returns (one-time cost, order of seconds; accepted).

### §3.3 State file

`~/.cache/claude-usage/state.json` — persists across reboots so the full parse happens once ever.
Holds: fetched `limits[]` + fetch timestamp + last-forced-fetch timestamp, per-file scan state,
day×model aggregates, timestamped dedup set. Written atomically (tmp + rename) under the
exclusive `flock` described in §2.

## §4 Rendering

Reads the 13 theme roles from `~/.config/sway/theme.gen.env` at runtime (the repo's script
convention, PLAYBOOK §9.6) for tooltip Pango colours; bar colours come from waybar CSS classes.
**Every externally sourced string** (model display names, raw `kind`s, prettified model ids,
`subscriptionType`/`rateLimitTier`) **is Pango-markup-escaped before interpolation**, and the
module's stdout object is produced by `json.dumps`, never hand-assembled (cf. `netspeed.sh`'s
quote-only escaping — a bug not to copy).

**Bar** (45px vertical, every line ≤4 chars): U+EC82 icon, then one stacked percent per `limits[]`
row — session, weekly, each scoped weekly (currently: Fable) — e.g. `\n44\n41\n70`.
Module class = `normal` | `warning` (worst limit ≥70%) | `critical` (≥90%) | `stale`; `style.css`
colours these with FG/WARNING/CRITICAL/MUTED roles via `#custom-claude.<class>`.

**Tooltip** (Pango; the entire body wrapped in `<span face="JetBrainsMono Nerd Font">` — a bare
`<tt>` resolves to the fontconfig `monospace` default (NotoSansMono here), which lacks U+EC82 and
U+27F3 and would wreck the character grid; layout per approved mockup
`2026-08-22-claude-usage-widget-mockup.html` beside this spec):

- Header: ` Claude Code · <subscriptionType/rateLimitTier>` (from credentials file).
- Stale banner when applicable: `⚠ stale — <reason>, data from <HH:MM>` in WARNING colour.
- LIMITS: one row per `limits[]` entry — label, 16-cell `█`/`░` bar (fill colour INDICATOR,
  ≥70% WARNING, ≥90% CRITICAL; track SEL), percent, `<countdown>` prefixed by `nf-fa-arrow_rotate_left`
  U+F0E2 (user-chosen; the mockup's ⟳ U+27F3 is **absent** from JetBrainsMono NF. U+F0E2 verified
  in the installed build's cmap as glyph `fa-undo` — Font Awesome's pre-FA6 name for the same
  arrow-rotate-left glyph) — countdown from `resets_at` (UTC→local, `3h 13m` / `4d 22h` style).
- TOKENS BY DAY: last 7 local days, oldest first, weekday names with **Today** last; bars scaled
  to the max day; values humanised (`7.9M`, `141.8M`, `1.0B` — ≤6 chars, right-aligned).
- TOKENS BY MODEL (7d): descending by tokens; model ids mapped to display names
  (`claude-fable-5`→`Fable 5`, `claude-opus-5`→`Opus 5`, `claude-sonnet-5`→`Sonnet 5`,
  `claude-haiku-4-5*`→`Haiku 4.5`; unknown ids prettified from the raw id; `<synthetic>` rows
  excluded).
- Footer: `updated <HH:MM> · click  to refresh` in MUTED.

## §5 Error handling

| Condition | Behaviour |
|---|---|
| Token expired / credentials unreadable | No API call; last-known limits, `stale` class + banner |
| Network error / 5s timeout / 429 / 5xx / unexpected 401·403 | Keep last-known limits, `stale`; retry next tick (no special backoff — tick is already ≥300s) |
| Never logged in, no cache | Icon + `–`, tooltip "not logged in", `stale` |
| Corrupt state file | Rebuild from scratch, no user-visible error |
| Malformed JSONL line | Skip line |
| theme.gen.env missing | Fall back to Pango **named** colours (`grey` etc.) — never undefined (PLAYBOOK §9.10), and never hex literals, which `tests/check_hex.py` scans every tracked file for |

Diagnostics to stderr only (lands in the waybar journal); the UI signals problems solely through
the stale state. Because the banner always carries the data's age, a permanent failure
(credentials schema change) is visibly different from a one-tick blip without extra machinery.

## §6 Testing

Stdlib `unittest` beside the existing `tests/` (`tests/claude_usage_test.py`), importing
`claude_usage.py` directly as a module (underscore filename, path inserted via `sys.path` or
`importlib.util.spec_from_file_location`). Covers: aggregator (offset resume, unchanged-file
skip, shrunk-file re-read, **within-file** and cross-file dedup, local-midnight bucketing, 8-day
pruning of aggregates/seen-set/file-states), humanised number formatting, countdown formatting,
limits[] → rows mapping incl. unknown kinds, Pango escaping of hostile strings, class thresholds,
stale paths, `--refresh` debounce. API fetch verified manually (done during design, §3.1). No
network or live-file access in tests.

## §7 Deployment

Files touched, all in the dotfiles repo:

- `waybar/.config/waybar/scripts/claude_usage.py` (new)
- `waybar/.config/waybar/config` — module block + `modules-right` entry (module must live in
  `config` only, never also in an included file, PLAYBOOK §9.12)
- `waybar/.config/waybar/style.css` — `#custom-claude` class colours
- `tests/claude_usage_test.py` (new)
- `claude/.claude/statusline.py` — rate-limit thresholds `50, 80` → `70, 90` (line ~229) and the
  line-224 comment reversed per user ruling: rate limits cost delivery speed, not output quality;
  context degrades quality, so *context* (60/85) keeps the earlier warning. One machine-wide
  definition of warning/critical for rate limits: 70/90.
- PLAYBOOK/CLAUDE.md notes at ship time.

Implementation gate — **cleared 2026-08-22 during planning**: U+EC82 verified as glyph
`cod-claude` and U+F0E2 as `fa-undo` (= `nf-fa-arrow_rotate_left`) by parsing the cmap/post tables of the installed
`/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf` directly (the `statusline.py` precedent
— this font build is documented to remap codepoints vs the upstream cheat sheet). Reload via the
usual waybar restart; no sway changes.

## §8 Honest caveats

- `/api/oauth/usage` is undocumented; the `limits[]` shape, the `anthropic-beta` header value,
  and its tolerance of a 300s cadence may all change without notice. Consuming `limits[]`
  generically softens but does not remove this risk. Breakage degrades to `stale`, never crashes.
- `~/.claude/.credentials.json` staying a plain-readable file with this schema is assumed; a
  Claude Code move to a keyring leaves the widget permanently stale (visible via the banner age)
  until adapted.
- Token counts are client-side log parsing; they will not exactly match Anthropic's server-side
  accounting (retries, other devices, claude.ai usage are invisible here).
- First-seen dedup assumes duplicate lines keep carrying byte-identical usage objects (measured
  true today, 137/137 groups).
- The dedup set and aggregates trust JSONL `timestamp` fields; clock changes mid-day can
  double-count at the margin. Accepted.
- If Claude Code's `cleanupPeriodDays` is ever set below 8, deleted-file lines older than the
  scan horizon would silently vanish from charts mid-window. Not guarded; noted.
- Fable-weekly on the bar assumes scoped weekly limits stay ≤2 on this account; more scoped
  limits would lengthen the bar module (it grows gracefully, just taller).
