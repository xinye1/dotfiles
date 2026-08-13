-- Neovim. Ported from ~/.vimrc, which is still live and still vim's.
--
-- The two configs are deliberately independent: no `source ~/.vimrc`, no
-- shared runtimepath. They agree on behaviour because both are edited, not
-- because one includes the other.
--
-- The colourscheme is written by hand from the thirteen roles in PLAYBOOK.md
-- §3.1 rather than taken from a plugin, so nvim tracks the same palette as
-- waybar and sway rather than a third party's reading of it. lualine is a
-- plugin, but it is themed from those same roles — see statusline.lua.

--==== Plugins ====
--
-- vim.pack is Neovim 0.12's built-in plugin manager. No bootstrap block to
-- write. Plugin *code* goes to ~/.local/share/nvim/site/pack/core/opt — the
-- data directory, well away from here.
--
-- It does however write ONE file into the config directory:
-- `nvim-pack-lock.json`, pinning each plugin to a revision. Because this
-- package is folded, that lands in the repo — and it is **tracked on
-- purpose**. A pinned revision is a property of the configuration, not of
-- this machine, so unlike `.theme` it belongs in git. The consequence to
-- expect: `:lua vim.pack.update()` dirties the tree, and that commit is the
-- record of the bump. It rewrites the file in place rather than by rename,
-- so it holds no htop-style trap (PLAYBOOK §9.16) either way.
--
-- It clones on first launch, so that one launch needs network. pcall'd
-- because a config that cannot open a file offline is a worse trade than a
-- plain statusline: statusline.lua degrades to the built-in bar, which
-- highlights.lua has already themed.
--
-- Must run before the colourscheme below: that is what themes lualine, and it
-- can only do so once `require('lualine')` resolves.
--
-- Updating is manual and deliberate — `:lua vim.pack.update()`.
if vim.pack then
  pcall(vim.pack.add, {
    'https://github.com/nvim-tree/nvim-web-devicons',
    'https://github.com/nvim-lualine/lualine.nvim',
  })
end

--==== Colours ====
--
-- vim's colorscheme.vim. Guarded so a tree where `theme` has not been run yet
-- starts nvim instead of erroring on every launch.
--
-- termguicolors is set next to the highlights in highlights.lua, not here: it
-- must be on before they are defined, and a fragment that only works when
-- sourced from this file is a trap for whoever reads it next.
local palette = vim.fn.stdpath('config') .. '/colorscheme.gen.lua'
if vim.uv.fs_stat(palette) then
  dofile(palette)
end

--==== Spaces & tabs ====
vim.o.tabstop = 2      -- number of visual spaces per TAB
vim.o.softtabstop = 2  -- number of spaces in tab when editing
vim.o.shiftwidth = 2   -- spaces per step of (auto)indent
vim.o.expandtab = true -- tabs are spaces

--==== UI config ====
vim.o.number = true    -- show line numbers
vim.o.showmatch = true -- highlight matching brackets
--
-- Dropped from .vimrc as already-default in Neovim, listed so their absence
-- reads as a decision rather than an oversight:
--
--   syntax enable, filetype plugin indent on, laststatus=2, showcmd,
--   wildmenu, incsearch, hlsearch, foldenable
--
-- Dropped on purpose: lazyredraw. Neovim's docs advise against it — its
-- asynchronous UI can be left showing a stale screen.

--==== Searching ====
vim.o.ignorecase = true -- ignore case when searching
vim.o.smartcase = true  -- ...unless the search has a capital in it

--==== Folding ====
vim.o.foldmethod = 'indent' -- fold based on indent level
vim.o.foldlevelstart = 10   -- open most folds by default
vim.o.foldnestmax = 10      -- 10 nested folds max

--==== Movement ====
-- Move by visual line, so a wrapped line is not one keystroke tall.
vim.keymap.set('n', 'j', 'gj')
vim.keymap.set('n', 'k', 'gk')

--==== Mappings ====
-- Space opens and closes a fold.
--
-- NOTE: .vimrc carries a commented-out `let mapleader = "\<Space>"`. Enabling
-- it would collide head-on with this map — space cannot be both the leader
-- prefix and a normal-mode command. Carried over as it actually behaves
-- today: leader stays the default backslash. Pick one before uncommenting.
vim.keymap.set('n', '<Space>', 'za')

-- Copy/paste against the system clipboard, on the leader.
--
-- Kept as explicit "+ maps rather than `clipboard=unnamedplus`: that would
-- reroute every unprefixed yank and delete through the system clipboard,
-- which is a behaviour change, not a port.
vim.keymap.set('v', '<Leader>y', '"+y')
vim.keymap.set('v', '<Leader>d', '"+d')
vim.keymap.set({ 'n', 'v' }, '<Leader>p', '"+p')
vim.keymap.set({ 'n', 'v' }, '<Leader>P', '"+P')
