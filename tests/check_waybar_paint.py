"""Assert no waybar module inherits its paint from the system GTK theme.

A waybar state class is a *bare* GTK style class, so it shares a namespace with
GTK's own stock ones. `warning` is the collision that bit: GtkInfoBar's stock
class set is `.info/.warning/.question/.error`, and the Nordic theme styles it
unscoped --

    .info, .warning, .question, .error { background-color: #c3674a; }

-- so every widget carrying one of those names took a solid infobar fill.
cpu, memory and battery get `warning` from their `states` in waybar's config
and custom-claude gets it from scripts/claude_usage.py, which parks there for
most of a working day: an orange block appeared behind text style.css had only
ever given a *colour* to. Colloid, gruvbox's GTK theme, scopes the same class
(`infobar.warning`) and leaked nothing, so this was invisible for as long as
the palette the widget was written under stayed put -- it surfaced on the first
switch to nord, months later.

That is the class of bug worth a guard, not the one instance. Reading style.css
for the missing `background-color` would only ever re-check the fix; the actual
question is what GTK *paints*, which is answered by rendering. So each module is
built offscreen -- a widget of that name inside a `#waybar` parent, the shape
waybar builds -- once bare and once per style class, under every GTK theme
palettes.toml names. A class that changes the painted background is a class the
theme is styling through us.

Deliberately wider than the classes waybar emits today: the whole stock set is
tested, because the next collision will be a class name nobody looked up.

Two things are outside the net, both on purpose:

  * `#workspaces button` is a real GtkButton and takes a background from the
    GTK theme under *both* palettes, as it always has. Overriding that is a
    look change, not a fix -- and CSS has no way to say "the theme's button
    background, minus the infobar rules", so the fix would have to invent a
    colour. Left alone, and so left untested.
  * animations. `#memory.critical` blinks its background from a keyframe, which
    is our paint, not the theme's. `gtk-enable-animations` is turned off so the
    comparison sees the static value; without it the sampled colour depends on
    when the frame was grabbed.

Needs a display and the GTK themes installed, hence check_consumers.sh rather
than the sandboxed theme_test.sh. Exits 77 when it cannot run at all, which
that script reports as a skip -- a check that cannot see its subject must say
so rather than pass.
"""
import re
import sys
import tomllib
from collections import Counter
from pathlib import Path

# GtkInfoBar's stock style classes. The four that themes style unscoped, and
# the reason this file exists.
STOCK_CLASSES = ("info", "warning", "question", "error")
# Sampling stride over the rendered widget. The dominant colour is the fill;
# a 1px border or antialiased glyph cannot outvote it, so this stays a question
# about the background rather than about text.
STRIDE = 3
SIZE = 60
# `#workspaces button` — see the module docstring.
EXEMPT_IDS = {"workspaces"}
SKIP_EXIT = 77


def theme_names(repo):
    """Every gtk_theme_name in palettes.toml, palette name -> theme name."""
    with open(repo / "palettes.toml", "rb") as fh:
        table = tomllib.load(fh)
    return {name: p["gtk_theme_name"] for name, p in table.items()
            if isinstance(p, dict) and "gtk_theme_name" in p}


def theme_installed(name):
    return any((Path(d).expanduser() / name).is_dir()
               for d in ("~/.themes", "~/.local/share/themes",
                         "/usr/share/themes"))


def uncommented(style_css):
    """style.css with its /* */ comments removed.

    Not cosmetic: the selectors below are found by regex, and this file
    documents itself heavily. `tests/check_waybar_paint.py` in a comment reads
    as a class named `py` and `palettes.toml` as one named `toml`, which is how
    a prose paragraph silently adds renders to the sweep. Same lesson as
    check_hex.py's comment table -- what counts as a comment has to be decided
    before anything is matched, not after.
    """
    return re.sub(r'/\*.*?\*/', '', style_css.read_text(), flags=re.DOTALL)


def module_ids(style_css, waybar_config):
    """The widget names to test: what style.css names, plus what config enables.

    Both, because neither is sufficient. A module can be styled and not
    enabled (`#window`, currently commented out of config) or enabled and
    unstyled -- and an unstyled module is exactly the one with no
    `background-color` of its own to stop the theme.
    """
    css = uncommented(style_css)
    # Bare `#id` selectors only. `#workspaces button` and `#custom-claude.warning`
    # are descendants and states of something already in the list.
    ids = set()
    for chunk in re.findall(r'([^{}]*)\{', css):
        for sel in chunk.split(","):
            sel = sel.strip()
            if re.fullmatch(r'#[\w-]+', sel):
                ids.add(sel[1:])
    # waybar's config is JSONC with trailing commas, so it is read for the one
    # thing a regex reads reliably: the quoted names inside the modules-* lists.
    conf = waybar_config.read_text()
    conf = re.sub(r'^\s*//.*$', '', conf, flags=re.MULTILINE)
    for body in re.findall(r'"modules-(?:left|center|right)"\s*:\s*\[(.*?)\]',
                           conf, flags=re.DOTALL):
        for name in re.findall(r'"([^"]+)"', body):
            # waybar's widget name is the module name with the group prefix
            # dropped for sway/*, and the slash turned into a dash otherwise.
            ids.add(name.split("/", 1)[1] if name.startswith("sway/")
                    else name.replace("/", "-"))
    return sorted(ids - {"waybar"} - EXEMPT_IDS)


def style_classes(style_css):
    found = set(re.findall(r'[#\w]\.([a-zA-Z][\w-]*)', uncommented(style_css)))
    return sorted(found | set(STOCK_CLASSES))


def main(repo, style_path, config_path):
    repo, style_css = Path(repo), Path(style_path).expanduser()
    waybar_config = Path(config_path).expanduser()
    for path in (style_css, waybar_config):
        if not path.is_file():
            print(f"no {path} — run `theme` then `stow waybar`", file=sys.stderr)
            return SKIP_EXIT
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, Gtk
    except (ImportError, ValueError) as exc:
        print(f"no GTK 3 python bindings ({exc})", file=sys.stderr)
        return SKIP_EXIT
    if Gtk.init_check()[0] is False:
        print("no display", file=sys.stderr)
        return SKIP_EXIT

    settings = Gtk.Settings.get_default()
    settings.set_property("gtk-application-prefer-dark-theme", True)
    settings.set_property("gtk-enable-animations", False)
    provider = Gtk.CssProvider()
    provider.load_from_path(str(style_css))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def painted(widget_id, classes):
        """The dominant colour of the module as GTK actually draws it."""
        win = Gtk.OffscreenWindow()
        win.set_name("waybar")
        box = Gtk.Box()
        win.add(box)
        label = Gtk.Label(label=" ")
        label.set_name(widget_id)
        for cls in classes:
            label.get_style_context().add_class(cls)
        label.set_size_request(SIZE, SIZE)
        box.pack_start(label, True, True, 0)
        win.show_all()
        while Gtk.events_pending():
            Gtk.main_iteration()
        pixbuf = win.get_pixbuf()
        data = pixbuf.get_pixels()
        width, height = pixbuf.get_width(), pixbuf.get_height()
        stride, chans = pixbuf.get_rowstride(), pixbuf.get_n_channels()
        seen = Counter()
        for y in range(0, height, STRIDE):
            for x in range(0, width, STRIDE):
                off = y * stride + x * chans
                seen["#%02x%02x%02x" % tuple(data[off:off + 3])] += 1
        win.destroy()
        return seen.most_common(1)[0][0]

    ids = module_ids(style_css, waybar_config)
    classes = style_classes(style_css)
    if not ids or not classes:
        print(f"derived {len(ids)} module ids and {len(classes)} classes from "
              f"{style_css} — this check can no longer see its subject",
              file=sys.stderr)
        return SKIP_EXIT

    bad, checked = [], 0
    for palette, theme in sorted(theme_names(repo).items()):
        if not theme_installed(theme):
            print(f"{palette}: GTK theme {theme!r} is not installed — the "
                  f"render below would silently be Adwaita's", file=sys.stderr)
            return SKIP_EXIT
        settings.set_property("gtk-theme-name", theme)
        for widget_id in ids:
            base = painted(widget_id, ())
            for cls in classes:
                checked += 1
                got = painted(widget_id, (cls,))
                if got != base:
                    bad.append(
                        f"{palette} ({theme}): #{widget_id}.{cls} paints {got}, "
                        f"not {base} — the GTK theme is styling the bare "
                        f"`.{cls}` class through waybar's; declare the paint in "
                        f"style.css")
    for line in bad:
        print(line, file=sys.stderr)
    print(f"{checked} module/class renders across "
          f"{len(theme_names(repo))} GTK themes")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
