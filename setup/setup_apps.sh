#! /usr/bin/bash

sudo pacman -Rns --noconfirm \
  gimp \
  palemoon-bin

sudo pacman -S --noconfirm r

pamac build --no-confirm \
  google-chrome \
  visual-studio-code-bin \
  rstudio-desktop-bin

# use Intel MKL for R
#if
#  [ $(inxi -C | grep -i intel | wc -l) -eq 1 ]
#then
#  pamac install --no-confirm intel-mkl
#  pamac build --no-confirm r-mkl
#else
#  pacman -S --no-confirm r
#fi

