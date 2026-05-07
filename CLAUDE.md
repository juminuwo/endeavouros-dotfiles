# endeavouros-dotfiles — system source of truth

This repo is the source of truth for system config (i3, Kitty, zsh, Claude Code, `~/bin` scripts, packages, systemd units). `~/.config/i3/config`, `~/.claude/settings.json`, `~/bin/*`, `~/git/CLAUDE.md` etc. are **symlinks managed by dotbot** — edit the file under `config/` in the repo, never the symlink target.

## Three install entry points (idempotent, re-runnable)

- `./install` — dotbot symlinker, driven by `install.conf.yaml`
- `./install-packages` — installs portable packages in `config/packages-{repo,aur}.txt` (works on any machine)
- `./host-install` — installs hardware-specific packages (`config/host/packages-host-repo.txt`) and systemd units from `config/host/systemd/`

## When adding something, do it in the repo so a fresh machine gets it

| Adding... | Put the file at... | Then... |
|---|---|---|
| A config file | `config/<whatever>` | add a `link:` entry in `install.conf.yaml`, run `./install` |
| A `~/bin/` or `~/.local/bin/` script | `config/<name>` (or `config/bin/<name>` for `~/.local/bin`) | add `link:` entry, `chmod +x` the source, run `./install` |
| A portable dependency | `config/packages-repo.txt` (pacman) or `config/packages-aur.txt` (AUR) | run `./install-packages` |
| A hardware-specific package (NVIDIA, Intel ucode, etc.) | `config/host/packages-host-repo.txt` | run `./host-install` |
| A systemd unit | `config/host/systemd/{system,user}/` | extend `host-install`, re-run it |
| A Claude Code skill | `config/claude-skills/<name>/SKILL.md` | add `link:` entry pointing at `~/.claude/skills/<name>` |

## Conventions

- **`config/`** = portable, symlinked. **`config/host/`** = machine-specific (drive UUIDs, hardware-tied services), not symlinked.
- After editing a config that's already symlinked, no install step is needed — the live file *is* the repo file.
- After adding/removing a `link:` entry, run `./install` to apply.
- Reload i3 after touching `config/i3/config`: `i3-msg reload`.
- Don't hand-write files into `~` when a dotbot-managed equivalent exists — edit the source under `config/` instead.

## Two CLAUDE.md files in this repo

- **`config/CLAUDE.md`** — symlinked to `~/git/CLAUDE.md`, inherited by every `~/git/<project>` cwd. Keep it lean; cross-project content only.
- **`CLAUDE.md`** (this file) — only loaded when cwd is inside this repo. Dotfiles-specific guidance goes here.
