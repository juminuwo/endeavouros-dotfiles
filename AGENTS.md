# endeavouros-dotfiles — system source of truth

This repo is the source of truth for system config (i3, Kitty, zsh, Hermes, Codex CLI, legacy Claude Code, `~/bin` scripts, packages, systemd units). `~/.config/i3/config`, `~/.codex/config.toml`, `~/.claude/settings.json`, `~/bin/*`, `~/git/AGENTS.md`, `~/git/CLAUDE.md` etc. are **symlinks managed by dotbot** — edit the file under `config/` in the repo, never the symlink target.

## Three install entry points (idempotent, re-runnable)

- `./install` — dotbot symlinker, driven by `install.conf.yaml`
- `./install-packages` — installs portable packages in `config/packages-{repo,aur}.txt` (works on any machine)
- `./host-install` — installs hardware-specific packages (`config/host/packages-host-repo.txt`) and systemd units from `config/host/systemd/`

## When adding something, do it in the repo so a fresh machine gets it

| Adding... | Put the file at... | Then... |
|---|---|---|
| A config file | `config/<whatever>` | add a `link:` entry in `install.conf.yaml`, run `./install` |
| A `~/bin/` or `~/.local/bin/` script | `config/<name>` (or `config/bin/<name>` for `~/.local/bin`) | add `link:` entry, `chmod +x` the source, run `./install` |
| A portable dependency | `config/packages-repo.txt` (pacman) or `config/packages-aur.txt` (AUR). Decide with `pacman -Si <pkg>`: `Repository: extra/core/multilib` → repo file; `Repository: aur` (or not found) → AUR file. | run `./install-packages` |
| A hardware-specific package (NVIDIA, Intel ucode, etc.) | `config/host/packages-host-repo.txt` | run `./host-install` |
| A systemd unit | `config/host/systemd/{system,user}/` | extend `host-install`, re-run it |
| A shared agent skill | `config/agent-skills/<name>/SKILL.md` | Codex/Claude are linked via `install.conf.yaml`; Hermes reads the whole directory through `skills.external_dirs`. Run `./install`, then restart agents or reload skills. |

## Conventions

- **`config/`** = portable, symlinked. **`config/host/`** = machine-specific (drive UUIDs, hardware-tied services), not symlinked.
- After editing a config that's already symlinked, no install step is needed — the live file *is* the repo file.
- After adding/removing a `link:` entry, run `./install` to apply.
- Reload i3 after touching `config/i3/config`: `i3-msg reload`.
- After editing a script driven by a systemd unit, restart the unit: `systemctl --user restart <name>` (e.g. `mmo-mouse-workspaces.service`). The symlink edit is live in the file but the daemon has cached state / a running interpreter.
- After editing an i3blocks block script (`config/bin/i3blocks-*`), signal i3blocks to re-run the block: `pkill -RTMIN+<N> i3blocks` where `<N>` matches the block's `signal=` line in `config/i3/i3blocks.conf`. Without this, the bar shows cached output until its `interval` ticks.
- **Workspaces 6 and 7 are reserved for project-switch** (kitty pairs managed via i3 marks + workspace renames). Nothing else should spawn windows there — including i3-resurrect, scratchpad rules, or `for_window` placements. Adding such a rule collides with project-switch's mark/rename state and silently breaks project switching.
- Don't hand-write files into `~` when a dotbot-managed equivalent exists — edit the source under `config/` instead.

## Shared agent skills

- `config/agent-skills/` is the canonical source for personal workflow/domain skills shared by Hermes, Codex, and legacy Claude Code.
- Codex uses `~/.agents/skills/<name>` symlinks; legacy Claude Code uses `~/.claude/skills/<name>` symlinks; Hermes reads `config/agent-skills/` via `skills.external_dirs`.
- Keep skill instructions agent-neutral where possible. Prefer canonical repo paths over `~/.claude/skills/...` paths when referencing bundled scripts or references.
- When adding a new skill, add the source directory under `config/agent-skills/`, add Codex/Claude symlinks in `install.conf.yaml`, run `./install`, then verify with the target agent's skill list/reload command.

## AGENTS.md and CLAUDE.md compatibility

- **`config/AGENTS.md`** — symlinked to both `~/git/AGENTS.md` and `~/git/CLAUDE.md` so Hermes/Codex and Claude-compatible agents inherit the same cross-project context. Keep it lean; cross-project content only.
- **`AGENTS.md`** (this file) — only loaded when cwd is inside this repo. Dotfiles-specific guidance goes here.
