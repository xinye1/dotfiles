#! /usr/bin/bash

echo "====== installing R ======"
sudo pacman -S --noconfirm r code

echo "====== installing Chrome and stuff ======"
baph -inN \
  google-chrome \
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

