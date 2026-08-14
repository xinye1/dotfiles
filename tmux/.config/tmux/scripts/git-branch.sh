#!/bin/sh
# The branch of the repository the active pane is sitting in, for the status bar.
#
#   git-branch.sh <directory>      ->  "main "  |  "main* "  |  "a1b2c3d "  |  ""
#
# Prints nothing at all outside a repository, so the whole segment disappears
# rather than leaving an empty label behind. The trailing space is part of the
# output for the same reason: it belongs to the segment, so status-right does
# not have to reserve one for a branch that may not exist.
#
# Why a file rather than an inline `#()` in tmux.conf: the one-liner needs an
# awk program, quoted, inside a tmux format string, in which `#` introduces a
# format sequence and `,` separates the arms of a conditional. A file has none
# of those hazards and can be run on its own to see what it does.
#
# One `git status` rather than `rev-parse` plus a second call: `--porcelain=v2
# --branch` reports the branch and the modified entries in a single walk. `-uno`
# keeps it off the untracked-file walk, which is what makes it cheap enough for
# `status-interval`; the cost of that is that a repo dirty ONLY with untracked
# files reads as clean here.
set -eu

[ $# -eq 1 ] || exit 0
cd "$1" 2>/dev/null || exit 0

git --no-optional-locks status --porcelain=v2 --branch -uno 2>/dev/null | awk '
    /^# branch\.oid/  { oid  = $3 }
    /^# branch\.head/ { head = $3 }
    /^[^#]/           { dirty = "*" }
    END {
        # A detached HEAD reports the literal "(detached)" as the branch name,
        # which says nothing; the commit it is on does.
        if (head == "(detached)") head = substr(oid, 1, 7)
        # Escape `#` the way tmux`s own `qh` modifier would. Output of a `#()`
        # is spliced into the status line BEFORE tmux parses `#[...]` style
        # directives, so a branch named `fix/#123` would leave a bare `#` that
        # pairs with the `#` of the following directive and prints it as text.
        # `#` is legal in a git ref, and this is the one segment whose content
        # tmux.conf cannot put a modifier on.
        gsub(/#/, "##", head)
        if (head != "") printf "%s%s ", head, dirty
    }
'
