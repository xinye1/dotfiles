#! /usr/bin/bash

echo "Setting up oh-my-zsh..."
git clone https://github.com/zsh-users/zsh-autosuggestions.git $ZSH_CUSTOM/plugins/zsh-autosuggestions
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git $ZSH_CUSTOM/plugins/zsh-syntax-highlighting

echo "Installing kitty..."
git clone --depth 1 git@github.com:dexpota/kitty-themes.git $HOME/.config/kitty/kitty-themes

echo "Grabbing i3blocks-contrib"
git clone git@github.com:vivien/i3blocks-contrib.git $HOME/.i3/blocklets

echo "rofi-calendar fix..."
cp $HOME/dotfiles/i3/rofi-calendar $HOME/.i3/blocklets/rofi-calendar/

echo "Grabbing zsh plugins..."
git clone https://github.com/zsh-users/zsh-autosuggestions.git $ZSH_CUSTOM/plugins/zsh-autosuggestions
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git $ZSH_CUSTOM/plugins/zsh-syntax-highlighting

echo "Vim packages..."
git clone https://github.com/itchyny/lightline.vim $HOME/.vim/pack/plugins/start/lightline
git clone https://tpope.io/vim/fugitive.git $HOME/.vim/pack/plugins/start/fugitive

echo "Power Level 10k..."
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k
