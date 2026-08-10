-- Nord — the thirteen theme roles, for Neovim.
--
-- Sourced from init.lua. `colorscheme.lua` is a symlink to this file or to
-- colorscheme-gruvbox.lua; ~/.local/bin/theme flips it. Already-running nvim
-- instances keep their colours; new ones pick this up.
--
-- The counterpart to colorscheme-gruvbox.lua; both must define exactly the
-- same role names. Which group each role paints lives in highlights.lua, and
-- no colour belongs in this file's neighbours. Roles: PLAYBOOK.md §3.1.
--
-- No plugin backs this. The hexes are the same ones in theme-nord.env and
-- colors-nord.css, so nvim shows the palette rather than an approximation of
-- it — which is also why the two must be edited together.

local apply = dofile(vim.fn.stdpath('config') .. '/highlights.lua')

apply('nord', {
  bg        = '#2E3440',
  surface   = '#3B4252',
  sel       = '#434C5E',
  muted     = '#4C566A',
  fg        = '#D8DEE9',
  fg_bright = '#ECEFF4',
  accent    = '#88C0D0',
  accent2   = '#5E81AC',
  indicator = '#8FBCBB',
  critical  = '#BF616A',
  warning   = '#EBCB8B',
  success   = '#A3BE8C',
  desktop   = '#272B33',
})
