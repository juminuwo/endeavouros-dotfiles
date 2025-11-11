return {
  -- Add Rosé Pine
  {
    "rose-pine/neovim",
    name = "rose-pine",
    opts = {
      variant = "main", -- 'main', 'moon', or 'dawn'
    },
  },

  -- Configure LazyVim to use it
  {
    "LazyVim/LazyVim",
    opts = {
      colorscheme = "rose-pine",
    },
  },
}
