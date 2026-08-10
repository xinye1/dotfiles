-- Gruvbox Dark — the thirteen theme roles, for Neovim.
--
-- The counterpart to colorscheme-nord.lua; both must define exactly the same
-- role names. Which group each role paints lives in highlights.lua.
--
-- Unlike vim's fragment there is no `set background=dark` here: that existed
-- to stop morhetz/gruvbox choosing its light variant. Nothing reads it now —
-- these are literal hexes — and Neovim's default is dark anyway.

local apply = dofile(vim.fn.stdpath('config') .. '/highlights.lua')

apply('gruvbox', {
  bg        = '#282828',
  surface   = '#3C3836',
  sel       = '#504945',
  muted     = '#7C6F64',
  fg        = '#EBDBB2',
  fg_bright = '#FBF1C7',
  accent    = '#FABD2F',
  accent2   = '#D65D0E',
  indicator = '#8EC07C',
  critical  = '#FB4934',
  warning   = '#FE8019',
  success   = '#B8BB26',
  desktop   = '#1D2021',
})
