#
# ~/.bashrc — managed by ~/repos/dotfiles (stow package: bash)
#

# If not running interactively, don't do anything
[[ $- != *i* ]] && return

# --- PATH -------------------------------------------------------------------
# Before the tool activations below: both mise and starship land in ~/.local/bin
# when installed without a package manager.
export PATH="$HOME/.local/bin:$PATH"

# --- Environment ------------------------------------------------------------
# EDITOR was previously set in the old i3 package's .profile, which went away
# with the X11 setup; it has been unset since.
export EDITOR="vim"
export VISUAL="vim"
# The AUR google-chrome package ships /usr/bin/google-chrome-stable only — there is
# no bare `google-chrome`, so the old i3/.profile value would not resolve today.
export BROWSER="google-chrome-stable"
# Matches what sway actually launches on mod+Return (`set $term kitty` in
# ~/.config/sway/config.d/default). This said "alacritty", then "foot", each
# time until the two were reconciled; anything reading $TERMINAL was opening a
# different terminal to the keybinding. Keep it a bare command name: a program
# reading $TERMINAL expects to exec it, and some do not split the value into
# arguments at all.
export TERMINAL="kitty"

# --- Aliases ----------------------------------------------------------------
alias ls='ls --color=auto'
alias ll='ls -alh --color=auto'
alias grep='grep --color=auto'

# Carried over from the old zsh package (dropped in 3c3cfc0):
alias mkd='mkdir -pv'
alias pm='sudo pacman'
alias vimrc='vim ~/.vimrc'
alias bashrc='vim ~/.bashrc'   # was `zshrc` in the old .aliases

# --- yazi --------------------------------------------------------------------
# `y` runs yazi and leaves the shell in whatever directory yazi ended up in.
# Plain `yazi` cannot do this — a child process cannot change its parent's
# working directory — so yazi writes the path to --cwd-file and the wrapper
# reads it back. This is yazi's own documented recipe; the guards are ours.
#
# Guarded on the binary like mise and starship below, so this file still works
# on a machine without yazi. Note the early return at the top: a non-interactive
# shell never sees this, so test it with `bash -ic`, never `bash -lc`.
#
# `builtin cd` rather than `cd` in case a later alias shadows it, and the
# tempfile is removed on every path — including the one where yazi exits with Q
# (quit --no-cwd-file), which leaves the file empty on purpose.
command -v yazi >/dev/null && y() {
    local cwd dir
    cwd=$(mktemp -t "yazi-cwd.XXXXXX") || return
    yazi "$@" --cwd-file="$cwd"
    if [ -s "$cwd" ] && IFS= read -r dir < "$cwd" && [ -n "$dir" ] && [ "$dir" != "$PWD" ]; then
        builtin cd -- "$dir" || true
    fi
    rm -f -- "$cwd"
}

# --- mise: per-project tool versions ---------------------------------------
# Applies a repo's .mise.toml pins on cd (trading-platform-v2 pins python 3.12,
# node 18, go 1.22). Activated *before* starship so the prompt's version modules
# read mise's interpreter rather than the ambient one.
#
# Guarded so this file still works on a machine without mise. Note the early
# return above means non-interactive shells get no shims — inside scripts use
# `mise exec -- <cmd>` or `mise run <task>`.
command -v mise >/dev/null && eval "$(mise activate bash)"

# --- LS_COLORS ---------------------------------------------------------------
# The file uses only the 16 ANSI slots, so it follows whichever terminal
# palette the theme switcher has set — no per-theme variant needed.
if [ -r "$HOME/.config/dircolors" ]; then
    eval "$(dircolors -b "$HOME/.config/dircolors")"
fi

# --- Prompt -----------------------------------------------------------------
# Fallback prompt set *before* starship: if starship is missing the guard below
# is skipped and this PS1 stays in effect, so the shell is still usable.
PS1='[\u@\h \W]\$ '
command -v starship >/dev/null && eval "$(starship init bash)"
