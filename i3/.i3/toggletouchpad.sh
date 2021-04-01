#!/bin/bash

# from here https://github.com/hashtagsaurav/dotfiles/blob/master/.config/i3/toggletouchpad.sh
if synclient -l | grep "TouchpadOff .*=.*0" ; then
	    synclient TouchpadOff=1 ;
    else
	    synclient TouchpadOff=0 ;
fi
