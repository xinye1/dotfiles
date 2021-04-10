[[ -f ~/.zshrc ]] && . ~/.zshrc

export PATH=$PATH:$HOME/.scripts
export EDITOR="vim"
export TERMINAL="termite"
#export TERMINAL="st"
export BROWSER="google-chrome"

if [[ "$(tty)" = "/dev/tty1" ]]; then
  pgrep i3 || startx
fi
