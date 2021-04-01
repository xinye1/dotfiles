#! /usr/bin/bash

# system tweaks
echo "Turning off the terminal beeping..."
echo "blacklist pcspkr" | sudo tee /etc/modprobe.d/nobeep.conf

# a few utils
echo "Installing utils and fonts..."
sudo pacman -S --noconfirm \
  xdotool \
  xorg-xbacklight xorg-xset \
  caffeine-ng \
  i3blocks \
  rofi \
  zsh \
  lsd \
  xclip \
  unzip \
  ttf-roboto \
  ttf-font-awesome \
  ttf-cascadia-code

# utilities to make R work
echo "Installing R package dependencies"
sudo pacman -S --noconfirm \
  gcc-fortran

# install kitty
echo "Installing kitty..."
curl -L https://sw.kovidgoyal.net/kitty/installer.sh | sh /dev/stdin
git clone --depth 1 git@github.com:dexpota/kitty-themes.git \
  ~/.config/kitty/kitty-themes

# make zsh the default shell
echo "zsh for default shell..."
chsh -s $(which zsh)

# grap i3blocks-contrib
echo "Grabbing i3blocks-contrib"
git clone \
  git@github.com:vivien/i3blocks-contrib.git \
  $HOME/.i3/blocklets

# zsh plugins
echo "Grabbing zsh plugins"
git clone \
  https://github.com/zsh-users/zsh-autosuggestions.git \
  $ZSH_CUSTOM/plugins/zsh-autosuggestions
git clone \
  https://github.com/zsh-users/zsh-syntax-highlighting.git \
  $ZSH_CUSTOM/plugins/zsh-syntax-highlighting

# vim packages
git clone \
  https://github.com/itchyny/lightline.vim \
  ~/.vim/pack/plugins/start/lightline
git clone \
  https://tpope.io/vim/fugitive.git \
  ~/.vim/pack/plugins/start/fugitive
