# Dotfile collection

My small collection.

Currently this is set up on Manjaro i3, i.e. i3 config is in `$HOME/.i3/` by default, rather than the normal `$HOME/.config/`.

## Dependencies

Based on Manjaro i3, needs installing

* xdotool
* xbacklight
* caffeine-ng
* i3blocks and i3blocks-contrib
* rofi
* zsh, oh-my-zsh and powerlevel10k
* Roboto font
* Nerd Fonts patches (e.g. Caskaydiacove)
* kitty and [themes lib](https://github.com/dexpota/kitty-themes)
* lsd
* lightline fugitive for vim

Part of the distro

* picom
* i3
* dunst

Additional apps for workflow

* Google Chrome
* R and RStudio
* Visual Studio Code

## Setup

```sh
cd ~
git clone https://github.com/xinye1/dotfiles.git
cd dotfiles
./install.sh
./symlink.sh
```
