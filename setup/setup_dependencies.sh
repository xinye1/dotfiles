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

