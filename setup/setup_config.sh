# ===== sync time ======
timedatectl set-ntp true

# ===== ranger =====
sed -i 's+export EDITOR=/usr/bin/nano+export EDITOR=/usr/bin/vim+g' ~/.profile
sed -i 's+export BROWSER=/usr/bin/palemoon+#export BROWSER=/usr/bin/palemmon+g' ~/.profile

# ===== profile ======
sed -i 's/set show_hidden false/set show_hidden true/g' ~/.config/ranger/rc.conf

# ===== nitrogen ======
#sed -i 's/bgcolor=#002a36/bgcolor=#3B4252/g' ~/.config/nitrogen/bg-saved.cfg
