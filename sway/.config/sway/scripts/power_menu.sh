#!/bin/bash

MENU="$(printf "󰌾 Lock\n󰤄 Suspend\n󰍃 Log out\n Reboot\n Reboot to UEFI\n󰐥 Shutdown")"
if [[ "$(systemctl is-enabled suspend.target 2>/dev/null)" == "masked" ]]; then
    MENU="$(echo "$MENU" | grep -v Suspend)"
fi
LINE_COUNT="$(printf '%s' "$MENU" | grep -c .)"

# '%s\n' and not "$MENU": the menu is DATA, and `printf "$MENU"` hands it to
# printf as the FORMAT string. It works only because no label happens to hold
# a % or a backslash today. The day one does, printf eats it and that row goes
# missing from the picker with no error anywhere -- a power menu quietly one
# entry short. Same reason line 7 already spells it `printf '%s'`.
SELECTION="$(printf '%s\n' "$MENU" | fuzzel --dmenu -a top-right -l "$LINE_COUNT" -w 18 -p "Select an option: ")"

confirm_action() {
    local action="$1"
    CONFIRMATION="$(printf "No\nYes" | fuzzel --dmenu -a top-right -l 2 -w 18 -p "$action?")"
    [[ "$CONFIRMATION" == *"Yes"* ]]
}

case $SELECTION in
    *"󰌾 Lock"*)
        ~/.config/sway/scripts/lock.sh;;
    *"󰤄 Suspend"*)
        if confirm_action "Suspend"; then
            systemctl suspend
        fi;;
    *"󰍃 Log out"*)
        if confirm_action "Log out"; then
            swaymsg exit
        fi;;
    *" Reboot"*)
        if confirm_action "Reboot"; then
            systemctl reboot
        fi;;
    *" Reboot to UEFI"*)
        if confirm_action "Reboot to UEFI"; then
            systemctl reboot --firmware-setup
        fi;;
    *"󰐥 Shutdown"*)
        if confirm_action "Shutdown"; then
            systemctl poweroff
        fi;;
esac
