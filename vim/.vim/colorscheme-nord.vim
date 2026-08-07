" Nord — vim and lightline colours.
"
" Sourced from ~/.vimrc. `colorscheme.vim` is a symlink to this file or to
" colorscheme-gruvbox.vim; ~/.local/bin/theme flips it. Already-running vim
" instances keep their colours; new ones pick this up.
"
" Requires ~/.vim/pack/plugins/start/nord-vim (see PLAYBOOK.md §8).

set termguicolors
colorscheme nord
let g:lightline = { 'colorscheme': 'nord' }
