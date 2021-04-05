#! /bin/bash

kitty \
  --start-as fullscreen \
  --class cmatrix \
  --name cmatrix \
  -e cmatrix -s

i3lock -n; # i3-msg kill
