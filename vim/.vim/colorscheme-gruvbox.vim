" Gruvbox Dark — vim and lightline colours.
"
" Requires ~/.vim/pack/plugins/start/gruvbox (see PLAYBOOK.md §8).
" `background=dark` must be set before the colorscheme: gruvbox reads it to
" choose between its light and dark variants, and defaults to light.

set termguicolors
set background=dark
colorscheme gruvbox
let g:lightline = { 'colorscheme': 'gruvbox' }
