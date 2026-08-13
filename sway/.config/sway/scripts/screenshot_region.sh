#!/bin/sh
# Region screenshot, with the slurp selection box in the active palette.
#
# Usage:  screenshot_region.sh              region -> swappy editor
#         screenshot_region.sh --clipboard  region -> clipboard, no editor
#
# Why a script rather than sway variables: config.d/* is read alphabetically,
# so `default` (which holds the keybindings) is parsed BEFORE `theme` (which
# includes colors.conf). A $role written into a binding in `default` is not yet
# defined and sway rejects the whole config. Sourcing the palette at runtime
# sidesteps parse ordering completely.
set -eu

. "$HOME/.config/sway/theme.gen.env"

# slurp exits non-zero when the selection is cancelled with Escape. Bail out
# rather than handing grim an empty geometry, which the previous inline
# `grim -g "$(slurp)"` did.
geom=$(slurp -b "${BG}cc" -c "$ACCENT" -s "${ACCENT}22" -B "${BG}66") || exit 1

if [ "${1:-}" = "--clipboard" ]; then
    grim -g "$geom" - | wl-copy
else
    grim -g "$geom" - | swappy -f -
fi
