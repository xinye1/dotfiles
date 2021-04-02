#! /usr/bin/bash

# system tweaks
echo "Turning off the terminal beeping..."
echo "blacklist pcspkr" | sudo tee /etc/modprobe.d/nobeep.conf

# install stuff
echo "Installing utils and fonts..."
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

echo "Make zsh the default shell..."
chsh -s $(which zsh)

echo "Setting up oh-my-zsh..."
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
git clone https://github.com/zsh-users/zsh-autosuggestions.git $ZSH_CUSTOM/plugins/zsh-autosuggestions
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git $ZSH_CUSTOM/plugins/zsh-syntax-highlighting

echo "Installing kitty..."
curl -L https://sw.kovidgoyal.net/kitty/installer.sh | sh /dev/stdin
git clone --depth 1 git@github.com:dexpota/kitty-themes.git $HOME/.config/kitty/kitty-themes

echo "Grabbing i3blocks-contrib"
git clone git@github.com:vivien/i3blocks-contrib.git $HOME/.i3/blocklets

echo "Grabbing zsh plugins..."
git clone https://github.com/zsh-users/zsh-autosuggestions.git $ZSH_CUSTOM/plugins/zsh-autosuggestions
git clone https://github.com/zsh-users/zsh-syntax-highlighting.git $ZSH_CUSTOM/plugins/zsh-syntax-highlighting

echo "Vim packages..."
git clone https://github.com/itchyny/lightline.vim $HOME/.vim/pack/plugins/start/lightline
git clone https://tpope.io/vim/fugitive.git $HOME/.vim/pack/plugins/start/fugitive

# i3block rofi-calendar fix
# temporary until PR merged
cp $HOME/dotfiles/i3/rofi-calendar $HOME/.i3/blocklets/rofi-calendar/

# manual stuff
echo "Restart system and run `git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/themes/powerlevel10k`"
echo "Change $EDITOR var to /usr/bin/vim in ~/.profile"
