-- lualine, themed from the thirteen roles.
--
-- Palette-neutral, like highlights.lua: it holds no colours, only the decision
-- about which role paints which part of the bar. Called from highlights.lua
-- with the roles the active fragment defined.
--
-- WHY NOT `theme = 'auto'`. lualine's auto mode reads `g:colors_name` and
-- loads its own bundled theme of that name — and it bundles both `nord` and
-- `gruvbox`. It would therefore find one every time and quietly paint the bar
-- in *lualine's* idea of the palette, a few shades off the waybar and sway
-- next to it, with nothing failing to reveal it. Passing a table built from
-- the same roles as everything else is what keeps the bar honest.

return function(c)
  local ok, lualine = pcall(require, 'lualine')
  if not ok then
    -- vim.pack has not fetched it yet (first launch, or no network). The
    -- built-in statusline is already themed by highlights.lua, so this is a
    -- degraded bar rather than a broken editor.
    return
  end

  -- The mode indicator, section `a`. Reads as the palette's own colours
  -- because it is them.
  --
  -- NOTE: under Gruvbox, visual and command sit one hue step apart — accent2
  -- is #D65D0E and warning #FE8019, both oranges. That is the same property
  -- PLAYBOOK.md §3 documents for the palette as a whole: gruvbox's accents
  -- are warm and close together where Nord's are far apart. It is not a
  -- mistake in this mapping, and swapping in a cooler role to fix it would
  -- mean the bar no longer matched the rest of the desktop.
  local function mode(colour)
    return { fg = c.bg, bg = colour, gui = 'bold' }
  end

  local b = { fg = c.fg, bg = c.sel }
  local rest = { fg = c.muted, bg = c.surface }

  local theme = {
    normal   = { a = mode(c.accent),   b = b, c = rest },
    insert   = { a = mode(c.success),  b = b, c = rest },
    visual   = { a = mode(c.accent2),  b = b, c = rest },
    replace  = { a = mode(c.critical), b = b, c = rest },
    command  = { a = mode(c.warning),  b = b, c = rest },
    inactive = {
      a = { fg = c.muted, bg = c.surface },
      b = { fg = c.muted, bg = c.surface },
      c = rest,
    },
  }

  lualine.setup({
    options = {
      theme = theme,
      -- Plain separators. The powerline arrows need glyphs that only a patched
      -- font has; the font here is patched (§9.4), but the bar should not stop
      -- rendering correctly the moment nvim runs somewhere over ssh that has no
      -- Nerd Font. Icons stay on for the same reason they are worth having.
      component_separators = { left = '', right = '' },
      section_separators = { left = '', right = '' },
      globalstatus = true,
    },
  })
end
