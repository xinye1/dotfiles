#! /usr/bin/bash

export I3_HOME="$HOME/.config/i3"

# system tweaks
#echo "====== Turning off the terminal beeping ====="
#echo "blacklist pcspkr" | sudo tee /etc/modprobe.d/nobeep.conf

# install stuff
echo "===== Installing utils and fonts ====="
sudo pacman -S --noconfirm \
  acpi \
  xdotool \
  xorg-xbacklight xorg-xset \
  i3blocks \
  rofi \
  lsd \
  xclip \
  sbxkb \
  unzip \
  cmatrix \
  pulseaudio-bluetooth \
  nerd-fonts-fira-code \
  ttf-cascadia-code \
  ttf-fira-code \
  ttf-font-awesome \
  ttf-roboto \
  gcc-fortran # R dependency

baph -inN \
  nordic-theme-git \
  papirus-folders-nordic \
  nord-vim caffeine-ng \
  nord-vim-lightline

echo "===== Grabbing i3blocks-contrib ====="
git clone https://github.com/vivien/i3blocks-contrib.git $I3_HOME/blocklets

echo "===== Make i3blocks ====="
make -C $I3_HOME/blocklets/bandwidth2/
make -C $I3_HOME/blocklets/cpu_usage2/

echo "===== rofi-calendar fix ====="
cp $HOME/dotfiles/i3/rofi-calendar $I3_HOME/blocklets/rofi-calendar/

echo "===== Vim packages ======"
git clone https://github.com/itchyny/lightline.vim $HOME/.vim/pack/plugins/start/lightline
git clone https://tpope.io/vim/fugitive.git $HOME/.vim/pack/plugins/start/fugitive
git clone https://github.com/lilydjwg/colorizer.git $HOME/.vim/pack/plugins/start/colorizer

echo "===== GTK theme ====="
git clone https://github.com/EliverLara/Nordic.git $HOME/.themes/Nordic
