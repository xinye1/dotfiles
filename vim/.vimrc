"==== Set the leader key ====
"let mapleader = "\<Space>"

""==== Colours ====
syntax enable " enable syntax processing
filetype plugin indent on

"==== Spaces & tabs ====
set tabstop=2       " number of visual spaces per TAB
set softtabstop=2   " number of spaces in tab when editing
set shiftwidth=2    " Number of spaces to use for each step of (auto)indent.
set expandtab       " tabs are spaces
"
""==== UI config ====
filetype plugin on	" enable plugin for filetypes
filetype indent on 	" load filetype-specific indent files
set number 		    " show line numbers
set relativenumber
"set cursorline 	" highlight current line
set showcmd 		" show command in bottom bar
set wildmenu 		" visual autocomplete for command menu
set lazyredraw 		" redraw only when it needs to
set showmatch 		" highlight matching brackets

" " Activate Nerdtree using F2
"map <F2> :NERDTreeToggle<CR>
"
" "==== Searching ====
set incsearch 	" search as characters are entered
set hlsearch 	" highlight matches
set ignorecase 	" ignore case when searching
set smartcase 	" when searching try to be smart about cases
" turn off search highlight
 " nnoremap <leader><space> :nohlsearch<CR>
"
" " ==== Folding ====
set foldenable 		" enable folding
set foldlevelstart=10 	" open most folds by default
set foldnestmax=10 	" 10 nested fold max
" " space open/closes folds
nnoremap <space> za
set foldmethod=indent	" fold based on indent level
"
" " ==== Movement =====
" " move vertically by visual line
nnoremap j gj
nnoremap k gk
"
" "==== Copy paste to system clipboard ====
vmap <Leader>y "+y
vmap <Leader>d "+d
vmap <Leader>p "+p
vmap <Leader>P "+P
nmap <Leader>p "+p
nmap <Leader>P "+P

" "==== Code editing ====
" augroup vimrc_autocmds
" autocmd!
" " highlight characters past column 120
" "autocmd FileType python highlight Excess ctermbg=DarkGrey guibg=Black
" "autocmd FileType python match Excess /\%120v.*/
" autocmd FileType python set nowrap
" augroup END



"==== Vim packages =====
" lightline
set laststatus=2   " always show status line
set noshowmode
let g:lightline = {
      \ 'active': {
      \   'left': [ [ 'mode', 'paste' ],
      \             [ 'gitbranch', 'readonly', 'filename', 'modified' ] ]
      \ },
      \ 'component_function': {
      \   'gitbranch': 'FugitiveHead'
      \ },
      \ }

