# System Context

## OS & Environment
- **OS:** EndeavourOS (Arch-based, rolling release)
- **Window Manager:** i3 (v4.25.1) — config at `~/.config/i3/config`
- **Shell:** zsh
- **Terminal:** Kitty
- **Package Manager:** yay (AUR + pacman wrapper)
- **Editor:** Neovim (`vim` is aliased to `nvim`), Cursor IDE
- **Docker:** v29.2.1

## Development Tools
- **Python:** 3.14.2
- **Node.js:** v25.2.1
- **uv:** 0.9.11 (Python project/package manager — used across all Python projects)
- **GitHub CLI:** gh

## Conventions
- Python projects use `uv` with `.venv` in the project directory
- Each project has its own CLAUDE.md with project-specific commands and structure
- Git repos live in `~/git/`

## Obsidian Vault
- Location: `/home/howis/Documents/online-personal/`
- Personal notes: `/home/howis/Documents/online-personal/Personal/`
- Project ideas and planning: `/home/howis/Documents/online-personal/Personal/Projects/`

## Active Projects (~/git/)
- **logistics-kit** — Python logistics library (routing, pricing, tracking) using OR-Tools
- **logistics-pricing** — Freight pricing engine with FastAPI
- **customer-tracking-portal** — Streamlit freight tracking portal with Supabase
- **route-optimisation** — Route optimisation tooling
- **badminton-computer-vision** — CV project using uv
- **business-scout** — Business acquisition candidate finder
- **auto-tech-blog** — Git activity to Obsidian blog entries
- **twitter-bot** — Twitter/X automation
- **personal_keyboard** — QMK keyboard config
- **predictive-maintenance** — Predictive maintenance project
- **endeavouros-dotfiles** — System dotfiles (see below)

## endeavouros-dotfiles — system source of truth

`~/git/endeavouros-dotfiles/` is the source of truth for system config (i3, Kitty, zsh, Claude Code, `~/bin` scripts, packages, systemd units). `~/.config/i3/config`, `~/.claude/settings.json`, `~/bin/*` etc. are **symlinks managed by dotbot** — edit the file under `config/` in the repo, never the symlink target.

### Three install entry points (idempotent, re-runnable)
- `./install` — dotbot symlinker, driven by `install.conf.yaml`
- `./install-packages` — installs everything in `config/packages-{repo,aur}.txt`
- `./host-install` — installs systemd units from `config/host/systemd/`

### When adding something, do it in the repo so a fresh machine gets it

| Adding... | Put the file at... | Then... |
|---|---|---|
| A config file | `config/<whatever>` | add a `link:` entry in `install.conf.yaml`, run `./install` |
| A `~/bin/` or `~/.local/bin/` script | `config/<name>` (or `config/bin/<name>` for `~/.local/bin`) | add `link:` entry, `chmod +x` the source, run `./install` |
| A new dependency | `config/packages-repo.txt` (pacman) or `config/packages-aur.txt` (AUR) | run `./install-packages` |
| A systemd unit | `config/host/systemd/{system,user}/` | extend `host-install`, re-run it |
| A Claude Code skill | `config/claude-skills/<name>/SKILL.md` | add `link:` entry pointing at `~/.claude/skills/<name>` |

### Conventions
- **`config/`** = portable, symlinked. **`config/host/`** = machine-specific (drive UUIDs, hardware-tied services), not symlinked.
- After editing a config that's already symlinked, no install step is needed — the live file *is* the repo file.
- After adding/removing a `link:` entry, run `./install` to apply.
- Reload i3 after touching `config/i3/config`: `i3-msg reload`.
- Don't hand-write files into `~` when a dotbot-managed equivalent exists — edit the source under `config/` instead.

## Laptop Setup
- For laptops, uncomment the `[battery]` block in `config/i3/i3blocks.conf` (line ~144) and its `command=` line to show battery level in the i3 status bar. Requires `acpi` package.

## Project Ideas (Obsidian Vault)
- **Driver Shield 360** — 360° camera system for delivery driver protection (Pi 5 + commodity cameras)
- **Shipping Spend Intelligence** — Shopify app for UK e-commerce shipping cost analysis
- **Badminton Computer Vision** — Court/player tracking
