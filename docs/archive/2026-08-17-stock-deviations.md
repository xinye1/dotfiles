# Stock deviations and retired mechanisms

Archived from PLAYBOOK.md on 2026-08-17. This is the historical record of what changed relative
to stock EndeavourOS Sway CE and of designs that were measured and rejected. Nothing here is
needed to operate the desktop — the live rules live in PLAYBOOK §3, §5 and §9. It is kept because
the *reasons* keep the same mistakes from being remade.

## The pre-render theming scheme (retired 2026-08-13)

Each themed file was kept twice, once per palette, with a theme-neutral symlink pointing at
whichever was active. The colours were written 36 times, the 18 pointers had to be enumerated in
`.gitignore` because no glob could catch names like `colors.css` and `.gtkrc-2.0` without also
catching tracked files, and a test existed only to catch that list falling behind. The render
scheme replaced it: generation chooses the output name, so a glob can catch it. The full designs
are in `2026-08-06-theme-switching-design.md` and `2026-08-13-simplify-theming-design.md`.

### 6.1 Theming

| | Stock | Here | Why |
|---|---|---|---|
| sway borders | Dracula `#6272A4` / `#282A36` / `#F8F8F2` | `$accent` focus, `$accent2` focused-inactive, `$muted` unfocused | Consistency; stock clashed with the terminals. Role names, so both palettes get the same ladder |
| sway border bg | `bground` == `border` (accent-filled titlebar) | `bground` = `$bg` | The accent belongs on the border, not flooding the title area |
| sway font | `Noto Sans Regular 10` | `JetBrainsMono Nerd Font 10` | Matches bar and launcher; glyph coverage |
| Terminals | *Nordic* (`#242933`) | *Nord* (`#2E3440`) | See §3.2 — different scheme despite the name |
| waybar | `@highlight #685878`, `@base1 #19191e`, literal `orange`/`red` | The thirteen roles as `@define-color`, in the rendered `colors.gen.css` | One-off hexes matched nothing else, and named roles are what make two palettes possible |
| waybar calendar | pastel pink `#ff6699` `#ecc6d9` `#99ffdd` | `$accent2` weekdays, `$warning` today, `$muted` week numbers | Loudest palette break in the setup. The weekday colour moved nord9 → nord7 in the role rewrite — the one deliberate visual change on the Nord side |
| waybar font | `JetBrainsMono` | `"JetBrainsMono Nerd Font"` | §9.4 |
| mako | Arc blue `#5294e2` on `#404552` | `$surface` body / `$accent` border | |
| mako frame | 5px border, square | 2px border, `border-radius=10,0,0,10` | Rounded on the left, square on the right, so the card reads as a tab flush against the screen edge. Note `border-size` is **not** directional in mako 1.11 — only `margin`, `outer-margin`, `padding` and `border-radius` are, so a per-edge accent *spine* cannot be expressed; asymmetric corners are the closest thing |
| mako icons | `/usr/share/icons/Arc-X-D` | `/usr/share/icons/Papirus-Dark` | **The stock path does not exist** — icons were silently falling back |
| fuzzel | purple/navy `08052bdd`, Dracula selection `44475add` | `$bg` / `$sel` / `$accent` border | Related to nothing else |
| fuzzel font | `JetBrainsMono-Regular` | `JetBrains Mono` | §9.4 — file name vs fontconfig family |
| nwg-drawer | `rgba(38,18,57,.9)` purple | `@bg` with alpha | |
| gtklock | 22 MB background image, purple accents | Solid `@bg`, role-named accents | Image moved to `~/Pictures/wallpapers`; a 22 MB binary has no place in a config dir |
| GTK theme / icons | `Arc-Dark` / `Qogir-Dark` | `Nordic` or `Colloid-Yellow-Dark-Gruvbox`, `Papirus-Dark` | Per palette, from the `gtk_theme_name` role, rendered into `settings.ini` and `theme.gen.env` |
| GTK dark hint | `gtk-application-prefer-dark-theme=0` | `=1` | Was `0` while the theme name was a *dark* variant — libadwaita apps rendered light |
| libadwaita | *(nothing)* | `gtk-4.0/gtk.css` + `color-scheme` in gsettings | §2.2 — the only way to reach these apps |
| Wallpaper | 3.3 MB PNG via untracked `~/.azotebg` | `output * bg $desktop solid_color` | Native to sway; no loose script, no tracked binary |

### 6.2 Defects fixed

| Defect | Detail | Fix | Verify |
|---|---|---|---|
| **swayidle process leak** | `exec_always swayidle …` re-ran on every reload without killing the previous instance. **40 were alive** when found, all racing to lock the screen | `exec_always pkill -x swayidle; swayidle …` | `pgrep -xc swayidle` → `1`, still `1` after a second reload |
| **No idle locking at all** | Stock had `before-sleep` only — no `timeout` clauses, so an unattended machine never locked or blanked | `timeout 300` lock, `timeout 600` dpms off + resume | Leave it 5 minutes |
| **`XDG_CURRENT_DESKTOP` empty** | greetd doesn't set it; stock imported the *empty* value into systemd and dbus. `xdg-desktop-portal` picks its backend from it, with portal-gtk and portal-wlr both installed — the choice was arbitrary | `systemctl --user set-environment` + `dbus-update-activation-environment`, both `exec_always`. Full fix in §6.4 | `systemctl --user show-environment \| grep XDG_CURRENT` |
| **Undeclared display scale** | `config.d/output` was 100% comments. `eDP-1` runs 3840×2160 at scale 2 by autodetection — worked here, would silently not reproduce elsewhere | `output eDP-1 { scale 2 }` | `swaymsg -t get_outputs` |
| **Unhandled lid switch** | A `Lid_Switch` input exists; nothing bound to it | `bindswitch --reload --locked lid:on/off` | Close the lid |
| **mako icon path** | Points at a directory that does not exist | Papirus-Dark | `notify-send -i firefox test` |
| **Hex guard blind to bare colours** | `tests/check_hex.py` asserts "no tracked config carries a literal hex" and passed while `sway/…/config.d/default` ran `fuzzel … -t bf616aff -S bf616aff`. The regex required a leading `#`; fuzzel's `-t`/`-S` want a bare `RRGGBBAA`. Same colour, different spelling. The cost was not the one off-palette picker — it was a green check certifying a rule it could not see | `BARE_HEX` pattern added; the binding moved into `scripts/cliphist_delete.sh`, which sources `theme.gen.env` and derives `${CRITICAL#\#}ff` at press time, because `config.d/default` is parsed before `config.d/theme` (§9.6) | `python3 tests/check_hex.py .`; `theme gruvbox` then `$mod+Ctrl+x` — picker is gruvbox red, not Nord red |
| **Critical notifications expired after 5s** | `[urgency=high] ignore-timeout=1` was commented "never time out on their own". It does not mean that. Per `man 5 mako` it means *ignore the timeout the app asked for and use `default-timeout` instead* — which is `5000` globally. So critical notifications vanished after five seconds, **and** an app that explicitly asked to stay longer was overridden into vanishing sooner. The comment described the intent, not the behaviour, and nothing ever checked | `default-timeout=0` alongside `ignore-timeout=1` in the same criteria. The pair is what makes it stick: ignore what the app said, then apply no timeout | `notify-send -u critical x y`, wait >5s, `makoctl list` still shows it |
| **waybar workspaces 1–2** | `format-icons` covered `"3"`–`"10"` only; 1 and 2 fell through to the raw name | Added, plus a `default` | Harmless for numeric workspaces; breaks the moment one is renamed |
| **No Nerd Font** | Only the symbols-only fallback was installed; every glyph rendered via fontconfig fallback | `ttf-jetbrains-mono-nerd` | §9.4 |
| **Cursor theme never resolved** | The name was written `Qogir-dark` in 13 places; the directory is `/usr/share/icons/Qogir-Dark`. XCursor resolves by **case-sensitive path**, so it silently fell back to the default cursor everywhere | `Qogir-Dark` throughout, plus `seat * xcursor_theme` and `~/.icons/default/index.theme` so it reaches XWayland and the compositor cursor too | `ls -d /usr/share/icons/Qogir-dark` errors, `-Dark` does not — that one letter was the whole bug |
| **Dangling GTK2 include** | `.gtkrc-2.0` ended with `include "/home/xinye/.gtkrc-2.0.mine"` — a file that has never existed on this machine | Line dropped | `grep -rl gtkrc-2.0.mine ~/repos/dotfiles --exclude-dir=.git --exclude-dir=docs` → nothing but this file |
| **Stale, untracked xsettingsd** | `~/.config/xsettingsd/xsettingsd.conf` was untracked and still named `Arc-Dark` / `Qogir-Dark`, disagreeing with `settings.ini`. **xsettingsd is not running**, which is exactly why the drift was invisible | Tracked in the `gtk` package, per-theme, generated from the same names as everything else | `readlink -f ~/.config/xsettingsd/xsettingsd.conf` is inside the repo |
| **alacritty depended on an untracked clone** | Its palette was imported from `~/.config/alacritty/themes`, so the repo alone did not describe the colours | A self-contained rendered `colors.gen.toml`; the clone is now optional | The only `import` in `alacritty.toml` is `~/.config/alacritty/colors.gen.toml` |
| **Cancelled screenshot ran anyway** | `grim -g "$(slurp)"` — pressing Escape gave slurp a non-zero exit and an empty string, and grim was handed an empty geometry | `scripts/screenshot_region.sh` captures slurp's exit status and bails | `Print`, then Escape: nothing is written and swappy does not open |


*(The alacritty package itself was retired on 2026-08-17 — kitty is the terminal, foot the
standalone fallback. The `~/.config/alacritty/themes` clone was never managed here.)*

## Terminal recolouring: rejected designs and the measurements behind §9.11

**The rejected trick, recorded so it is not re-proposed:** park Nord in foot's `[colors-dark]` and
Gruvbox in `[colors-light]`, then switch with `SIGUSR1`. It works, and it was still rejected twice
over — it caps the setup at exactly two themes forever, and it makes the config lie, with a dark
palette declared as the light one.

**The `--restart-terminals` flag that never existed.** This document once read as if
`theme <name> --restart-terminals` ran `pkill -x foot; foot --server`. No such flag ever existed in
`theme` — the argument parser rejects any unknown option, so every copy of that line was an
instruction that would have exited non-zero. It is recorded here because the drift is the lesson:
four places described a flag nobody had run, and nothing checks prose against `--help`. (The
render-scheme grep in `tests/theme_test.sh` is the descendant of that lesson.)

It is not coming back: restarting terminals to recolour them destroys the processes inside them,
which are the user's and not the theme switcher's. **tmux sessions are the exception and survive
it** (verified: the server's PPID is 1, so it is never a child of the terminal; SIGKILL the pty
owner and the session and its jobs stay up and reattachable). But that only protects what was
already started *inside* tmux, which is not a safe assumption to design a default around.

**kitty `--single-instance` was measured and rejected.** It is the direct analogue of the
`foot --server` this replaced — one process serving every window — so it was the obvious default
and it is not the one here. Measured on this machine:

| | `--single-instance` | one process per window |
|---|---|---|
| invoke → shell actually running | **47 ms** | 221 ms |
| PSS, two windows open | **87 MB** | 136 MB |
| one window crashes | **every window dies** | the others are unaffected |

~175 ms and ~50 MB per window is not worth every terminal sharing a fate. Note also that
single-instance does not fix the cold start: the first window still pays the 221 ms, because there
is no daemon. It buys speed only for windows 2..n.

Two arguments in the usual pro/con list do not apply to kitty, and both were checked rather than
reasoned about:

- *"Config changes only reach new processes"* — false. Two independent kitty processes both
  recoloured across a `theme` switch, because `reload_conf_in_all_kitties()` walks every GUI
  process. Palette switching never depended on a shared process.
- *"Windows inherit the environment of the original parent"* — false for kitty, whatever it may be
  for other terminals. kitty forwards both the environment and the cwd over the single-instance
  socket; a second window invoked with `MARKER=second` from a different directory got both.
