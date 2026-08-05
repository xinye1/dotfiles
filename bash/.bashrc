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
# Matches what sway actually launches on mod+Return (`set $term footclient` in
# ~/.config/sway/config.d/default). This said "alacritty" until the two were
# reconciled; anything reading $TERMINAL was opening a different terminal to the
# keybinding. alacritty stays installed for machines where foot can't run.
export TERMINAL="foot"

# --- Aliases ----------------------------------------------------------------
alias ls='ls --color=auto'
alias ll='ls -alh --color=auto'
alias grep='grep --color=auto'

# Carried over from the old zsh package (dropped in 3c3cfc0):
alias mkd='mkdir -pv'
alias pm='sudo pacman'
alias vimrc='vim ~/.vimrc'
alias bashrc='vim ~/.bashrc'   # was `zshrc` in the old .aliases

# --- mise: per-project tool versions ---------------------------------------
# Applies a repo's .mise.toml pins on cd (trading-platform-v2 pins python 3.12,
# node 18, go 1.22). Activated *before* starship so the prompt's version modules
# read mise's interpreter rather than the ambient one.
#
# Guarded so this file still works on a machine without mise. Note the early
# return above means non-interactive shells get no shims — inside scripts use
# `mise exec -- <cmd>` or `mise run <task>`.
command -v mise >/dev/null && eval "$(mise activate bash)"

# --- Prompt -----------------------------------------------------------------
# Fallback prompt set *before* starship: if starship is missing the guard below
# is skipped and this PS1 stays in effect, so the shell is still usable.
PS1='[\u@\h \W]\$ '
command -v starship >/dev/null && eval "$(starship init bash)"
