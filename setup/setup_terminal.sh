#! /usr/bin/bash

echo "\n===== Make zsh the default shell ====="
chsh -s $(which zsh)

echo "\n===== Installing kitty ====="
curl -L https://sw.kovidgoyal.net/kitty/installer.sh | sh /dev/stdin
git clone --depth 1 https://github.com/dexpota/kitty-themes.git $HOME/.config/kitty/kitty-themes

echo "\n===== Setting up oh-my-zsh ====="
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

