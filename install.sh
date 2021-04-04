#! /usr/bin/bash

# install dependencies
./setup/setup_dependencies.sh
./setup/setup_config.sh
./setup/setup_apps.sh
./setup/setup_terminal.sh

# link dotfiles
./setup/symlink.sh