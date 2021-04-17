# ===== sync time ======
timedatectl set-ntp true

# ===== profile ======
ranger --copy-config=all
sed -i 's/set show_hidden false/set show_hidden true/g' ~/.config/ranger/rc.conf
sed -i 's/set preview_images false/set preview_images true/g' ~/.config/ranger/rc.conf

# ====== wallpapers =====
cd $HOME/Pictures
git clone --depth 1 https://github.com/tamaldearroz/nord-wallpapers
git clone https://github.com/dxnst/nord-backgrounds.git
