#!/bin/bash

# Palette, so the selection box matches the active theme. theme.env is a
# symlink switched by ~/.local/bin/theme.
. "$HOME/.config/sway/theme.env"

grim -g "$(swaymsg -t get_tree | jq -r '.. | select(.pid? and .visible?) | .rect | "\(.x),\(.y) \(.width)x\(.height)"' | slurp -b "${BG}cc" -c "$ACCENT" -s "${ACCENT}22" -B "${BG}66")" - | swappy -f -
