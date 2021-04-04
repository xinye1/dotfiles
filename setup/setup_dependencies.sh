#! /usr/bin/bash

# system tweaks
echo "====== Turning off the terminal beeping ====="
echo "blacklist pcspkr" | sudo tee /etc/modprobe.d/nobeep.conf

# install stuff
echo "===== Installing utils and fonts ====="
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
  ttf-cascadia-code \
  gcc-fortran # R dependency

echo "===== Make i3blocks ====="
make -C $HOME/.i3/blocklets/bandwidth2/
make -C $HOME/.i3/blocklets/cpu_usage2/

echo "===== Grabbing i3blocks-contrib ====="
git clone https://github.com/vivien/i3blocks-contrib.git $HOME/.i3/blocklets

echo "===== rofi-calendar fix ====="
cp $HOME/dotfiles/i3/rofi-calendar $HOME/.i3/blocklets/rofi-calendar/

echo "===== Vim packages ======"
git clone https://github.com/itchyny/lightline.vim $HOME/.vim/pack/plugins/start/lightline
git clone https://tpope.io/vim/fugitive.git $HOME/.vim/pack/plugins/start/fugitive
git clone https://github.com/lilydjwg/colorizer.git $HOME/.vim/pack/plugins/start/colorizer
