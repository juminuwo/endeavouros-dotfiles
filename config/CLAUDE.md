# Cross-Project Context

This file is symlinked to `~/git/CLAUDE.md` and inherited by every project under `~/git/`. Keep content here strictly to things useful in *every* project — project-specific guidance belongs in that project's own `CLAUDE.md`.

## OS & Environment
- **OS:** EndeavourOS (Arch-based, rolling release)
- **Window Manager:** i3
- **Shell:** zsh
- **Terminal:** Kitty
- **Package Manager:** yay (AUR + pacman wrapper)
- **Editor:** Neovim (`vim` is aliased to `nvim`), Cursor IDE

## Development Tools
- **Python 3** — managed per-project with `uv` (creates `.venv/` in the project root)
- **Node.js**, **GitHub CLI** (`gh`), **Docker** — installed system-wide
- For exact versions, run `<tool> --version` — versions drift, don't pin them here

## Conventions
- Git repos live in `~/git/`
- Each project has its own `CLAUDE.md` for project-specific commands and structure
- Python projects use `uv` with `.venv` in the project directory

## Obsidian Vault
The vault lives at `~/Documents/online-personal/`. For any vault-related task, the `obsidian-vault` skill loads the full structure, conventions, and publishing flow on trigger — don't duplicate vault content here.
