# ===== sync time ======
timedatectl set-ntp true

# ===== profile ======
ranger --copy-config=all
sed -i 's/set show_hidden false/set show_hidden true/g' ~/.config/ranger/rc.conf
sed -i 's/set preview_images false/set preview_images true/g' ~/.config/ranger/rc.conf

# ===== picom ======
sed -i 's/fading = false;/fading = true;/g' ~/.config/picom.conf

# ===== bluetooth ======
sudo systemctl enable bluetooth.service

# ===== nitrogen ======
#sed -i 's/bgcolor=#002a36/bgcolor=#3B4252/g' ~/.config/nitrogen/bg-saved.cfg
