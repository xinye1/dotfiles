# Migrating this laptop to Omarchy 4: research, judgement and plan

*STORM research report, 2026-09-25. Subject: Omarchy 4 "Quattro", **pinned to the released tag
v4.0.4** (`c668141`, 2026-09-15), against this repo at `4979873` and the live machine `xps-eos`.
Consumer: Xinye (decision-maker) and a later Claude session that executes the Implementation Brief.*

*Source note: the research read the development branch `omacom/omarchy@quattro` (c3e67f5,
2026-09-24), which has **diverged** from the release — 555 commits ahead of and 109 behind v4.0.4.
Phase 5 re-checked every source-code claim against the v4.0.4 tag; nearly all files are
identical. The few that are not are marked **(dev branch only)**.*

> **Verification banner:** 29 load-bearing claims checked by 87 adversarial votes (3 independent
> refute-by-default checkers each, against the v4.0.4 tag and primary sources) · **1 killed**
> (Super+grave drop-down "in the release" — dev branch only) · **21 corrected** for precision ·
> **2 demoted** (rollback breakage: one unconfirmed reporter; TPM "v1" quote: an unshipped plan,
> replaced by direct evidence) · 0 fabricated sources found. Details in
> [§12](#12-verification-record).

---

## 0. Executive summary

**What Omarchy 4 is.** Omarchy is DHH's opinionated Arch Linux distribution. Version 4 ("Quattro",
v4.0.0 on 2026-08-14, v4.0.4 on 2026-09-15) is no longer "dotfiles plus scripts". It is two pacman
packages (`omarchy`, `omarchy-settings`) living under `/usr/share/omarchy`, a Hyprland compositor
configured in **Lua**, and **one Quickshell process** (`quickshell -p $OMARCHY_PATH/shell`, logged
as `omarchy-shell`, which is also the name of its IPC CLI) that is the bar, launcher,
notifications, OSD, clipboard, polkit dialog, idle manager and lock screen [1][2][61]. It installs from
its own ISO onto a whole disk (btrfs, Limine, snapper; LUKS on by default) [6] and updates through
`omarchy update`, which snapshots root, runs migrations, and deliberately blocks a bare
`pacman -Syu` [8][9].

**The settled facts that decide most of the plan:**

1. **Omarchy 4 removed the components this repo spends most of its effort on.** "Waybar, Walker,
   Mako, SwayOSD, hyprlock, hypridle, swaybg, and polkit-gnome are all gone" [1], and the compositor
   is Hyprland, not sway. `sway`, `waybar`, `mako`, `fuzzel`, `nwg-drawer`, `kanshi`, `gtk`, the
   lock/idle/power/screenshot scripts, `keyhint.sh` and `waybar_run.sh` have **nothing to attach
   to**. They cannot be ported, only re-implemented — and re-implementing them on Hyprland would be
   rebuilding the thing you are migrating to get.
2. **Omarchy's ownership model matches this repo's philosophy.** Omarchy's defaults live in
   `/usr/share/omarchy`; your home directory (`~/.config`, `~/.bashrc`, …) is seeded once from
   `/etc/skel` at user creation and is yours thereafter; your Hyprland files are loaded *after*
   Omarchy's so "package updates can improve the defaults without rewriting your ~/.config/hypr
   files" [2][4]. The manual's one line on versioning them is "Stow is a great way to do that",
   linking a video [3]. Themes are one `colors.toml` of semantic roles rendered into `*.tpl`
   templates — the same idea as `palettes.toml` → `*.tmpl` [12].
3. **Omarchy already ships, often better, several things you built by hand**: a keybinding
   cheat-sheet built from `hyprctl binds` plus a cache derived from the config source (yours is a
   hardcoded yad array that §7 admits drifts) [21]; a scratchpad on Super+S — and, on the dev
   branch only, a drop-down "Quake console" on your exact key, Super+grave [22][23]; a Claude usage panel that
   reads `.credentials.json` and never refreshes a token — your §9.23 rule [24]; a supervised shell
   [25]; a lock screen that reads a local theme background, never the network [62];
   and live re-colouring of running **foot** terminals via OSC escape sequences [14] — which
   removes the reason you moved from foot to kitty (§9.11).
4. **Several things you built encode knowledge Omarchy lacks**: a measured contrast floor (Omarchy's
   Nord `dark_foreground` is ~2.5:1 on its background [13] — knowingly given up by D4); a server's never-sleep-on-AC policy
   (Omarchy's lid switch still suspends on AC when undocked [34][35]); the herdr blocked-agent alert; and
   orphan-proof bar supervision (Omarchy's supervisor restarts but doesn't use `pdeathsig`) [25].
5. **The server role is where Omarchy's defaults are wrong for you** — not dangerously, but in six
   specific, fixable ways: ufw blocks the tailnet unless `tailscale0` is opened [37][38]; Docker is
   socket-activated so `restart: unless-stopped` containers don't return after a reboot [39]; no
   user lingering [64]; the lid suspends on AC; root snapshots would roll back
   `/var/lib/jellyfin` with the OS [10]; and the stable channel's month-delayed mirror carries
   Jellyfin **10.11.11** while you run **12.1**, which cannot be downgraded [43][44].

**Verdict — migrate, conditionally, and adopt far more than you port.**

| Layer | Judgement | In this repo |
|---|---|---|
| **Desktop** (compositor, bar, launcher, notifications, lock, idle, OSD, screenshots, GTK, keybinding help) | **Adopt Omarchy's wholesale.** Override only where you hold knowledge it lacks. | Retire `sway`, `waybar`, `mako`, `fuzzel`, `nwg-drawer`, `kanshi`, `gtk`, `kitty` (+ `htop`): 45 of the ~72 files in non-systemd stow packages |
| **Look** (colours, fonts, wallpapers) | **Adopt Omarchy's native themes** (decided, D4) — the whole-desktop theme switch is Omarchy's core feature. Your palettes and contrast floor retire | `palettes.toml`, `bin/theme`, `walls-sync` retire; `themed/*.tpl` only for apps Omarchy doesn't theme (yazi, tmux colours, maybe nvim) |
| **Terminal & dev** (bash, nvim, vim, tmux, yazi, starship, herdr, Claude statusline, `bin/`) | **Port**, as override files, handling five collisions with Omarchy's seeded configs. | Keep, re-plumbed |
| **Server** (Jellyfin, family site, Tailscale, restic timers, sleep policy) | **Carry over deliberately as system config**, with the six fixes above, gated on a Jellyfin version check. | Grow `systemd-system/` |

**Go/no-go gates** (all must pass before the disk is wiped — or, on a new PC, before the server
role moves): (G1) the Omarchy stable mirror carries
`jellyfin-server` ≥ 12.1, or you accept the edge channel; (G2) a trial install has proved the
override set, the NVIDIA decision and the server fixes; (G3) every item in the data inventory
(§9.3) is backed up *and a restore has been tested*.

### Decisions taken (Xinye, 2026-09-25)

These supersede the leans wherever the body below still discusses the alternatives; §9.2 records
them as decided.

| # | Decision | Consequence for the plan |
|---|---|---|
| D1 | **Migrate — but not yet.** G1 (Jellyfin on the stable mirror) forces a wait, and a **new mini PC may arrive first** | The plan now has two targets: this laptop (wipe-and-reinstall, as written) or a new PC (§9.10: side-by-side, no wipe). Hardware facts in §4 apply only to the laptop |
| D2 | **No disk encryption** | Unattended reboots come back on their own; SDDM's greeter is the login boundary; linger (S3) becomes a must. Theft would expose SSH keys and backup credentials — accepted |
| D3 | **NVIDIA is not a requirement.** Omarchy runs its NVIDIA installer only when `lspci` shows an NVIDIA card [26]; the manual sets no GPU requirement | On this laptop, remove the legacy driver (§9.6 step 10). For a mini PC, integrated Intel/AMD graphics avoids the whole NVIDIA branch |
| D4 | **Omarchy's native themes** | `palettes.toml`, `bin/theme`, `walls-sync` and the contrast floor retire (§3.2) |
| D5 | **Omarchy's keybindings for two weeks**, then override only what you still reach for | Unchanged |
| D6 | **Ghostty**, because foot can't render ligatures [68] | §3.1, §3.3 |
| D9 | **Chrome**, because Chromium lost Google sync in 2021 [72]; Omarchy installs, defaults and themes Chrome natively [71] | §3.3 |
| — | **Hostname changes; name decided later** (the current name encodes hardware + OS, and both will change) | Decouple the family-facing tailnet name from the OS hostname (§5.3) |
| — | **Backups of trading-platform data are owned elsewhere** — another session is moving EODHD data to backup; Sharadar clean-up follows | R1 excludes that data; this plan waits for those sessions rather than duplicating them |
| — | Done now, independent of migration: the sleep-on-AC inhibitor is tracked in `systemd-system/` (it lived only in `/etc`); leaving the `docker` group is handed to you (needs sudo) | §2.3 |

---

## 1. What Omarchy 4 is

### 1.1 Architecture

| Concern | Omarchy 4 | Source |
|---|---|---|
| Base | Arch Linux; Omarchy's own pacman repo `[omarchy]` at `pkgs.omarchy.org`; stable channel uses a **one-month-delayed** Arch mirror | [8][58] |
| Compositor | Hyprland, configured in **Lua** since Hyprland 0.55 deprecated hyprlang | [4][5] |
| Desktop shell | Quickshell, one process (launched by `omarchy-launch-shell`, driven by the `omarchy-shell` IPC CLI): bar, menu, notifications, OSD, clipboard history, idle, lock, polkit — each a plugin under `shell/plugins/` | [1][61] |
| Login | SDDM; **autologin when encrypted** ("the LUKS prompt is the auth boundary"), SDDM greeter when not | [6] |
| Disk | GPT, `OMARCHY_EFI` FAT32 + `OMARCHY_ROOT`; LUKS2 by default (Ctrl+C at the confirm screen opts out); btrfs subvolumes `@ @home @log @pkg`, `compress=zstd`; Limine; swap | [6][36] |
| Snapshots | snapper, **root only**, 5 kept, pre-update, no timeline; restore via Limine "restores root, not `/home`"; the ISO also keeps a read-only `@factory` snapshot of `@` | [10][6] |
| Default terminal | **foot** (since May 2026; was Alacritty) | [1][51] |
| Default browser / files / editor | Chromium (Omarchy build, themed) / Nautilus / nvim with a pre-built LazyVim (`omarchy-nvim`) | [1][58] |
| Multiplexers | tmux (prefix Ctrl+Space) **and herdr** (0.8.2), both in the base package list, both with seeded configs | [54][58] |
| Firewall | ufw + ufw-docker, default deny incoming, only LocalSend (53317) open | [37] |
| Docker | installed, `docker.socket` enabled, user **not** in the `docker` group (it is root-equivalent) | [39] |
| Agents | Claude Code, Codex, OpenCode et al. launched from Super+Shift+Ctrl+A in low-/no-prompt modes (Claude: `--permission-mode auto` since PR #7001; grok still `bypassPermissions`); two skills (`omarchy`, `diagnose-crash`) symlinked into `~/.claude/skills` | [24][60] |

The base package list is 155 packages [54]. Of your tools it includes `herdr`, `tmux`, `starship`,
`foot`, `mise-bin`, `fzf`, `ripgrep`, `btop`, `docker`, `ufw` and `omarchy-nvim`; it does **not**
include `kitty` (though a `config/kitty/kitty.conf` ships), `yazi`, `kanshi`, `vim`, `tailscale`,
`jellyfin-*` or `google-chrome` [54].

### 1.2 Who owns which file

Omarchy's own `docs/file-layout.md` [2] is explicit, and it is the single most important fact for
this repo:

| Path | Owner | Behaviour |
|---|---|---|
| `/usr/share/omarchy/**` | Omarchy (package) | Replaced on every update. Never edit. |
| `/etc/skel/**` | Omarchy | Copied into `$HOME` (`~/.config`, `~/.bashrc`, `~/.local/share/applications`, …) **once, at user creation** ("`/etc/skel` only fires at user creation") |
| `~/.config/**` | **You** | Omarchy's updates don't bulk-overwrite it — but *migrations* may make targeted edits (§1.4) |
| `~/.config/omarchy/` | You | "for files a user may intentionally version in a dotfile manager": themes, `themed/*.tpl`, hooks, `shell.json`, extensions, plugins |
| `~/.local/state/omarchy/current/` | Omarchy (generated) | The rendered theme; apps `include` from here |

The Hyprland entry point makes the layering concrete [4]:

```lua
dofile((os.getenv("OMARCHY_PATH") or "/usr/share/omarchy") .. "/default/hypr/bootstrap.lua")
require("default.hypr.omarchy")      -- Omarchy's defaults
require("hypr.monitors")             -- yours, loaded after
require("hypr.input")
require("hypr.bindings")
require("hypr.looknfeel")
require("hypr.autostart")
require("default.hypr.toggles")      -- Omarchy again: dynamic toggles load after yours
```

So "yours load last" is true of everything except `default.hypr.toggles` — an override of a
toggle-controlled setting needs to go through the toggle, not around it.

`~/.bashrc` follows the same pattern: Omarchy's seeded file sources
`/usr/share/omarchy/default/bash/env-bootstrap` (PATH, needed even non-interactively) and then
`$OMARCHY_PATH/default/bash/rc` (aliases, functions, tool init) [53]. **Your stowed `.bashrc`
replaces that file, so it must carry those two lines** or you silently lose Omarchy's PATH and
shell integration.

### 1.3 Updates

- `omarchy update` runs: cache prune → snapper snapshot → packages → `omarchy-migrate` →
  `omarchy-hook post-update` → shell restart [8]. Nothing runs on a timer; a kernel update ends in
  a `Reboot?` confirm, never an automatic reboot [63].
- A libalpm hook aborts any pacman call that combines sync with sysupgrade — `-Syu`, `-Su`,
  `-Syyu`, `-Syu <pkg>` ("Woah partner…"); `pacman -S <pkg>` and the AUR still work (on stable,
  `-S` installs the delayed mirror's version); the bypass is
  `sudo env OMARCHY_ALLOW_DIRECT_PACMAN=1 pacman -Syu` [9].
- Four channels: stable (month-delayed mirror), RC, edge, dev [8]. One report says 4.0.1 moved
  stable users to edge without asking (closed) [56].
- Updates can remove packages without asking (`pacman -Rns --noconfirm`), but so far only
  Omarchy's own picks — none of your server packages [63].
- **Rollback is reported broken**: "btrfs-overlayfs is enabled by default, which makes snapshot
  rollback impossible: limine-snapper-sync refuses to start inside every snapshot boot" (#8047,
  open since 2026-08-24; one reporter, verified on 4.0.0 without LUKS, no maintainer reply) [11].
  Booting *into* a snapshot still works; the *restore* chain is what fails. `btrfs-overlayfs` is
  in the initramfs hook list at v4.0.4 [source]. Treat rollback as unproven until the trial
  tests it.

### 1.4 Migrations: the one place Omarchy edits your files

Migrations are timestamped scripts in `migrations/`, run by `omarchy-migrate`, tracked per-user in
`~/.local/state/omarchy/migrations/`. The rule is that a migration "may touch user/session state
(`~/.config`…)" [17]. In practice v4's migrations are guarded: herdr's only seeds a config if none
exists; kitty's replaces the file only if its sha256 equals the stock one; Hyprland edits are
exact-pattern [17]. **A fresh ISO install marks every migration shipped in the installed
`omarchy` package complete** for the user it creates (`omarchy-provision-user --first-install`)
[60], so only *later* migrations can touch you. Some migrations also keep system-wide markers in
`/var/lib/omarchy/migrations`.

Two properties matter for Stow:

- `omarchy-refresh-config` does `cp -f default user`, backing up to `user.bak.<epoch>` — and `cp`
  **writes through a symlink into its target**, i.e. into this repo (tested three times
  independently in Phase 5) [17]. The `.bak` is a regular file placed next to the symlink, so it
  lands in `~/.config` for an unfolded package but **inside the repo** for a folded one. gigacrat's
  Omarchy dotfiles pin `--no-folding` for exactly this reason [18].
- One migration used `sed --follow-symlinks -i` on `kitty.conf` [17] — Omarchy *expects* configs
  to be symlinks, and edits their targets.

History is worse than the v4 design: v3 updates deleted a user's `source =` override line and
rewrote custom bindings (the reporter was unsure of the exact version; #1802 is closed) [46]; the
3→4 in-place upgrade silently stopped loading old `bindings.conf` — and, per commenters,
`envs.conf`, `looknfeel.conf` and window rules — with no `hyprctl configerrors` output (#6933,
open) [47], and lost saved Wi-Fi networks [45]. **You are doing a fresh install, which skips `omarchy-upgrade-to-quattro` entirely**
— but the pattern ("an override that silently stops loading") is the failure to design against.

### 1.5 Themes

Exactly 22 themes ship, including `nord` and `gruvbox` [59]. Each is a directory: `colors.toml` (~24
semantic keys: `accent`, `selection`, `muted`, `background`/`dark_`/`darker_`/`lighter_background`,
`foreground`/`dark_`/`light_`/`bright_foreground`, plus 14 ANSI colours), `neovim.lua`,
`vscode.json`, `icons.theme`, backgrounds, an unlock image [12][13]. `omarchy-theme-set` renders
`*.tpl` files (`{{ background }}`, with `_strip`/`_rgb`/`mix` variants) into
`~/.local/state/omarchy/current/theme/`. Precedence: a file the theme itself ships beats
**your `~/.config/omarchy/themed/*.tpl`**, which beat Omarchy's built-in templates [12]. It then
live-updates, in parallel, foot (OSC escapes to each foot child's pty), tmux (environment),
GNOME/GTK (`gtk-theme "Adwaita-dark"`), the browser, and writes `~/.claude/themes/omarchy.json`
(Claude Code hot-reloads it; `settings.json` is only touched with `--activate`) [14][60]. After
those it runs `omarchy-hook theme-set <name>` — your `~/.config/omarchy/hooks/theme-set` and
`theme-set.d/*` — followed by switcher preload and background caching; none of this runs in
headless mode [12][14].

Two gaps against your model: the renderer is plain `sed` built from the keys that exist, so **a
placeholder the theme doesn't define is left in the output as literal text, and the renderer
raises no error** (`omarchy-theme-color` does fill some legacy alias keys, and a couple of
downstream consumers grep for leftover `{{`) — your §9.10 "undefined colour renders black" failure
in a new form; and **nothing measures contrast** [12].

Omarchy's `nord` and `gruvbox` are not your palettes. Its Nord accent is `#81a1c1` (yours
`#88c0d0`); its Gruvbox `colors.toml` uses *Gruvbox Material* foreground and accents on the
classic `#282828` background — foreground `#d4be98`, accent `#7daea3`, red `#ea6962` — where yours
is morhetz: `#ebdbb2`, `#fabd2f`, `#fb4934`. (The same theme's `neovim.lua` and `vscode.json` load
the *original* Gruvbox, so the theme isn't even internally one variant.) [13]

### 1.6 Extension points

Hooks (`~/.config/omarchy/hooks/{post-boot,post-update,pre-refresh-pacman,theme-set,font-set,battery-low}.d/`),
menu extensions (`extensions/omarchy-menu.jsonc`), and **shell plugins** (git repos with a
`manifest.json`, `omarchy plugin add <url>`, "arbitrary, unsandboxed code") [3]. `omarchy plugin
validate` **rejects symlinks anywhere in a plugin folder outside `.git/`** [20] — so a plugin
cannot be a Stow package; it must be a real directory (clone or copy).

---

## 2. This machine, as three layers

### 2.1 Hardware

Dell XPS 15 9570 (2018): i7 CoffeeLake-H, Intel UHD 630 + **NVIDIA GTX 1050 Ti Mobile (Pascal,
`10de:1c8c`)**, 30 GiB RAM, 3840×2160 panel at scale 2, Intel 9260 Wi-Fi, 1 TB NVMe. Today: no
NVIDIA driver; the dGPU sits on nouveau with `runtime_status=suspended`.

### 2.2 Layers

| Layer | Today | Size in repo |
|---|---|---|
| Desktop | sway (SwayCE base) + waybar (supervised) + mako + fuzzel + nwg-drawer + swaylock/swayidle + kanshi + GTK (Nordic/Colloid) + greetd | `sway` 20 files, `waybar` 8, `gtk` 7, `mako`/`fuzzel`/`nwg-drawer`/`kanshi` 7 |
| Look | `palettes.toml` (2 palettes × ~16 roles + 16-colour ramp) → `bin/theme` → 19 rendered files; contrast floors; `walls-sync` lock wallpapers | `palettes.toml`, `bin/theme`, `*.tmpl` |
| Terminal & dev | kitty (default) / foot, bash, starship, tmux, herdr (0.8.0, hand-installed in `~/.local/bin`), nvim (vim.pack, lockfile), vim, yazi, htop, Claude statusline, mise | `bash`, `nvim`, `vim`, `tmux`, `herdr`, `yazi`, `starship`, `htop`, `claude`, `kitty`, `foot` |
| Server | Jellyfin 12.1 (native), family-site (user unit, `python -m http.server` on :8321), `tailscale serve` exposing both tailnet-only, restic `tp-backup` regime (7 user timers → Hetzner), `herdr-session-backup`, `inhibit-sleep-on-ac` (system unit + udev rule), firewalld, linger on | `systemd` 19 files, `systemd-system` 6 |

Tests: `theme_test.sh`, `check_consumers.sh`, `waybar_run_test.sh`, `herdr_test.py`,
`tp_backup_test.sh`.

### 2.3 Facts from the live machine that the plan must respect

- **Two tailnet URLs are bound to this node's identity**: `https://xps-eos.tail7ff5d7.ts.net` →
  :8321 (family site) and `:8443` → :8096 (Jellyfin). A reinstall that re-registers Tailscale makes
  a *new* node; the name `xps-eos` is only kept if the old node is removed first or its state file
  is restored.
- **Untracked system and user config that a wipe loses silently** (the first two are **now
  tracked** in `systemd-system/`, done 2026-09-25):
  `/etc/systemd/system/inhibit-sleep-on-ac.service` and `/etc/udev/rules.d/99-inhibit-sleep-on-ac.rules`
  (neither is in this repo), and user units `family-site.service`, `signal-daily.*`,
  `tp2-judge-nightly.*`, `tp2-resync-check.*` (documented in the `household` and
  `trading-platform-v2` repos, not here).
- **Four repos have unpushed commits** (`familiy-site` 3, `trading-platform-android` 5,
  `trading-platform-v2` 1, `xl-skills` 1). `tp2-signal-home` (113 GB) and `trading-platform-v2`
  (74 GB) are mostly untracked data.
- **You are in the `docker` group today** — root-equivalent for any process in your session. Omarchy
  itself made the same choice by default (2025-06-01, briefly reverted, re-enabled 2025-06-17) until
  PR #8056 removed it on 2026-08-24, shipped in 4.0.1 with a migration that also removes existing
  users from the group; the write-up behind that is [48]. This is true of your machine with or
  without a migration. Checked 2026-09-25: nothing here depends on it (no containers; no timer
  calls Docker; the trading platform's `docker compose` calls run on its VPS over SSH), so leaving
  the group is safe — `sudo gpasswd -d xinye docker`, effective at next login; afterwards local
  Docker needs `sudo`.
- `/mnt/ext` (932 GB exFAT, 87% full) holds media and is **not** on the NVMe — the wipe does not
  touch it.

---

## 3. Port or keep, layer by layer

The user's hypothesis was that Omarchy's defaults are designed with care. The evidence mostly
supports it, with one important refinement: **the care is in coherence** — one theme reaching
every surface, one shell process, bindings that document themselves, 255 shell tests in the repo
[67] — **not in the edge cases your PLAYBOOK §9 is made of**. So the rule this report
applies everywhere is:

> **Adopt the default unless you hold a specific, written-down piece of knowledge the default
> lacks. Then override *that piece*, in the smallest file Omarchy's layering allows, and put a test
> on it.**

### 3.1 Desktop layer — adopt

| Your component | Omarchy 4 equivalent | Judgement |
|---|---|---|
| sway + `config.d/*` | Hyprland Lua, layered | Adopt. Port **intent**, not syntax: workspace pinning, app placement, gaps toggle, resize mode → a few lines in `hypr/*.lua` if you still want them after the trial |
| waybar + `waybar_run.sh` supervisor | Shell top bar, relaunched by `omarchy-launch-shell` after a non-zero exit while Hyprland is alive (gives up after 5 relaunches in a fixed 60 s window; signals forwarded by `trap`, no `pdeathsig`) | Adopt. Keep your §9.29 *knowledge* as a check, not a supervisor (§3.5) |
| mako + DND/restore/dismiss bindings | Shell notifications | Adopt |
| fuzzel + nwg-drawer | Shell launcher + Omarchy menu | Adopt |
| swaylock + `lock.sh` + walls | Shell lock plugin over the blurred current theme background (a local symlink — no network) | Adopt. Your "lock never touches the network" rule is **already true** of Omarchy's lock |
| swayidle + `idle.sh` (AC/battery) | `shell.json` `idle: {screensaver:150, lock:300}`; Super+Ctrl+I stay-awake; **no suspend step, no AC/battery split** | Adopt for the *screen*; the *sleep* policy is server config (§5.3) |
| kanshi | `hypr/monitors.lua` `hl.monitor(...)`; scale `auto` → 2× on this panel | Adopt; add a docked profile only when you dock |
| GTK (Nordic/Colloid, `import-gsettings`, nwg-look defence) | `omarchy-theme-set-gnome` sets Adwaita-dark on every switch | Adopt. This deletes §2.2, §9.1, §9.9, §9.10, §9.27 as live concerns |
| keyhint.sh (hardcoded yad array) | Super+K, built from `hyprctl binds` + a source-derived cache (Lua binds show as `__lua`) | **Adopt — Omarchy's is strictly better** |
| `$mod+grave` dropdown | v4.0.4: scratchpad on Super+S. Dev branch only: Super+grave "Quake console" (PR #7420) | Adopt the scratchpad; one `o.bind` gives you Super+grave until the Quake console ships |
| kitty as default terminal | foot is the default, but **foot will never render ligatures** — "Ligatures is not possible in foot without a large rewrite of the rendering logic" (closed wontfix, 2025-07-28) [68]. Omarchy fully supports Alacritty, Ghostty and Kitty as alternatives (*Install > Terminal*) [69]; Alacritty has no ligatures either | **Decided (D6): Ghostty.** It renders the font's ligatures (they're a font feature; `font-feature = -calt` is how you'd turn them *off*) [70]; Omarchy ships a Ghostty config that includes the generated theme and reloads running Ghostty windows with `SIGUSR2` on every theme switch [69]. Retire the `kitty` and `foot` packages |
| screenshots (grim/slurp/swappy scripts) | Shell screenshot + Tensaku annotation | Adopt |
| greetd + agreety | SDDM (autologin if encrypted, greeter if not) | Adopt. Unencrypted (D2), so SDDM's login screen is the auth boundary |

### 3.2 Look — Omarchy's native themes (D4, decided)

**Decided 2026-09-25: use Omarchy's own themes.** They are the point of the Quickshell design: one
switch re-colours the shell, lock screen, OSD, terminal, browser, btop, nvim and Claude Code
together, across all 22 themes, each with its own backgrounds [59][12]. `palettes.toml`,
`bin/theme`, the two-palette constraint and `walls-sync`'s palette-matched lock wallpapers all
retire; Omarchy's Nord and Gruvbox (with their different values, §1.5) replace yours.

What this knowingly gives up, stated once: **the contrast floor.** Omarchy has no contrast rule;
its Nord `dark_foreground` is ≈2.5:1 and its Gruvbox ≈3.0:1 on their backgrounds (WCAG, computed
from [13]) — below the 4.5:1 your `dim` role guarantees. If quiet text ever becomes hard to read,
the fix is a user theme override, not a return to `palettes.toml`.

What survives is only the part Omarchy leaves to you — apps it doesn't theme:

| Your file | Becomes | Guard |
|---|---|---|
| `yazi/…/theme.toml.tmpl` | `~/.config/omarchy/themed/yazi-theme.toml.tpl`, written against Omarchy's keys (`background`, `foreground`, `accent`, `selection`, `muted`, `red`, …) | **Test**: every `{{key}}` used in your `themed/*.tpl` is defined in **every installed theme's** `colors.toml` — the renderer leaves an undefined one as literal text, silently (§1.5), and with 22 themes a key that exists in one may be missing in another |
| tmux colours (`colors.gen.conf.tmpl`) | Same: a `.tpl` against Omarchy's keys (Omarchy's `theme-set-tmux` only pushes env vars) | Same test |
| nvim colourscheme (`colorscheme.gen.lua.tmpl`) | Either load the theme's own `neovim.lua` from `~/.local/state/omarchy/current/theme/`, or keep a `.tpl` — decide when porting nvim | Same test |

### 3.3 Terminal & dev layer — port, as overrides

| Package | Collision with Omarchy | Judgement |
|---|---|---|
| `bash` | Omarchy seeds `~/.bashrc` that sources `env-bootstrap` + `default/bash/rc` [53] | Port; **add those two source lines** at the top of yours; drop anything Omarchy's rc now does (starship/zoxide/mise init — diff them) |
| `nvim` | `omarchy-nvim` ("Pre-built LazyVim configuration with cached plugins") [58]; theme renders `neovim.lua` | Port yours (it's your editor, lockfile-pinned). **Stow it before nvim's first launch** and check how `omarchy-nvim` deploys (UNRESOLVED). Colourscheme template → `themed/*.tpl` |
| `vim` | none (vim not in base) | Port; install `vim` |
| `tmux` | Omarchy seeds `~/.config/tmux/tmux.conf` (prefix Ctrl+Space); theme-set pushes env into tmux | Port yours (206 lines, carries §9.18–9.20 fixes) *or* adopt Omarchy's — **D7**. Colours → `themed/*.tpl` |
| `herdr` | Base package **0.8.2** at `/usr/bin/herdr`; seeded config only if none exists; Omarchy's config has `name = "terminal"` like yours. Migration `1786273938.sh` runs an **unconditional** `rm -f ~/.local/bin/herdr` — any copy, whoever installed it (moot on a fresh install, where it's pre-marked done) | Port config + attention plugin; **don't restore the hand-installed `~/.local/bin/herdr` 0.8.0** — it would shadow the package; re-run `herdr_test.py` and the `--default-config` key check against 0.8.2 |
| `yazi` | none | Port; install `yazi`; `theme.toml.tmpl` → `themed/*.tpl` |
| `starship` | Omarchy seeds `~/.config/starship.toml` | D7-adjacent: port yours or adopt theirs; small either way |
| `claude` (statusline) | Omarchy writes `~/.claude/themes/omarchy.json` on theme switch; symlinks two skills into `~/.claude/skills` | Port; no conflict with the statusline. See §3.5 on the skills |
| `bin/` | none | Port `tp-backup`, `tp-backup-ssd`, `herdr-session-backup`; **retire `theme` and `walls-sync`** (D4) |
| `htop` | Omarchy ships btop | Retire (it was already a drop candidate) |
| `foot` | Omarchy's default terminal, but no ligatures [68] | Retire the package; D6 picks Ghostty |
| `kitty` | kitty not installed | Retire |
| *(new)* Ghostty | Omarchy ships `config/ghostty/config` (includes the generated theme; JetBrainsMono Nerd Font) [69] | Adopt Omarchy's config; add an override only if a font-size or ligature tweak turns out to be needed |
| Chrome | First-class in Omarchy: *Install > Browser > Chrome* (from the AUR), selectable as default, and themed by `omarchy-theme-set-browser` [71] | **Decided (D9): keep Chrome.** Chromium builds lost Google's Chrome Sync API on 2021-03-15, so Chromium can't give you the Google integration [72] |

### 3.4 Keybindings (D5)

Omarchy's scheme is built for people coming from macOS/Windows: "All the muscle memory you've
built around Cmd … transfers to one key: Super"; Super+C/X/V copy/cut/paste everywhere including the
terminal [66]. Super+Return is still the terminal. The friction for you is vim keys:
focus moves with **Super+Arrows**, and **Super+J / K / L are taken** (toggle split, keybinding help,
workspace layout) [22]. A long-running discussion asks for hjkl [22].

Mechanics if you override: `o.rebind(...)`, `hl.unbind(...)`, or `omarchy_default_bindings = false`
to drop all defaults [4]. Rebinding hjkl means relocating three defaults, one of which is the help
screen.

### 3.5 Knowledge Omarchy lacks — the keepers

| Keeper | Why Omarchy doesn't cover it | Form on Omarchy |
|---|---|---|
| ~~Contrast floor~~ (§3.1, §9.28) | No contrast rule; measured defaults fail 4.5:1 | **Given up by D4** (native themes). Recorded so a later legibility complaint has its explanation |
| **Templates work under every theme** | Undefined `{{key}}` renders as literal text, silently | A test: every key your `themed/*.tpl` uses exists in all installed themes |
| **Never sleep on AC** (inhibit unit, §9.26) | Lid suspends on AC by default; idle never suspends | System config: logind drop-in + your inhibit unit + udev rule, deployed by `systemd-system/deploy.sh` (§5.3) |
| **herdr blocked-agent alert** (§9.30) | herdr ships with no attention widget | Your `herdr` local plugin keeps the notify half. The bar half needs a Quickshell plugin — **defer**: judge after two weeks whether notifications alone suffice |
| **Supervisor orphan check** (§9.29) | Omarchy restarts the shell but gives up after 5/min, and has no `pdeathsig` | A 10-line check in `check_consumers.sh`: exactly one `omarchy-shell`, its parent is the supervisor. Don't re-implement the supervisor |
| **"An override that silently stops loading"** (#6933) | Hyprland reported no config error when v4 stopped loading old files | A test: every binding in *your* `bindings.lua` appears in `hyprctl binds -j` |
| **Repo drift after updates** | Migrations/refresh write through symlinks | A `post-update.d` hook that runs `git -C ~/repos/dotfiles status --porcelain` and notifies if dirty, and flags any `*.bak.*` in stowed paths (kogakure does this [19]) |
| **Agent posture** | Omarchy launches agents with prompts reduced or bypassed [24]; ships an `omarchy` skill into `~/.claude/skills` that triggers on any `~/.config/hypr` / `~/.config/omarchy` edit | Keep launching agents through herdr with your own permission settings; add a CLAUDE.md rule that forbids `omarchy-refresh-config` / `omarchy reinstall configs` on stowed paths |

---

## 4. Hardware on the XPS 15 9570

*Applies only if the target stays this laptop (D1). On a new mini PC, integrated Intel/AMD
graphics avoids every NVIDIA item below — Omarchy's installer acts only when `lspci` shows an
NVIDIA card [26].*

- **NVIDIA.** Omarchy's installer auto-selects `nvidia-580xx-dkms` + utils for GPUs without GSP
  (device IDs `0x1340`–`0x1dff`; yours is `0x1c8c`), from its own repo, with no opt-out; it writes
  `/etc/modprobe.d/nvidia.conf` (`nvidia_drm modeset=1`) and `/etc/mkinitcpio.conf.d/nvidia.conf`
  (early-loads the four nvidia modules) [26][58]. The device-ID test lives in
  `bin/omarchy-hw-nvidia-without-gsp`; `install/hardware/all.sh` runs the script unconditionally.
  Arch dropped Pascal from the main driver in 590 [27]. An older bug that picked the wrong driver
  for Pascal (#3954) [50] is superseded by this code.
- **Hybrid-graphics risks under the proprietary driver**: v4.0.4 forces
  `__GLX_VENDOR_LIBRARY_NAME=nvidia` even on hybrids — which the fix's own code comment says
  "globally breaks Chromium-based browsers (black video)". The fix (6ecf4bf2, 2026-09-13) is on the
  dev branch only and in **no released tag** [28]; an open
  report of i915 GPU hangs in Hyprland when externals are wired to the NVIDIA side (#10350) [29];
  Omarchy omits the `i915`-first module ordering Hyprland's wiki recommends against a
  minute-long Chromium stall on Intel+NVIDIA hybrids [32].
- **Power**: NVIDIA's runtime D3 power management "requires a Turing or newer GPU" [30]; the Arch
  wiki reports that turning this card off (keeping it only for PRIME offload) takes the 9570 "from
  around 13W to 6/7W" [31]. Today, nouveau keeps
  it suspended. *Inference, not measured:* on an always-on server, the 580xx driver likely costs
  several watts continuously.
- **HiDPI**: Omarchy assumes a retina-class panel; `monitors.lua` defaults to scale `auto` with
  `GDK_SCALE=2`; this panel (~282 PPI) needs no work [33].
- **Lid & sleep**: Omarchy's only logind drop-ins are `HandlePowerKey=ignore` and
  `InhibitDelayMaxSec=15` [35]; `HandleLidSwitchExternalPower=` "is completely ignored by default"
  [34], so undocked with only the internal panel, **the lid suspends on AC** (docked or with an
  external display, `HandleLidSwitchDocked=ignore` applies). Hyprland's lid binding only runs
  `omarchy-system-lid-close`, which locks and reconciles monitors; nothing takes a lid inhibitor. Suspend/hibernate are enabled by default; hibernation needs a
  RAM-sized swap subvolume (~32 GB) [16].
- **Install path**: the ISO is the only supported v4 path — no `install.sh` onto an existing Arch
  (Discussion #2209) [57].

---

## 5. The server role under Omarchy

### 5.1 Encryption vs coming back after a reboot (D2)

Encrypted installs autologin after the LUKS prompt; unencrypted ones stop at SDDM [6]. There is
**no TPM auto-unlock** in v4.0.4: nothing in `bin/` or `install/` of either repo calls
`systemd-cryptenroll` or touches a TPM, the manual tells you to "turn off Secure Boot and/or TPM"
[36], and the initramfs uses the busybox `encrypt` hook, whereas TPM2 unlock via
`systemd-cryptenroll` needs `systemd` + `sd-encrypt` [41]. (An unshipped Secure Boot plan also
scopes it out: "No TPM auto-unlock for Omarchy root in v1" — v1 of *that plan* [40].) So:

| Option | After a power cut or crash | If the laptop is stolen | Fights Omarchy? |
|---|---|---|---|
| **A. LUKS (Omarchy default), type the passphrase** | Waits at the passphrase prompt until you're home | Data safe | No |
| B. No encryption + linger (today's posture) | Comes back unattended; user units run via linger; desktop at SDDM | Repos, SSH keys, restic and ntfy credentials, market data exposed | No |
| C. LUKS + DIY TPM2 unlock | Comes back unattended | Safe against casual theft | **Yes** — swapping `encrypt` for `sd-encrypt` in a file Omarchy owns and regenerates |

My lean was **A** (a laptop is its own UPS). **Decided: B — no encryption.** At the ISO's disk
confirmation screen, press `Ctrl + C` to switch to an encryption-less install [36]. The machine then
boots unattended to SDDM's greeter; nothing runs as you until linger (S3) is on, so S3 is a
**must**. Accepted cost: a stolen disk exposes `~/.ssh`, the restic/rclone/ntfy credentials and
market data.

### 5.2 Snapshots would roll your data back with the OS

`/var/lib/{jellyfin,docker,postgres}` sit inside `@`, the snapshotted root [10]. Rolling back an
update would roll Jellyfin's database back too — and Jellyfin "does not have a downgrade mechanism"
[44]. The Arch wiki recommends separate subvolumes for such state [42]. Plan: create `@jellyfin`
(and `@docker` if you keep containers) mounted at `/var/lib/jellyfin` / `/var/lib/docker` before
restoring data. **Open:** what `limine-snapper-restore` does with nested/extra subvolumes is
unverified [65] — test in the trial.

### 5.3 The six server fixes (all small)

| # | Default | Fix |
|---|---|---|
| S1 | ufw deny-incoming (host input: only LocalSend 53317 + Docker DNS; ufw-docker lets private ranges reach *published container* ports); Omarchy's Tailscale installer adds **no** `tailscale0` rule (only the Sunshine installer does, for its own ports) [37] | `ufw allow in on tailscale0` [38]. Don't also run firewalld — both filter, so every port would need opening twice [52] |
| S2 | `docker.socket` only; containers created by Omarchy's DB installer with `unless-stopped` don't return after reboot (#8541, open; fix PR #8098 referenced) [39] | `systemctl enable docker.service` — only if you run containers |
| S3 | No linger | `loginctl enable-linger xinye` (family-site, tp-backup timers run without a login) |
| S4 | Lid suspends on AC | Deploy this repo's `inhibit-sleep-on-ac.service` + udev rule (`sudo systemd-system/deploy.sh`) — **tracked since 2026-09-25**, and the deploy asserts logind really holds the lid-switch block. Optionally belt-and-braces: `/etc/systemd/logind.conf.d/50-server.conf` with `HandleLidSwitchExternalPower=ignore` |
| S5 | `NetworkManager-wait-online` masked → `network-online.target` isn't a real gate [64] | Check the tp-backup/family-site units don't rely on it; restic already retries |
| S6 | Stable mirror's `extra` (last modified 2026-09-08) has Jellyfin 10.11.11; Arch has had 12.1 since 2026-09-22 and you run it; "Jellyfin does not have a downgrade mechanism" [43][44] | **Gate G1**: migrate only once `stable-mirror.omarchy.org/extra/os/x86_64/extra.db` carries ≥ 12.1 (or choose the edge channel). Re-check on the day |

Plus identity. **The OS hostname will change (decided; new name later)**, because `xps-eos` names
hardware and an OS that are both going away. The family's two links hang off the *tailnet* name,
and Tailscale lets that differ from the OS hostname: `tailscale set --hostname=<name>` — "hostname
to use instead of the one provided by the OS" [73]. So pick the tailnet name for the *service*, not
the machine (it outlives this laptop, and it moves with the server role to a mini PC), move the
family's bookmarks once, and never again. Restoring `/var/lib/tailscale/tailscaled.state` keeps
the node's identity and its `tailscale serve` config; re-registering creates a new node. Either
way, re-check `tailscale serve status` afterwards.

### 5.4 Backups

Omarchy has no backup story of its own ("Omarchy has no answer for 'my disk died'", an unshipped
plan) [65]. Your restic regime continues unchanged; add `/var/lib/jellyfin` to it (with
Jellyfin stopped, as its docs require [44]) if it isn't already covered.

---

## 6. Keeping this repo sane on Omarchy

1. **Stow override files, never whole directories Omarchy writes into.** Use `--no-folding` for
   `hypr`, `omarchy`, `tmux`, `foot`, `starship`, `herdr` — a `.bak.*` or migration-added file
   must land in `~/.config`, not the repo [18]. `nvim` is the one folded exception you already
   accept (its lockfile), and it gets the drift hook.
2. **`/etc/skel` has already populated `~/.config` by first login.** `stow -n` will refuse every
   collision. Per package: diff Omarchy's seeded file against yours, fold anything of Omarchy's
   worth keeping into yours, delete the seeded file, then stow (PLAYBOOK §5.3's adopt procedure).
3. **Plugins are not packages.** `omarchy plugin validate` rejects symlinks [20]; a Quickshell
   plugin lives in its own repo and is installed with `omarchy plugin add`.
4. **Drift is detected, not prevented**: the `post-update.d` hook (§3.5) plus `git status` after
   any Omarchy menu action that says "refresh" or "reset".
5. **Tests re-scoped**:

| Suite | Fate |
|---|---|
| `theme_test.sh` | Replaced by a small `omarchy_theme_test`: every `{{key}}` in your `themed/*.tpl` is defined in every installed theme (D4 retired parity, no-hex and contrast checks with `palettes.toml`) |
| `check_consumers.sh` | Re-scoped: Hyprland accepts your Lua (`hyprctl configerrors` empty **and** your bindings present in `hyprctl binds`), foot/tmux/nvim/vim/yazi/herdr accept rendered config, one `omarchy-shell` with a live parent |
| `waybar_run_test.sh` | Retired with `waybar_run.sh` |
| `herdr_test.py`, `tp_backup_test.sh` | Kept unchanged |

6. **PLAYBOOK.md** is rewritten as a diff against *Omarchy 4* (as it was against SwayCE). §9 splits:
   still-live gotchas (tmux §9.18–9.20, yazi §9.22, bash §9.15, stow §9.5, herdr §9.30, claude
   §9.23, backups) stay; sway/waybar/mako/GTK/lock gotchas go to `docs/archive/` with the
   `eos-sway-final` tag as their reference.

---

## 7. Tensions and open questions

### 7.1 Contradiction map

| # | Clash | Evidence quality | Resolution |
|---|---|---|---|
| T1 | **"Stow is endorsed"** (manual [3]) vs **"Omarchy writes through symlinks and rejects them in plugins"** [17][20] | Both primary (manual vs source) | Both true. Stow individual override files, unfolded; plugins as real dirs; drift hook |
| T2 | **"v4 layering avoids rewriting your config"** [4] vs **"updates rewrote user configs"** [46][47] | Design = primary source; incidents = v3 issues and the 3→4 upgrade script | Risk is real but concentrated in paths a fresh install skips. Residual risk → drift hook + bindings test |
| T3 | **"Full-disk encryption is mandatory"** [36] vs **a server must come back unattended** | Primary | D2 — **decided: no encryption**; unattended recovery won over theft protection (Omarchy supports this via `Ctrl + C` at the disk confirmation) |
| T4 | **Omarchy auto-installs the proprietary driver** [26] vs **it probably costs idle power and has hybrid bugs** [28][29][30] | Driver choice = source; power = vendor doc + wiki + inference | D3, resolved empirically in the trial (measure both) |
| T5 | **Omarchy's defaults are tasteful** (reviews, [55]) vs **measured contrast fails your floor** (computed from [13]) | Reviews are soft; the ratio is arithmetic | D4 — **decided: taste wins**; the floor is knowingly given up |
| T6 | **Delayed stable is safer** vs **it's older than what you run** [43] | Primary (mirror db, dated 2026-09-25) | G1 gate — a date problem, not a design one |

**Universal agreement** (all six perspectives, independently): Omarchy 4's desktop layer replaces,
rather than hosts, the one this repo customises.

**Resolving question**: *does a trial install on this hardware, with the proposed override set, pass
the verification in §9.7?* Every remaining contested item (rollback, NVIDIA power, nvim deploy,
subvolume restore) is answered by it.

### 7.2 Open questions

1. Is snapshot rollback (#8047) fixed in a released 4.0.x? Test it in the trial before relying on it.
2. What does `limine-snapper-restore` do with extra subvolumes (`@jellyfin`)?
3. How does `omarchy-nvim` deploy LazyVim — `/etc/skel`, or on first launch? Does stowing your
   `~/.config/nvim` first fully pre-empt it?
4. Does removing the 580xx packages stick across `omarchy update`? (No migration found that
   re-adds them; unverified.)
5. Which of the 9570's external ports are wired to the dGPU? (Only matters for #10350 if you dock.)
6. ~~Semantics of `light_foreground` / `dark_foreground` for mapping `dim` and `desktop`~~ — moot
   after D4 (native themes; nothing of yours is mapped onto Omarchy's keys).
7. Is `shell.toml` (a "machine-level override merged over the active theme") the right home for
   anything of yours, versus `shell.json` (which is "canonical… no deep merge" once customised)?

---

## 8. Claim-safety guide and frontier question

| Assert | Caveat | Avoid |
|---|---|---|
| v4 replaced waybar/mako/hypridle/hyprlock/walker/swaybg with one Quickshell shell | Migration safety: v4's design is careful, v3's record isn't — say "fresh install skips the known-bad path" | "Omarchy will never touch your ~/.config" |
| `~/.config` is user-owned; defaults live in `/usr/share/omarchy`; Hyprland is Lua and layered | Rollback works — only after the trial proves it (#8047) | "Omarchy's Nord/Gruvbox are your Nord/Gruvbox" — they're different values (D4 accepts that) |
| Stable mirror is a month behind; bare `pacman -Syu` is blocked | NVIDIA idle power cost — vendor-doc inference, unmeasured on this machine | "The docker-group hole affects you on Omarchy" — Omarchy removed it; *your current machine* has it |
| ufw closes the tailnet without a `tailscale0` rule; lid suspends on AC | Update-breakage *frequency* — only individual incidents are documented | Any claim about Omarchy governance beyond "founder-led, no published board" |

**Frontier question** (the blind spot no perspective covered): *Omarchy 4 is agentic by design — it
installs its own skills into `~/.claude/skills`, launches agents in low-prompt modes, and offers AI
crash diagnosis. You run many Claude Code agents through herdr against real repos, including a
trading platform. Where should the boundary sit between Omarchy's agents (allowed to reconfigure the
desktop) and yours (allowed to touch your code), and should Omarchy's skills be visible to your
dev sessions at all?* Nothing researched here answers it; D8 is the minimum stance.

---

## 9. Implementation Brief

### 9.1 Objective & scope

Replace EndeavourOS/Sway on `xps-eos` with Omarchy 4 on the whole NVMe, preserving: every file
worth keeping, the server's externally visible behaviour (two tailnet URLs, restic timers,
never-sleep-on-AC), and this repo's verifiability. **In scope:** pre-wipe backup, trial, install,
port, server re-home, repo restructure, tests, PLAYBOOK rewrite. **Out of scope:** moving the server
role off this laptop; a Quickshell herdr widget (deferred to post-trial judgement); Windows (being
removed — back up anything wanted from its partitions first).

### 9.2 Key decisions (mini-ADRs)

| ID | Decision | Lean | Rejected | Evidence |
|---|---|---|---|---|
| **D1** ✔ | Migrate at all? | **Decided: yes, gated on G1–G3; target may be a new mini PC (§9.10)** | Stay on sway and borrow ideas (the skeptic's steelman: less risk, but you keep maintaining a desktop Omarchy now maintains for you) | §0, T2 |
| **D2** ✔ | Disk encryption | **Decided: none** (option B) — unattended recovery; linger required | A (waits for a passphrase after any reboot); C (fights an Omarchy-owned initramfs) | §5.1, [6][40][41] |
| **D3** ✔ | NVIDIA driver | **Decided: NVIDIA isn't needed by Omarchy.** On this laptop remove 580xx and stay on nouveau (dGPU runtime-suspended, as today); a mini PC with integrated graphics skips the question | Keep 580xx (idle power, hybrid bugs, Chromium black-video in 4.0.4) | §4, [26][28][29][30] ⚠ power claim is inference |
| **D4** ✔ | Palettes | **Decided: Omarchy's native themes**; retire `palettes.toml`, `bin/theme`, `walls-sync`, contrast floor | Two custom themes with your values (keeps the floor, loses the point of the 22-theme switcher); running `theme` beside Omarchy's switcher (two engines) | §3.2, [12][13] |
| **D5** ✔ | Keybindings | **Omarchy's defaults for two weeks; keep a list of what you reach for; then override only those** | Port the sway map wholesale (Super+J/K/L collide; loses Super+K help) | §3.4, [22] |
| **D6** ✔ | Default terminal | **Decided: Ghostty** — ligatures required; foot can't (wontfix); Omarchy supports and live-themes Ghostty | foot (no ligatures [68]); Alacritty (no ligatures); kitty (declined) | [68][69][70] |
| **D7** | tmux & starship configs | **Port yours** (they carry §9.18–9.20 fixes); revisit tmux's role now herdr is standard | Adopt Omarchy's (loses the escaping fixes) | §3.3 |
| **D8** | Agent boundary | **Launch agents via herdr with your settings; keep Omarchy's skills (they help on desktop tasks) but add a dotfiles CLAUDE.md rule banning `omarchy-refresh-config`/`reinstall configs` on stowed paths** | Remove the skills (they get re-linked by provisioning/migrations) | §3.5, [24] |
| **D9** ✔ | Browser | **Decided: Chrome** — Google integration; Omarchy installs, defaults and themes it | Chromium (no Google sync since 2021-03-15 [72]) | [1][14] |
| **D10** | Repo transition | **Branch `omarchy`; tag `eos-sway-final` on `main` first**; merge after 4 weeks on Omarchy | Rewrite `main` in place (loses the way back) | memory: live config follows checkout |

### 9.3 Requirements

| # | Requirement | Tag |
|---|---|---|
| R1 | Every repo pushed; untracked data triaged (keep / regenerable / drop) and the keepers copied off the NVMe. **Trading-platform data is out of scope** — its EODHD/Sharadar backup and clean-up are owned by other sessions; wait for them | must |
| R2 | Backup includes `~/.ssh`, `~/.gnupg`, `~/.claude`, `~/.config/{tp-backup,rclone,gh,gdrive-backup,jellyfin-roles,mise}`, `~/.local/state/herdr`, untracked user units, `/var/lib/jellyfin`, `/etc/jellyfin` (if present), `/var/lib/tailscale`, `/etc/systemd/system/inhibit-sleep-on-ac.service`, `/etc/udev/rules.d/99-inhibit-sleep-on-ac.rules`, `/var/lib/postgres` and `/var/lib/docker` if non-empty | must |
| R3 | A restore of R2 has been **tested** (list + one file per location), not assumed | must |
| R4 | G1: stable mirror `jellyfin-server` ≥ installed version, checked on the day | must |
| R5 | New OS hostname (TBD); a service-level tailnet name set with `tailscale set --hostname`; both family URLs answer on it after migration | must |
| R6 | Never-sleep-on-AC holds: lid close on AC does not suspend; on battery it does | must |
| R7 | family-site and all tp-backup timers active after an unattended reboot, with no desktop login (linger) | must |
| R8 | `/var/lib/jellyfin` on its own subvolume, outside root snapshots | should |
| R9 | Repo: no stowed dir Omarchy writes into is folded; `git status` clean after `omarchy update` + a theme switch | must |
| R10 | Tests: templates-defined-in-every-theme; bindings-present; shell-supervision; herdr; tp-backup — all green, and each shown able to fail (mutation) | must |
| R11 | ~~Contrast floor~~ — dropped by D4 | — |
| R12 | Way back exists: `eos-sway-final` tag + EOS ISO + backups sufficient to rebuild today's machine | must |
| R13 | `docker` group membership not recreated unless a concrete need is named (leave it on this machine now: `sudo gpasswd -d xinye docker`) | should |

### 9.4 Constraints & assumptions

- Assumes Windows partitions hold nothing needed, **after you check** (they're NTFS; mount and look
  before G3).
- Assumes the trading-platform nightly jobs can be paused for the install window (their timers are
  currently disabled; `inhibit-sleep-on-ac` describes itself as "tp2 nightly protection").
- The backup destination for home is **UNRESOLVED**: ~230 GB today, but most of it is
  trading-platform data whose backup and clean-up other sessions own (R1). Size what remains after
  those finish; `/mnt/ext` has ~126 GB free, the Hetzner box's spare capacity is unknown. On a new
  PC (§9.10) this becomes a copy, not a safeguard against a wipe.
- Omarchy facts are pinned to tag v4.0.4 (Phase 5 re-checked them there). The release line and the
  `quattro` dev branch have diverged; on install day, re-check anything marked `[source]` against
  the tag you actually install, and don't plan around a **(dev branch only)** feature.
- G1 timing is not predictable from here: the stable mirror's `extra` was last refreshed
  2026-09-08, before Arch's Jellyfin 12.1 (2026-09-22). Check the db; don't guess a date.

### 9.5 Target repo layout

```text
dotfiles/                       # branch: omarchy
├── bash/.bashrc                # + Omarchy env-bootstrap and rc source lines
├── nvim/.config/nvim/          # folded (lockfile); colourscheme via themed tpl
├── vim/  tmux/  yazi/  starship/  herdr/  claude/  bin/   # unfolded; bin/theme + walls-sync removed
├── hypr/.config/hypr/          # override files only: monitors.lua, input.lua,
│                               # bindings.lua, looknfeel.lua, autostart.lua
├── omarchy/.config/omarchy/
│   ├── themed/{yazi-theme.toml,tmux-colors.conf,…}.tpl
│   ├── hooks/post-update.d/10-dotfiles-drift
│   ├── hooks/theme-set.d/…     # only if something still needs a nudge
│   └── shell.json              # idle timings etc., only if changed from default
├── systemd/                    # user units, unchanged
├── systemd-system/             # + inhibit-sleep-on-ac.service, 99-inhibit-sleep-on-ac.rules,
│                               #   logind.conf.d/50-server.conf; deploy.sh extended
└── tests/                      # omarchy_theme_test, check_consumers (re-scoped), herdr, tp_backup
# retired: sway waybar mako fuzzel nwg-drawer kanshi gtk kitty foot htop
#          palettes.toml bin/theme bin/walls-sync tests/theme_test.sh tests/waybar_run_test.sh
```

### 9.6 Build sequence

**Phase 0 — Pre-flight (on EOS, reversible)**
1. `git tag eos-sway-final` on `main`; push the tag. Create branch `omarchy`.
2. Push the four repos with unpushed commits. Triage untracked data (R1).
3. Check the Windows partitions for anything wanted.
4. Back up R2; **test a restore** (R3). Record the Tailscale serve config (`tailscale serve status`)
   and `ufw`-equivalent of today's firewalld zone.
5. ✔ Done 2026-09-25: the two untracked system files are in `systemd-system/` (they were lost
   otherwise, even if you never migrate — this step is worth doing today).

**Phase 1 — Trial (no wipe)**
6. Build the override set in an Omarchy VM (Omarchy documents VM installs): theme mapping, bash,
   nvim, tmux, yazi, herdr, hypr overrides, hooks, tests. Get the test suites green there.
7. If a spare USB SSD is available, install Omarchy to it and boot this laptop from it to answer
   the hardware questions: 580xx vs nouveau power draw (`upower`/`powerstat` at idle, 10 min
   each), lid-on-AC behaviour, snapshot rollback (#8047), `@jellyfin` subvolume + restore.
   **UNRESOLVED** whether such a disk exists — otherwise these move to Phase 3 with the EOS way back
   as the safety net.

**Phase 2 — Install day** (G1–G3 passed; tp2 jobs paused)
8. ISO → new hostname (decided on the day), user `xinye`, whole disk; **`Ctrl + C` at the disk
   confirmation for an unencrypted install** (D2).
9. First boot: `omarchy update`. Record the Omarchy version.
10. D3: `pacman -Rns nvidia-580xx-dkms nvidia-580xx-utils lib32-nvidia-580xx-utils`; remove
    `/etc/modprobe.d/nvidia.conf` and `/etc/mkinitcpio.conf.d/nvidia.conf`; `mkinitcpio -P`;
    reboot; confirm `cat /sys/bus/pci/devices/0000:01:00.0/power/runtime_status` → `suspended`.

**Phase 3 — Server first** (the family notices this; nobody notices your bar)
11. Create the `@jellyfin` subvolume (R8); install `jellyfin-server jellyfin-web tailscale`;
    restore `/var/lib/jellyfin`, `/var/lib/tailscale`; mount `/mnt/ext` at the same path (fstab);
    start Jellyfin, then tailscaled; verify both URLs (R5).
12. Apply S1–S5; `sudo systemd-system/deploy.sh`; verify R6 (lid on AC and on battery).
13. Restore `~/.config/tp-backup`, rclone, the user units; `loginctl enable-linger`; enable timers;
    run `tp-backup` rehearsal; verify R7 with a reboot.

**Phase 4 — Dev layer**
14. Restore `~/.ssh`, `~/.gnupg`, `~/.claude`, `~/.local/state/herdr`; clone repos.
15. For each ported package: diff seeded vs yours → merge → delete seeded → `stow -n -v` → `stow`.
    Delete `~/.local/bin/herdr` if restored. Run `herdr_test.py`, `tp_backup_test.sh`.

**Phase 5 — Look & overrides**
16. Pick an Omarchy theme; add `themed/*.tpl` for yazi/tmux (and nvim if chosen); run
    `omarchy_theme_test`; switch through a few themes; `git status` clean (R9). Install Ghostty
    (*Install > Terminal*) and Chrome (*Install > Browser*), set both as defaults (D6, D9).
17. Minimal `hypr/` overrides (monitors if needed, any binding you can already name). Everything
    else waits for the two-week D5 review.

**Phase 6 — Harden & document**
18. Drift hook; re-scoped `check_consumers.sh`; mutation-check each new test (R10).
19. Rewrite README + PLAYBOOK for Omarchy; archive sway-era §9 entries; update CLAUDE.md (new
    gotchas: symlink write-through, `omarchy-refresh-config` ban, plugin-not-stowable, the
    `.bashrc` source lines, Omarchy skills in `~/.claude/skills`).
20. After four weeks: D5 review; decide the herdr-bar plugin; merge `omarchy` → `main`.

### 9.7 Verification (what "done" means)

```sh
# server
curl -sfo /dev/null https://<tailnet-name>.tail7ff5d7.ts.net/        # family site (from another tailnet device)
curl -sfo /dev/null https://<tailnet-name>.tail7ff5d7.ts.net:8443/   # Jellyfin
systemctl --user list-timers | grep -c tp-backup                  # 6 timers + watchdog, as before
loginctl show-user xinye -p Linger                                # Linger=yes
cat /sys/bus/pci/devices/0000:01:00.0/power/runtime_status        # suspended (D3)
# desktop / repo
hyprctl configerrors                                              # empty
omarchy-theme-set gruvbox && omarchy-theme-set nord && git -C ~/repos/dotfiles status --porcelain  # empty
sh tests/check_consumers.sh && python3 tests/herdr_test.py && sh tests/tp_backup_test.sh
```

### 9.8 Gotchas & failure modes (for the executing agent)

- `cp`-based refresh writes **through** stow symlinks into the repo — never run
  `omarchy-refresh-config` / `omarchy reinstall configs` on a stowed path.
- `/etc/skel` has populated `~/.config` before you stow; `stow -n` refusing is expected.
- A stowed `.bashrc` without Omarchy's two source lines loses PATH setup even for non-interactive
  shells (`env-bootstrap` runs before the interactive guard).
- Undefined `{{key}}` in a `.tpl` is emitted literally, silently.
- Plugins must not contain symlinks.
- Restoring a Jellyfin DB onto an older Jellyfin is unrecoverable — check G1 *on the day*.
- ufw + firewalld together double-filter; install neither firewalld nor its applet.
- The 4.0.4 tag forces NVIDIA GLX on hybrids (Chromium black video) — moot under D3, live if D3 is
  reversed.
- Omarchy skills in `~/.claude/skills` are symlinks re-created by provisioning; restoring an old
  `~/.claude` over them is fine, deleting them is futile.

### 9.9 Open questions blocking implementation

| Q | Blocks | Resolving step |
|---|---|---|
| Backup destination for ~230 GB | Phase 0 | R1 triage, then size the target |
| Spare USB SSD for a hardware trial? | Phase 1 step 7 | Ask/buy; else move checks to Phase 3 |
| Target hardware: this laptop or a new mini PC? | Which of §9.6 / §9.10 applies | Xinye's hardware decision; G1 forces a wait either way |
| Service-level tailnet name | R5, §5.3 | Xinye names it; `tailscale set --hostname=<name>` |
| `omarchy-nvim` deployment | Phase 4 | Inspect package file list in the VM |
| Rollback (#8047) and extra-subvolume restore | Trusting snapshots | Trial test |
| Is `/var/lib/postgres` / `/var/lib/docker` non-empty? | R2 | `sudo du -sh` on both |


### 9.10 Variant: the target is a new mini PC

D1 leaves the target open. If a new PC arrives before G1 clears, the plan gets **safer**, not
longer — nothing is wiped, and the laptop stays a working fallback:

| Laptop plan (§9.6) | New-PC plan |
|---|---|
| Wipe, then rebuild; the way back is a reinstall of EOS + restore | Build Omarchy on the new PC while `xps-eos` keeps serving; the way back is "don't cut over" |
| Phase 1 trial needs a VM or spare disk | The new PC *is* the trial |
| Hardware facts in §4 (NVIDIA, 4K, lid) | Mostly moot: prefer integrated Intel/AMD graphics (D3). A desktop has no lid; drop S4's lid parts, keep the inhibitor only if it has a battery/AC split |
| Backups (R2/R3) guard against a wipe | Same list, used as a **copy** onto the new PC; R3 still proves they restore |
| Tailscale: restore state onto the same box | Stand the service up on the new node, set the **service-level tailnet name** there (§5.3), move `tailscale serve` config, verify both URLs, *then* retire the name on the laptop |
| G1 gates the wipe | G1 gates the **cut-over** of Jellyfin (the DB still can't go to an older Jellyfin) |

Order on a new PC: Phase 4 (dev layer) and Phase 5 (look) first — they're risk-free there — then
Phase 3 (server) as a cut-over once G1 passes: stop Jellyfin on the laptop, copy
`/var/lib/jellyfin`, start it on the new PC, switch the tailnet name, verify R5–R7, and only then
disable the laptop's services. `systemd-system/deploy.sh` is the install step for the inhibitor and
the Jellyfin state dump on either machine.

---

## 10. What changes for you day to day (short version)

Super+Return is still a terminal — Ghostty now, with ligatures. The shell's launcher, Super+K for
every binding, Super+S for the scratchpad (Super+grave if you add one binding, or once the dev
branch's Quake console ships), Super+Ctrl+V for clipboard history, the Omarchy menu for everything
else. Focus moves with Super+arrows until you decide otherwise. Chrome stays your browser, themed
with the rest. Your editor, shell, tmux, yazi, herdr and Claude setup behave as today, coloured by
whichever of Omarchy's 22 themes is active. The family site and Jellyfin move once, to a
service-level tailnet name that survives future hardware changes. After a power cut the server
comes back by itself (no disk passphrase), with your user services running via linger.

---

## 11. References

Status: **✓ Phase 5** = checked by three refute-by-default voters (§12); **· not independently
re-verified** = cited by one research agent only; weight it accordingly. `[source]` = read directly in `omacom/omarchy@quattro`
c3e67f5.

1. Omarchy v4.0.0 release notes — https://github.com/omacom/omarchy/releases/tag/v4.0.0 — ✓ Phase 5
2. `docs/file-layout.md` — https://github.com/omacom/omarchy/blob/quattro/docs/file-layout.md — ✓ Phase 5
3. Manual: Dotfiles — https://github.com/omacom/omarchy/blob/quattro/manual/31-dotfiles.md · https://omarchy.org/manual/dotfiles/ — ✓ Phase 5
4. `config/hypr/hyprland.lua` — https://github.com/omacom/omarchy/blob/quattro/config/hypr/hyprland.lua — ✓ Phase 5
5. Hyprland: Lua configuration news — https://hypr.land/news/26_lua/ — · not independently re-verified
6. omarchy-iso configurator and orchestrator (`configs/airootfs/root/configurator`, `…/orchestrator/phases_impl.py`) — https://github.com/omacom/omarchy-iso — ✓ Phase 5
7. Manual: Unattended installs — https://github.com/omacom/omarchy/blob/quattro/manual/51-unattended-installs.md — · not independently re-verified
8. `docs/update-process.md`; Manual: Updates — https://github.com/omacom/omarchy/blob/quattro/docs/update-process.md · https://omarchy.org/manual/updates/ — ✓ Phase 5
9. `bin/omarchy-update-pacman-guard` — https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-update-pacman-guard — ✓ Phase 5
10. Manual: System snapshots — https://github.com/omacom/omarchy/blob/quattro/manual/47-system-snapshots.md — ✓ Phase 5
11. Issue #8047 (rollback vs btrfs-overlayfs) — https://github.com/omacom/omarchy/issues/8047 — ✓ Phase 5
12. Manual: Making your own theme — https://github.com/omacom/omarchy/blob/quattro/manual/43-making-your-own-theme.md — ✓ Phase 5
13. `themes/nord/colors.toml`, `themes/gruvbox/colors.toml` — https://github.com/omacom/omarchy/tree/quattro/themes — ✓ Phase 5
14. `bin/omarchy-theme-set`, `bin/omarchy-theme-set-foot` — https://github.com/omacom/omarchy/tree/quattro/bin — ✓ Phase 5
15. Manual: Toggles, idle & screensaver — https://github.com/omacom/omarchy/blob/quattro/manual/13-toggles-idle-screensaver.md — · not independently re-verified
16. Manual: System sleep — https://github.com/omacom/omarchy/blob/quattro/manual/36-system-sleep.md — · not independently re-verified
17. `bin/omarchy-refresh-config`; `agents/skills/migrations.md`; migrations `1786273938.sh`, `1781587663.sh`, `1788745941.sh` — https://github.com/omacom/omarchy/tree/quattro/migrations — ✓ Phase 5
18. gigacrat/dotfiles (Omarchy + Stow, `--no-folding`) — https://github.com/gigacrat/dotfiles — · not independently re-verified
19. kogakure/dotfiles-omarchy (post-update drift hook) — https://github.com/kogakure/dotfiles-omarchy — · not independently re-verified
20. `bin/omarchy-plugin-validate` — https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-plugin-validate — ✓ Phase 5
21. Manual: Hotkeys; `bin/omarchy-menu-keybindings` — https://omarchy.org/manual/hotkeys/ — ✓ Phase 5
22. `default/hypr/bindings/tiling.lua`; Discussion #511 (hjkl) — https://github.com/omacom/omarchy/discussions/511 — ✓ Phase 5
23. `default/hypr/qconsole.lua` — https://github.com/omacom/omarchy/blob/quattro/default/hypr/qconsole.lua — ✓ Phase 5
24. Manual: AI; PR #6729; PR #7001 — https://omarchy.org/manual/ai/ · https://github.com/basecamp/omarchy/pull/6729 · https://github.com/basecamp/omarchy/pull/7001 — ✓ Phase 5
25. `bin/omarchy-launch-shell` — https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-launch-shell — ✓ Phase 5
26. `install/hardware/nvidia.sh` — https://github.com/omacom/omarchy/blob/quattro/install/hardware/nvidia.sh — ✓ Phase 5
27. Arch news: NVIDIA 590 drops Pascal — https://archlinux.org/news/nvidia-590-driver-drops-pascal-support-main-packages-switch-to-open-kernel-modules/ — ✓ Phase 5
28. `default/hypr/nvidia.lua`, commit 6ecf4bf2 — https://github.com/omacom/omarchy/blob/quattro/default/hypr/nvidia.lua — ✓ Phase 5
29. Issue #10350 (Pascal + Intel hybrid, i915 hangs) — https://github.com/omacom/omarchy/issues/10350 — · not independently re-verified
30. NVIDIA README: Dynamic power management — https://download.nvidia.com/XFree86/Linux-x86_64/580.95.05/README/dynamicpowermanagement.html — ✓ Phase 5
31. Arch wiki: Dell XPS 15 (9570) — https://wiki.archlinux.org/title/Dell_XPS_15_(9570) — ✓ Phase 5
32. Hyprland wiki: NVIDIA — https://github.com/hyprwm/hyprland-wiki/blob/main/content/nvidia/_index.md — · not independently re-verified
33. Manual: Monitors — https://github.com/omacom/omarchy/blob/quattro/manual/33-monitors.md — · not independently re-verified
34. systemd `logind.conf(5)` — https://github.com/systemd/systemd/blob/main/man/logind.conf.xml — ✓ Phase 5
35. `etc/systemd/logind.conf.d/{10-ignore-power-button,20-inhibit-delay}.conf` [source] — ✓ Phase 5
36. Manual: Getting started; Security — https://github.com/omacom/omarchy/blob/quattro/manual/02-getting-started.md · https://github.com/omacom/omarchy/blob/quattro/manual/48-security.md — ✓ Phase 5
37. `install/config/firewall.sh` — https://github.com/omacom/omarchy/blob/quattro/install/config/firewall.sh — ✓ Phase 5
38. Tailscale KB 1077 — https://tailscale.com/kb/1077/secure-server-ubuntu — · not independently re-verified
39. `install/config/docker.sh`, `enable-services.sh`; Issue #8541 — https://github.com/omacom/omarchy/issues/8541 — ✓ Phase 5
40. omarchy-iso `plans/consumer-secure-boot.md`, `plans/remote.md` — https://github.com/omacom/omarchy-iso/blob/quattro/plans/consumer-secure-boot.md — ✓ Phase 5
41. Arch wiki: systemd-cryptenroll — https://wiki.archlinux.org/title/Systemd-cryptenroll — ✓ Phase 5
42. Arch wiki: Snapper — https://wiki.archlinux.org/title/Snapper — · not independently re-verified
43. Omarchy stable mirror `extra.db` (jellyfin-server 10.11.11-1), fetched 2026-09-25 — https://stable-mirror.omarchy.org/extra/os/x86_64/extra.db — ✓ Phase 5
44. Jellyfin docs: Backup and restore — https://jellyfin.org/docs/general/administration/backup-and-restore/ — ✓ Phase 5
45. Discussion #6577 (3→4 upgrade losses) — https://github.com/basecamp/omarchy/discussions/6577 — · not independently re-verified
46. Discussion #3439; Issue #1802 — https://github.com/basecamp/omarchy/discussions/3439 · https://github.com/omacom/omarchy/issues/1802 — ✓ Phase 5
47. Issue #6933 (old bindings silently not loaded) — https://github.com/omacom/omarchy/issues/6933 — ✓ Phase 5
48. 0xcc.io: docker group root — https://0xcc.io/posts/omarchy-root-creds/ — ✓ Phase 5
49. happyfellow: Merchants of insecurity — https://blog.happyfellow.dev/merchants-of-insecurity/ — · not independently re-verified
50. Issue #3954 (Pascal driver selection) — https://github.com/basecamp/omarchy/issues/3954 — · not independently re-verified
51. PR #5831 (foot replaces alacritty) — https://github.com/basecamp/omarchy/pull/5831 — ✓ Phase 5
52. Arch wiki: firewalld — https://wiki.archlinux.org/title/Firewalld — · not independently re-verified
53. `default/bashrc` [source] — ✓ read directly
54. `install/omarchy-base.packages` [source] — ✓ Phase 5
55. Reviews: techaeris (2026-08-25), devops-daily — https://techaeris.com/2026/08/25/omarchy-quattro-review-year-linux-desktop/ · https://devops-daily.com/posts/omarchy-4-quattro-developer-workstation — · not independently re-verified
56. Issue #8282 (4.0.1 moved stable → edge) — https://github.com/omacom/omarchy/issues/8282 — · not independently re-verified
57. Discussion #2209 (no overlay install) — https://github.com/omacom/omarchy/discussions/2209 — · not independently re-verified
58. Omarchy package repo db (`herdr-0.8.2-1`, `nvidia-580xx-dkms-580.178.04-1.1`, `omarchy-4.0.4-1`, `omarchy-nvim`), fetched 2026-09-25 — https://pkgs.omarchy.org/stable/x86_64/ — ✓ Phase 5
59. Manual: Themes — https://omarchy.org/manual/themes/ — ✓ Phase 5
60. `bin/omarchy-theme-set-claude`, `bin/omarchy-provision-user` [source] — ✓ Phase 5
61. `docs/omarchy-shell.md`; `bin/omarchy-launch-shell`; `shell/plugins/` — https://github.com/omacom/omarchy/blob/quattro/docs/omarchy-shell.md — ✓ Phase 5
62. `shell/plugins/lock/Service.qml` (lock reads the `current/background` symlink) [source] — ✓ read directly
63. `bin/omarchy-update-restart` (reboot confirm), `bin/omarchy-pkg-drop` and the migrations that call it [source] — ✓ read directly
64. `install/config/enable-services.sh` (masks `NetworkManager-wait-online`; no `enable-linger` anywhere shipped) [source] — ✓ read directly
65. omarchy-iso `plans/backup.md`, `plans/server.md`; factory-reset script note on nested subvolumes — https://github.com/omacom/omarchy-iso/tree/quattro/plans — · not independently re-verified
66. Manual: Coming from Mac or Windows — https://omarchy.org/manual/coming-from-mac-or-windows/ — · not independently re-verified
67. `test/shell.d` (255 shell tests, counted at c3e67f5) [source] — ✓ read directly
68. foot issue #57 "Ligature support" — closed wontfix 2025-07-28: "Ligatures is not possible in foot without a large rewrite of the rendering logic" — https://codeberg.org/dnkl/foot/issues/57 — ✓ read directly
69. Manual: Terminal ("we fully support _Alacritty_, _Ghostty_, and _Kitty_"); `config/ghostty/config` and `bin/omarchy-restart-terminal` (`killall -SIGUSR2 ghostty`, run by `omarchy-theme-set`) at v4.0.4 — https://github.com/omacom/omarchy/tree/quattro/manual — ✓ read directly
70. Ghostty config reference, `font-feature` ("To disable programming ligatures, use `-calt`") — https://ghostty.org/docs/config/reference — ✓ read directly
71. `bin/omarchy-install-browser`, `bin/omarchy-default-browser`, `bin/omarchy-theme-set-browser` (Chrome install from the AUR, default, and theming) at v4.0.4 [source] — ✓ read directly
72. Chromium Blog, "Limiting Private API availability in Chromium" (2021-01-15; Chrome Sync unavailable to third-party Chromium builds from 2021-03-15) — https://blog.chromium.org/2021/01/limiting-private-api-availability-in.html · coverage: https://www.bleepingcomputer.com/news/google/google-to-kill-chrome-sync-feature-in-third-party-browsers/ — · not independently re-verified (post body didn't render; dates from coverage)
73. `tailscale set --help` (1.102): "--hostname … hostname to use instead of the one provided by the OS" — ✓ read directly

---

## 12. Verification record

Method: each claim was given to three independent agents instructed to **refute** it (default
`refuted=true` when unverifiable), checking the v4.0.4 tag via `gh api …?ref=v4.0.4`, the ISO
repo, live mirror databases, vendor docs and the cited issues. A claim dies at ≥ 2/3 refutations.
Confidence = evidence quality (primary source code / official doc > issue report > inference),
not tone. Findings from the six research perspectives are author-built lenses; agreement between
them is a strong hypothesis, not field consensus.

| Claim | Votes (refute) | Outcome | Confidence | What changed |
|---|---|---|---|---|
| C1.1 v4 drops waybar/mako/…; one Quickshell shell | 0/3 | Corrected | 9 | Process/CLI naming; clipboard & idle sourced to the plugin tree [61] |
| C1.2 Hyprland Lua, user files after defaults | 0/3 | Corrected | 9 | `bootstrap.lua` first; `default.hypr.toggles` loads after user files |
| C1.3 `/etc/skel` once; `~/.config/omarchy` for dotfile managers; Stow | 0/3 | Corrected | 8 | skel seeds all of `$HOME`; Stow is one linked line, not a guide |
| C1.4 foot is the default terminal | 0/3 | Kept | 9 | — |
| C2.1 month-delayed stable; pacman guard | 0/3 | Corrected | 9 | Guard blocks any `-S`+`-u` combination; exact bypass command |
| C2.2 refresh `cp -f` writes through symlinks | 0/3 | Corrected | 10 | Tested ×3; `.bak` placement depends on folding |
| C2.3 fresh install pre-marks migrations | 0/3 | Corrected | 8 | ISO `--first-install` user only; system markers exist too |
| C2.4 rollback broken (#8047) | 0/3 | **Demoted** | 5 | Single reporter, no LUKS, no maintainer reply; restore chain only |
| C3.1 22 themes; user `.tpl` priority; silent placeholders | 0/3 | Corrected | 9 | Theme-shipped files outrank templates; downstream `{{` checks exist |
| C3.2 Omarchy Nord/Gruvbox values; 2.49:1 | 1/3 | Corrected | 9 | Gruvbox: Material palette on classic bg; nvim/vscode files use original |
| C3.3 foot OSC recolour; theme-set hook | 1/3 | Corrected | 8 | Hook isn't last; skipped headless; single-file hook honoured |
| C3.4 plugin validate rejects symlinks | 0/3 | Corrected | 9 | "outside `.git/`" |
| C4.1 nvidia-580xx auto-install, no opt-out | 0/3 | Corrected | 10 | ID range lives in `omarchy-hw-nvidia-without-gsp` |
| C4.2 GLX env forced on hybrids in v4.0.4 | 0/3 | Corrected | 9 | Quote is a code comment; fix in no released tag |
| C4.3 RTD3 needs Turing; 13 W → 6–7 W | 0/3 | Corrected | 8 | Wiki figure is for turning the card off; power cost to *this* setup still inference ⚠ |
| C4.4 lid suspends on AC | 0/3 | Corrected | 9 | "undocked, internal panel only" |
| C5.1 ufw deny; no `tailscale0` rule | 0/3 | Corrected | 9 | Tailscale installer specifically; ufw-docker FORWARD nuance |
| C5.2 `docker.socket` only; #8541 | 0/3 | Corrected | 9 | #8541 concerns DB-installer containers |
| C5.3 no TPM auto-unlock | 0/3 | **Demoted** (quote) | 8 | Plan quote re-scoped; conclusion now rests on grep + manual + hooks |
| C5.4 subvolumes; snapper root only | 0/3 | Kept (+detail) | 9 | `@factory`, `.snapshots`, optional swap noted |
| C5.5 Jellyfin 10.11.11 vs 12.1; no downgrade | 0/3 | Kept | 9 | Exact db path; mirror refresh date added |
| C6.1 Super+K help; J/K/L taken; **Super+grave console** | 3/3 on grave | **Killed** (grave part) | 9 | Super+grave is dev-branch only (PR #7420); v4.0.4 = Super+S |
| C6.2 agent permission flags (#6729 → #7001) | 0/3 | Corrected | 9 | grok still `bypassPermissions` |
| C6.3 skills symlinked into `~/.claude/skills` | 0/3 | Kept | 9 | — |
| C6.4 shell supervisor: 5/min, no `pdeathsig` | 0/3 | Corrected | 8 | Non-zero exit only, compositor alive, fixed 60 s window |
| C7.1 #6933 silent bindings loss | 0/3 | Kept (+detail) | 9 | Other orphaned files per commenters |
| C7.2 v3 override/binding rewrites | 0/3 | Corrected | 8 | Version hedged; #1802 closed |
| C7.3 docker-group default timeline | 0/3 | Corrected | 8 | Not continuous (06-02..06-17 gap); migration fixes existing users |
| C7.4 herdr migration `rm -f ~/.local/bin/herdr` | 0/3 | Corrected | 9 | Deletion is unconditional — any copy |

**Contested signal — monitor, don't assert:** snapshot rollback breakage (C2.4) and the
NVIDIA idle-power penalty on this machine (C4.3's application) both rest on a single report or on
inference. The trial (§9.6 step 7) turns each into a measurement.

**Added after Phase 5** (with Xinye's decisions, 2026-09-25): D6's ligature facts [68][69][70],
D9's Chrome facts [71][72], §5.3's tailnet-name mechanism [73], and D3's "NVIDIA is optional"
(the installer's `lspci` gate [26], already Phase-5-verified as C4.1). Each was read from its
primary source by the main session, not voted on; [72] rests on secondary coverage of a primary
post whose body didn't render.

**Not verified by Phase 5** (lower-weight, single-source, flagged where used): the Hyprland wiki's
"minute-long Chromium stall" hybrid note [32]; #10350's applicability to the 9570's ports [29];
review quotes [55]; #8282 [56]; kogakure/gigacrat repo practices [18][19].
