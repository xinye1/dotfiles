-- The palette-neutral half of the colourscheme: which role paints which
-- highlight group. Contains no colours and never needs editing to add a
-- palette.
--
-- This is the same split the rest of the repo uses — `colors-nord.css`
-- defines the roles and `style.css` spends them; here `colorscheme-nord.lua`
-- defines the roles and this file spends them. Adding a third palette means
-- one new fragment and no change to this file.
--
-- Neovim links its treesitter groups to these classic groups by default
-- (`@comment` -> `Comment`, and so on), so a treesitter-highlighted buffer
-- inherits everything below without a parser or a plugin in sight.

-- Every role a fragment must define. Kept as an explicit list so that a
-- fragment missing one fails here, by name, at startup — GTK's failure mode
-- for the same mistake is a widget silently turning black, and this is the
-- cheap opportunity to do better than that.
local REQUIRED = {
  'bg', 'surface', 'sel', 'muted', 'fg', 'fg_bright',
  'accent', 'accent2', 'indicator', 'critical', 'warning', 'success',
  'desktop',
}

return function(name, c)
  for _, role in ipairs(REQUIRED) do
    if not c[role] then
      error(("colorscheme %s: role '%s' is not defined"):format(name, role))
    end
  end

  -- Must be on before the highlights are set, or every gui colour below is
  -- quantised to the terminal's 256.
  vim.o.termguicolors = true

  -- `highlight clear` first: without it a switch would layer the new scheme
  -- over whatever the old one left behind, and only the groups both schemes
  -- define would actually change.
  vim.cmd('highlight clear')
  if vim.fn.exists('syntax_on') == 1 then
    vim.cmd('syntax reset')
  end
  vim.g.colors_name = name

  -- `desktop` is deliberately unused. It is the wallpaper-layer role — the
  -- shade *behind* the windows — and an editor has no such surface. Listed in
  -- REQUIRED anyway so the two fragments stay symmetric with every other pair
  -- in the repo.

  local hl = {
    -- Core
    Normal       = { fg = c.fg, bg = c.bg },
    NormalFloat  = { fg = c.fg, bg = c.surface },
    Cursor       = { fg = c.bg, bg = c.fg },
    CursorLine   = { bg = c.surface },
    CursorLineNr = { fg = c.accent, bold = true },
    LineNr       = { fg = c.muted },
    ColorColumn  = { bg = c.surface },
    Visual       = { bg = c.sel },
    MatchParen   = { fg = c.accent, bg = c.sel, bold = true },
    Search       = { fg = c.bg, bg = c.warning },
    IncSearch    = { fg = c.bg, bg = c.accent },
    Folded       = { fg = c.muted, bg = c.surface },
    FoldColumn   = { fg = c.muted, bg = c.bg },
    SignColumn   = { bg = c.bg },
    NonText      = { fg = c.sel },
    Whitespace   = { fg = c.sel },
    Directory    = { fg = c.accent },
    Title        = { fg = c.fg_bright, bold = true },
    Conceal      = { fg = c.muted },

    -- Windows, statusline, menus
    StatusLine   = { fg = c.fg_bright, bg = c.surface },
    StatusLineNC = { fg = c.muted, bg = c.surface },
    WinSeparator = { fg = c.sel },
    TabLine      = { fg = c.muted, bg = c.surface },
    TabLineSel   = { fg = c.fg_bright, bg = c.bg, bold = true },
    TabLineFill  = { bg = c.surface },
    Pmenu        = { fg = c.fg, bg = c.surface },
    PmenuSel     = { fg = c.bg, bg = c.accent },
    PmenuSbar    = { bg = c.surface },
    PmenuThumb   = { bg = c.muted },
    WildMenu     = { fg = c.bg, bg = c.accent },

    -- Syntax
    Comment      = { fg = c.muted, italic = true },
    Constant     = { fg = c.accent2 },
    String       = { fg = c.success },
    Character    = { fg = c.success },
    Number       = { fg = c.accent2 },
    Boolean      = { fg = c.accent2 },
    Identifier   = { fg = c.fg },
    Function     = { fg = c.accent },
    Statement    = { fg = c.accent2 },
    Operator     = { fg = c.fg_bright },
    Keyword      = { fg = c.accent2 },
    PreProc      = { fg = c.indicator },
    Type         = { fg = c.indicator },
    Special      = { fg = c.warning },
    Underlined   = { fg = c.accent, underline = true },
    Todo         = { fg = c.bg, bg = c.warning, bold = true },
    Error        = { fg = c.bg, bg = c.critical },

    -- Messages
    ErrorMsg     = { fg = c.critical },
    WarningMsg   = { fg = c.warning },
    MoreMsg      = { fg = c.success },
    Question     = { fg = c.accent },

    -- Diff
    DiffAdd      = { fg = c.success, bg = c.surface },
    DiffDelete   = { fg = c.critical, bg = c.surface },
    DiffChange   = { fg = c.accent2, bg = c.surface },
    DiffText     = { fg = c.bg, bg = c.accent2 },

    -- Diagnostics
    DiagnosticError = { fg = c.critical },
    DiagnosticWarn  = { fg = c.warning },
    DiagnosticInfo  = { fg = c.accent },
    DiagnosticHint  = { fg = c.indicator },
    DiagnosticOk    = { fg = c.success },
  }

  for group, spec in pairs(hl) do
    vim.api.nvim_set_hl(0, group, spec)
  end

  -- The sixteen ANSI slots :terminal renders with. Left to the terminal's own
  -- palette they would be foot's or alacritty's colours, which are themed from
  -- the same table but reach nvim only by coincidence; setting them here means
  -- a :terminal buffer is the same palette as the editor around it whatever
  -- launched nvim.
  local ansi = {
    c.sel, c.critical, c.success, c.warning,
    c.accent2, c.indicator, c.accent, c.fg,
    c.muted, c.critical, c.success, c.warning,
    c.accent2, c.indicator, c.accent, c.fg_bright,
  }
  for i, colour in ipairs(ansi) do
    vim.g['terminal_color_' .. (i - 1)] = colour
  end

  -- lualine is themed from the same roles rather than from its own bundled
  -- palettes. Done here, at the end, because this is the point where the roles
  -- are in hand and the highlights they must match are already set.
  dofile(vim.fn.stdpath('config') .. '/statusline.lua')(c)
end
