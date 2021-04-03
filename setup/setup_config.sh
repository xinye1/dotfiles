# ===== ranger =====
sed -i 's+export EDITOR=/usr/bin/nano+export EDITOR=/usr/bin/vim+g' ~/.profile
sed -i 's+export BROWSER=/usr/bin/palemoon+#export BROWSER=/usr/bin/palemmon+g' ~/.profile

# ===== profile ======
sed -i 's/set show_hidden false/setshow_hidden true/g' ~/.config/ranger/rc.conf

