#usr/bin/bash

# install stuff
echo "===== Installing utils and fonts ====="
sudo pacman -S --noconfirm \
  lsd \
  unzip \
  cmatrix \
  ttf-cascadia-code \
  ttf-roboto \
  flameshot \
  fcitx5 \
  fcitx5-gtk \
  fcitx5-chinese-addons \
  fcitx5-configtool \
  gcc-fortran # R dependency

baph -inN \
  papirus-nord \
  nord-vim \
  caffeine-ng \
  nord-vim-lightline \
  nordic-standard-button-theme \
  nordic-darker-standard-buttons-theme \
  nordic-bluish-accent-standard-buttons-theme

echo "===== Vim packages ======"
git clone https://github.com/itchyny/lightline.vim $HOME/.vim/pack/plugins/start/lightline
git clone https://tpope.io/vim/fugitive.git $HOME/.vim/pack/plugins/start/fugitive
git clone https://github.com/lilydjwg/colorizer.git $HOME/.vim/pack/plugins/start/colorizer
