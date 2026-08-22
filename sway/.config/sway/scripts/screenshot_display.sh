#!/bin/sh
# Whole-display screenshot: the focused output, straight into the swappy editor.
#
# Usage:  screenshot_display.sh   focused output -> swappy editor
#
# Bound to Shift+Print. No slurp and so no palette to source -- the geometry is
# an entire output, and sway already knows which one has focus.
set -eu

# With no focused output jq prints nothing, and the unquoted `grim -o $output`
# this used to be then collapsed to `grim -o -`: grim took the `-` as an OUTPUT
# NAME, found no such output, and swappy opened an editor over an empty stream.
# An output name can also hold spaces ("Some Vendor Monitor"), which the same
# missing quotes word-split into two arguments.
output_id=$(swaymsg -t get_outputs | jq -r '.[] | select(.focused).name')
if [ -z "$output_id" ]; then
    printf 'screenshot_display: no focused output; nothing to capture\n' >&2
    exit 1
fi

# Via a file rather than `grim … - | swappy -f -`: in a pipeline swappy starts
# regardless, so a grim that fails halfway still puts an empty editor on the
# screen. Writing first means a grim failure ends the script (set -e) before
# swappy is ever reached.
shot=$(mktemp -t "screenshot_display.XXXXXX.png") || exit 1
trap 'rm -f "$shot"' EXIT HUP INT TERM

grim -o "$output_id" "$shot"
swappy -f "$shot"
