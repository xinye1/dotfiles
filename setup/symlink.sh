#! /usr/bin/bash

export I3_HOME="$HOME/.config/i3"

echo "====== symlinks ======"
# HOME
ln -fs $HOME/dotfiles/zsh/.zshrc $HOME/.zshrc
ln -fs $HOME/dotfiles/zsh/.aliases $HOME/.aliases
ln -fs $HOME/dotfiles/vim/.vimrc $HOME/.vimrc

# oh-my-zsh
ln -fs $HOME/dotfiles/zsh/.oh-my-zsh $HOME/.oh-my-zsh/oh-my-zsh.sh

# i3
#ln -fs $HOME/dotfiles/i3/.i3/config $I3_HOME/config
ln -fs $HOME/dotfiles/i3/.i3/i3blocks.config $I3_HOME/i3blocks.config
mkdir -p $I3_HOME/scripts
ln -fs $HOME/dotfiles/scripts/matrixlock.sh $I3_HOME/scripts/matrixlock.sh

# rofi
mkdir -p $HOME/.config/rofi
ln -fs $HOME/dotfiles/rofi/.config/rofi/config.rasi $HOME/.config/rofi/config.rasi
ln -fs $HOME/dotfiles/rofi/.config/rofi/xl-common.rasi $HOME/.config/rofi/xl-common.rasi
ln -fs $HOME/dotfiles/rofi/.config/rofi/xl-manjaro.rasi $HOME/.config/rofi/xl-manjaro.rasi
ln -fs $HOME/dotfiles/rofi/.config/rofi/xl-nord.rasi $HOME/.config/rofi/xl-nord.rasi

# lsd
mkdir -p $HOME/.config/lsd
ln -fs $HOME/dotfiles/lsd/.config/lsd/config.yaml $HOME/.config/lsd/config.yaml

# kitty
#mkdir -p $HOME/.config/kitty
#ln -fs $HOME/dotfiles/kitty/.config/kitty/kitty.conf $HOME/.config/kitty/kitty.conf
#ln -fs $HOME/dotfiles/kitty/.config/kitty/nord.conf $HOME/.config/kitty/nord.conf

# picom
#mkdir -p $HOME/.config/picom
#ln -fs $HOME/dotfiles/picom/.config/picom/picom.conf $HOME/.config/picom/picom.conf

# dunst
ln -fs $HOME/dotfiles/dunst/.config/dunst/dunstrc $HOME/.config/dunst/dunstrc

# restart i3
i3-msg restart
