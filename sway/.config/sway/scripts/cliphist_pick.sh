#!/bin/sh
# Pick a cliphist entry and put it back on the clipboard: $mod+Ctrl+v and the
# palette's "Clipboard › History".
#
# It was an inline bindsym pipeline. It is a script because the palette runs it
# too (menu.toml's `Clipboard › History`), and the palette raises a failure notification on any non-zero exit: the
# pipeline exited non-zero on Esc, so a cancelled pick would have announced
# itself as a failure. Here a cancelled or empty pick exits 0 (spec §4.2).
set -u
sel=$(cliphist list \
      | fuzzel -d -w 90 -l 30 -p "Select an entry to copy it to your clipboard buffer:") \
    || exit 0
[ -n "$sel" ] || exit 0
printf '%s\n' "$sel" | cliphist decode | wl-copy
