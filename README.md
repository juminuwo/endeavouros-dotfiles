# endeavouros-dotfiles

Personal EndeavourOS (i3 + Kitty + zsh) configuration. Installed via [dotbot](https://github.com/anishathalye/dotbot) for symlinked configs, plus a small `host-install` script for systemd units that need to live in fixed system paths.

## Installation on a fresh machine

```bash
git clone --recursive https://github.com/<you>/endeavouros-dotfiles ~/git/endeavouros-dotfiles
cd ~/git/endeavouros-dotfiles

./install-packages    # 1. install pacman + AUR packages (uses yay)
./install             # 2. dotbot — symlink configs and ~/bin/*, ~/.local/bin/* scripts
./host-install        # 3. install systemd units (asks for sudo once)
```

Each step is idempotent. Re-run any of them after edits.

## What each step does

### `./install-packages`

Reads `config/packages-repo.txt` and `config/packages-aur.txt` and installs every uncommented package via `pacman` and `yay` respectively. Edit those lists to add/remove packages.

### `./install` (dotbot)

Driven by `install.conf.yaml`. Creates symlinks from `~` into `config/`, replacing any existing files at the destination (`relink: true`). Categories:

| What | Destination |
|---|---|
| i3 / Kitty / picom / fcitx5 / nvim configs | `~/.config/{i3,kitty,picom,fcitx5,nvim}` |
| zsh, X11, git | `~/.zshrc`, `~/.xprofile`, `~/.Xmodmap`, `~/.gitconfig`, `~/.config/git/ignore` |
| SSH client config | `~/.ssh/config` |
| Hermes/Codex/Claude agent config | `~/.codex/{config.toml,hooks.json,agents/*}`, `~/.agents/skills/*`, `~/.claude/{settings.json,keybindings.json,skills/*}`; Hermes reads `config/agent-skills/` via `skills.external_dirs` |
| User scripts in PATH | `~/bin/{clip-img,claude-notify}`, `~/.local/bin/{agents-dashboard,agents-dashboard-spawn,restore_i3_session,save_i3_session,soundwire-tray,backup-hermes-restic,hermes-notify-hook}` |
| User systemd units | `~/.config/systemd/user/mmo-mouse-workspaces.service`; host install also copies host-specific user units such as `hermes-restic-backup.{service,timer}` |
| Top-level repo agent context | `~/git/AGENTS.md`, `~/git/CLAUDE.md` |

After symlinking, dotbot runs `git submodule update --init --recursive` to keep `dotbot/` itself current, then configures Hermes to read shared skills from `~/git/endeavouros-dotfiles/config/agent-skills` when `hermes` is installed.

### `./host-install`

Installs the systemd units that **can't** be symlinked because they need to live at fixed system paths. The unit files are sourced from `config/host/systemd/`.

| Unit | Installed to | Purpose |
|---|---|---|
| `drive-sync.{service,timer}` | `/etc/systemd/system/` | Weekly external drive rsync (Sundays 5am) |
| `credit-claim.{service,timer}` | `~/.config/systemd/user/` | Daily oneshot, starting at 10:10 and moving 30s later after each success |
| `imoto-wiki-publish.{service,timer}` | `~/.config/systemd/user/` | Periodic Imoto wiki publish job |
| `hermes-restic-backup.{service,timer}` | `~/.config/systemd/user/` | Encrypted restic backup of Hermes state and canonical agent skills |

After install, timers are reloaded and `enable --now`'d. The Hermes restic timer is only enabled when `~/.config/restic/hermes-password` exists. Re-run `./host-install` whenever you edit the unit files in `config/host/systemd/`.

## Repo layout

```
endeavouros-dotfiles/
├── config/                          # everything dotbot symlinks
│   ├── i3/, nvim/, fcitx5/ ...      # standard application configs
│   ├── agent-skills/, agent-agents/, codex-agents/, claude-alerts/
│   ├── packages-{repo,aur}.txt      # package lists for install-packages
│   ├── bin/                         # scripts → ~/.local/bin/
│   └── host/                        # machine-specific (NOT symlinked)
│       ├── sync-drives.sh           # called by drive-sync.service
│       ├── credit-claim/claim.sh    # called by credit-claim.service
│       ├── jellyfin/                # docker-compose for Jellyfin
│       ├── change-backup-uuid.sh    # one-off util
│       ├── find-drive-uuids.sh      # one-off util
│       └── systemd/{system,user}/   # unit files installed by host-install
├── install                          # dotbot wrapper
├── install-packages                 # pacman + yay package installer
├── host-install                     # systemd unit installer (sudo)
└── install.conf.yaml                # dotbot config
```

## Conventions

- **`config/`** = portable configs that work on any EndeavourOS machine. Symlinked.
- **`config/host/`** = machine-specific (drive UUIDs, services tied to local hardware). Copied/referenced by absolute path; not symlinked.
- Adding a new dotfile: drop it under `config/`, add a `link:` entry in `install.conf.yaml`, run `./install`.
- Adding a shared personal skill: add `config/agent-skills/<name>/SKILL.md`, add Codex/Claude symlinks in `install.conf.yaml`, run `./install`, then reload/restart the target agent. Hermes uses the whole parent directory via `skills.external_dirs`.
- Adding a new systemd unit: drop it under `config/host/systemd/{system,user}/`, extend `host-install`, re-run it.

## Manual host steps (not automated)

These aren't run by any script — do them once per machine:

- **Drive sync UUIDs**: edit `config/host/sync-drives.sh` and set `MAIN_UUID` / `BACKUP_UUID`. See `config/host/DRIVE-SYNC-SETUP.md`.
- **Credit-claim**: drop the bearer token at `~/.config/credit-claim/token` and the target URL at `~/.config/credit-claim/api_url` (the script reads both from there).
- **Jellyfin**: data lives at `/opt/jellyfin/{config,cache}` and media at `/mnt/Main/Videos/`. Start with `cd config/host/jellyfin && docker compose up -d`.
- **Laptop battery indicator**: uncomment the `[battery]` block in `config/i3/i3blocks.conf` (~line 144) — requires `acpi`.
