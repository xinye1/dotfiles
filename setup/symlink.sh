#! /usr/bin/bash

echo "\n===== oh-my-zsh plugins ====="
git clone https://github.com/zsh-users/zsh-autosuggestions.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-autosuggestions
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting

echo "\n===== Power Level 10k ====="
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k

echo "\n====== symlinks ======"
# HOME
ln -fs $HOME/dotfiles/zsh/.zshrc $HOME/.zshrc
ln -fs $HOME/dotfiles/zsh/.aliases $HOME/.aliases
ln -fs $HOME/dotfiles/vim/.vimrc $HOME/.vimrc

# oh-my-zsh
ln -fs $HOME/dotfiles/zsh/.oh-my-zsh $HOME/.oh-my-zsh/oh-my-zsh.sh

# i3
ln -fs $HOME/dotfiles/i3/.i3/config $HOME/.i3/config
ln -fs $HOME/dotfiles/i3/.i3/i3blocks.config $HOME/.i3/i3blocks.config

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
mkdir -p $HOME/.config/kitty
ln -fs $HOME/dotfiles/kitty/.config/kitty/kitty.conf $HOME/.config/kitty/kitty.conf
ln -fs $HOME/dotfiles/kitty/.config/kitty/nord.conf $HOME/.config/kitty/nord.conf

# picom
mkdir -p $HOME/.config/picom
ln -fs $HOME/dotfiles/picom/.config/picom/picom.conf $HOME/.config/picom/picom.conf

# dunst
ln -fs $HOME/dotfiles/dunst/.config/dunst/dunstrc $HOME/.config/dunst/dunstrc

# restart i3
i3-msg restart
