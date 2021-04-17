#! /usr/bin/bash

echo "====== symlinks ======"
# HOME
ln -fs $HOME/dotfiles/zsh/.zshrc $HOME/.zshrc
ln -fs $HOME/dotfiles/zsh/.aliases $HOME/.aliases
ln -fs $HOME/dotfiles/vim/.vimrc $HOME/.vimrc

# xfce
ln -fs $HOME/dotfiles/xfce/whiskermenu-1.rc $HOME/.config/xfce4/panel/whiskermenu-1.rc

# oh-my-zsh
ln -fs $HOME/dotfiles/zsh/.oh-my-zsh $HOME/.oh-my-zsh/oh-my-zsh.sh

# rofi
mkdir -p $HOME/.config/rofi
ln -fs $HOME/dotfiles/rofi/.config/rofi/config.rasi $HOME/.config/rofi/config.rasi
ln -fs $HOME/dotfiles/rofi/.config/rofi/xl-common.rasi $HOME/.config/rofi/xl-common.rasi
ln -fs $HOME/dotfiles/rofi/.config/rofi/xl-manjaro.rasi $HOME/.config/rofi/xl-manjaro.rasi
ln -fs $HOME/dotfiles/rofi/.config/rofi/xl-nord.rasi $HOME/.config/rofi/xl-nord.rasi

# lsd
mkdir -p $HOME/.config/lsd
ln -fs $HOME/dotfiles/lsd/.config/lsd/config.yaml $HOME/.config/lsd/config.yaml

# termite
mkdir -p $HOME/.config/termite
ln -fs $HOME/dotfiles/termite/.config/termite/config $HOME/.config/termite/config

# dunst
ln -fs $HOME/dotfiles/dunst/.config/dunst/dunstrc $HOME/.config/dunst/dunstrc
