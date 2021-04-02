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

echo "Installing kitty..."
curl -L https://sw.kovidgoyal.net/kitty/installer.sh | sh /dev/stdin

# i3block rofi-calendar fix
# temporary until PR merged
cp $HOME/dotfiles/i3/rofi-calendar $HOME/.i3/blocklets/rofi-calendar/

# manual stuff
echo "Change $EDITOR var to /usr/bin/vim in ~/.profile"
