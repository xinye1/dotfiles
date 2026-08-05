#!/bin/bash
#
# Wallpaper. Replaces the stock ~/.azotebg, which was an untracked loose script
# pointing at a 3.3M png inside ~/.config/sway — a binary that had no business
# in a config directory, let alone in a dotfiles repo.
#
# Solid nord0. On a tiling WM the background is mostly occluded anyway, and a
# flat colour keeps the palette exact rather than approximately-Nord.
#
# pkill first: config.d/theme execs this on every `swaymsg reload`, and swaybg
# does not replace an existing instance. Without the pkill, reloads stack up
# swaybg processes the same way the stock config stacked up swayidle.

pkill -x swaybg

# To use an image instead, comment the line below and uncomment this one:
# swaybg -i "$HOME/Pictures/wallpapers/<file>" -m fill &
swaybg -c "#2E3440" &
