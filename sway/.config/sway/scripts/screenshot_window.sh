#!/bin/bash

# Palette, so the selection box matches the active theme. theme.gen.env is a
. "$HOME/.config/sway/theme.gen.env"

grim -g "$(swaymsg -t get_tree | jq -r '.. | select(.pid? and .visible?) | .rect | "\(.x),\(.y) \(.width)x\(.height)"' | slurp -b "${BG}cc" -c "$ACCENT" -s "${ACCENT}22" -B "${BG}66")" - | swappy -f -
