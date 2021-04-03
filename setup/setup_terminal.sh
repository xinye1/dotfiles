#! /usr/bin/bash

echo "===== Make zsh the default shell ====="
chsh -s $(which zsh)

echo "===== Installing kitty ====="
curl -L https://sw.kovidgoyal.net/kitty/installer.sh | sh /dev/stdin
git clone --depth 1 https://github.com/dexpota/kitty-themes.git $HOME/.config/kitty/kitty-themes

echo "===== Setting up oh-my-zsh ====="
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

echo "===== Setting up oh-my-zsh ====="
git clone https://github.com/zsh-users/zsh-autosuggestions.git $ZSH_CUSTOM/plugins/zsh-autosuggestions
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git $ZSH_CUSTOM/plugins/zsh-syntax-highlighting

echo "===== Power Level 10k ====="
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k
