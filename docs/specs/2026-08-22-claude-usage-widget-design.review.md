# Adversarial review log — claude-usage-widget design, round 1

**Date:** 2026-08-22 · **Reviewer:** cold Fable subagent (no conversation access) ·
**Verdict:** APPROVE-WITH-CHANGES · **Outcome:** all findings resolved in spec rev "post
adversarial review r1"; no round 2 (no architectural change).

| # | Finding (short) | Sev | Adjudication | Resolution in spec |
|---|---|---|---|---|
| F1 | Hardcoded hex fallback would fail `tests/check_hex.py` (scans every tracked file) | High | Accepted — verified against check_hex.py source | §5: fallback uses Pango *named* colours |
| F2 | Dedup specced "across files"; within-file duplication dominant (396→201 ids in one file, independently reproduced) | High | Accepted — verified by own measurement | §3.2: one global seen-set; §6: within-file test case |
| F3 | "≤5 chars" vs mockup's 6-char values | Mod | Accepted | §4: ≤6 chars, right-aligned |
| F4 | `exec-on-event` defaults true → up to 3 concurrent runs per click; no single-writer | Mod | Accepted — verified in man waybar-custom | §2: `exec-on-event: false` + exclusive flock |
| F5 | No fetch timeout (urllib blocks forever); 401/403 bucket unstated | Mod | Accepted | §3.1/§5: 5s timeout; 401/403 → stale bucket |
| F6 | `<tt>` resolves to NotoSansMono (no U+EC82/U+27F3) → ragged grid | Mod | Accepted | §4: body wrapped in `<span face="JetBrainsMono Nerd Font">` |
| F7 | "Timestamp prefix" check impossible — field near line end | Low-mod | Accepted | §3.2: `rfind('"timestamp"')` from line end |
| F8 | U+EC82 identity unverified in installed font build (repo precedent: remapping) | Low-mod | Accepted | §7: cmap/post verification gate before implementation |
| F9 | "Active scoped weekly" predicate undefined; `is_active` flips | Low | Accepted | §3.1: every `limits[]` entry, always, in API order |
| F10 | 70/90 diverges from statusline's 50/80 for same percentages | Low | **User ruling**: keep 70/90 AND change statusline to 70/90; its comment's reasoning reversed (rate limits cost speed, context costs quality — context keeps 60/85) | §7: statusline.py change added to scope |
| F11 | Unescaped external strings in Pango markup; hand-assembled JSON | Low | Accepted | §4: escape all external strings; emit via json.dumps |
| F12 | File count wrong (402 not ~200); first-tick rebuild, state growth bounds, test import mechanism unstated | Low | Accepted | §3.2/§3.3/§6: corrected count, blank-first-tick stated, all state pruned/bounded, underscore filename + importlib |

Reviewer's top-3 fragile assumptions adopted as §8 caveats: API cadence/header stability,
credentials file schema stability, JSONL corpus behaviour (byte-identical duplicates,
`cleanupPeriodDays ≥ 8`). Plus §2 gained a 30s `--refresh` debounce (click-spam → self-inflicted
429 risk, from assumption 1).
