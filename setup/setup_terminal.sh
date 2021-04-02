#! /usr/bin/bash

echo "===== Make zsh the default shell ====="
chsh -s $(which zsh)

echo "===== Installing kitty ====="
curl -L https://sw.kovidgoyal.net/kitty/installer.sh | sh /dev/stdin

echo "===== Setting up oh-my-zsh ====="
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
