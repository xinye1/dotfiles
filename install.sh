#! /usr/bin/bash

# HOME
ln -fs $HOME/dotfiles/zsh/.zshrc $HOME/.zshrc
ln -fs $HOME/dotfiles/zsh/.aliases $HOME/.aliases
ln -fs $HOME/dotfiles/vim/.vimrc $HOME/.vimrc

# i3
ln -fs $HOME/dotfiles/i3/.i3/config $HOME/.i3/config
ln -fs $HOME/dotfiles/i3/.i3/i3blocks.config $HOME/.i3/i3blocks.config

# rofi
mkdir -p $HOME/.config/rofi
ln -fs $HOME/dotfiles/rofi/.config/rofi/config.rasi $HOME/.config/rofi/config.rasi
ln -fs $HOME/dotfiles/rofi/.config/rofi/xl-common.rasi $HOME/.config/rofi/xl-common.rasi
ln -fs $HOME/dotfiles/rofi/.config/rofi/xl-manjaro.rasi $HOME/.config/rofi/xl-manjaro.rasi

# lsd
mkdir -p $HOME/.config/lsd
ln -fs $HOME/dotfiles/lsd/.config/lsd/config.yaml $HOME/.config/lsd/config.yaml

# other utility
ln -fs $HOME/dotfiles/picom/.config/picom/picom.conf $HOME/.config/kitty/kitty.conf
ln -fs $HOME/dotfiles/kitty/.config/kitty/kitty.conf $HOME/.config/kitty/kitty.conf
ln -fs $HOME/dotfiles/dunst/.config/dunst/dunstrc $HOME/.config/dunst/dunstrc
