#!/bin/sh
# Window screenshot, with the slurp selection box in the active palette.
#
# Usage:  screenshot_window.sh   pick a window -> swappy editor
#
# Bound to Ctrl+Print. The candidates are sway's own window rectangles -- every
# node in the tree with a pid that is currently visible -- fed to slurp, which
# snaps the selection to whichever one the pointer is over. That is the whole
# difference from screenshot_region.sh: same box, same colours, but the
# geometry comes from the compositor rather than a freehand drag.
#
# Why a script rather than sway variables: config.d/* is read alphabetically,
# so `default` (which holds the keybindings) is parsed BEFORE `theme` (which
# includes colors.gen.conf). A $role written into a binding in `default` is not yet
# defined and sway rejects the whole config. Sourcing the palette at runtime
# sidesteps parse ordering completely.
set -eu

. "$HOME/.config/sway/theme.gen.env"

# slurp exits non-zero when the selection is cancelled with Escape. Bail out
# rather than handing grim an empty geometry: `grim -g "" -` does not fail, it
# writes an empty stream, and swappy opened an editor over nothing every time
# Escape was pressed. Same bail as screenshot_region.sh, for the same reason.
geom=$(swaymsg -t get_tree \
       | jq -r '.. | select(.pid? and .visible?) | .rect | "\(.x),\(.y) \(.width)x\(.height)"' \
       | slurp -b "${BG}cc" -c "$ACCENT" -s "${ACCENT}22" -B "${BG}66") || exit 1
[ -n "$geom" ] || exit 1

grim -g "$geom" - | swappy -f -
