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
| User scripts in PATH | `~/bin/{clip-img,claude-notify}`, `~/.local/bin/{agents-dashboard,agents-dashboard-spawn,restore_i3_session,save_i3_session,soundwire-tray,backup-hermes-restic,hermes-notify-hook,dotfiles-autoupdate,services-workflow}` |
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
| `work.target` | `~/.config/systemd/user/` | Automatic group for work services |
| `driver-shield-main-demo.service` | `~/.config/systemd/user/` | Driver Shield MAIN-demo API on port 8010 |
| `hermes-gateway-driver-shield-slack.service` | `~/.config/systemd/user/` | Driver Shield Slack Hermes gateway, grouped under `work.target` |
| `hermes-gateway.service` and personal daemons | `~/.config/systemd/user/` | Always-on user services under `default.target` |

After install, timers and service groups are reloaded and enabled. The Hermes restic timer is only enabled when `~/.config/restic/hermes-password` exists. Re-run `./host-install` whenever you edit the unit files in `config/host/systemd/`.

## User service workflow

User services are grouped by intent:

| Group | Target | Rule |
|---|---|---|
| Personal/default | `default.target` | Small background services that should be available on this machine whenever the user manager is running |
| Work | `work.target` | Work daemons and project APIs; `work.target` is enabled by `default.target` on this host |
| Timers | `timers.target` | Scheduled jobs, even when they support work projects |

Common commands:

```bash
services-workflow audit
services-workflow work status
services-workflow work stop
services-workflow work start
services-workflow work logs
services-workflow failed
```

Add a work service with:

```ini
[Unit]
PartOf=work.target

[Install]
WantedBy=work.target
```

Add an always-on personal service with:

```ini
[Install]
WantedBy=default.target
```

## Scheduled dotfiles autoupdate

`config/bin/dotfiles-autoupdate` is the approval-gated scanner for keeping this repo aligned with the live machine. Hermes runs the scanner daily at 19:00 and delivers output only to the Discord DM target `discord:isitokaymimi`. A second Hermes cron job checks that DM every 5 minutes for approval replies and applies the pending request without relying on the active chat context.

Commands:

```bash
dotfiles-autoupdate scan          # read-only; prints nothing when there are no actionable changes
dotfiles-autoupdate show <id>     # show a pending Discord approval request
dotfiles-autoupdate apply <id>    # apply exactly the approved request, commit, and push
dotfiles-autoupdate reject <id>   # reject a pending request
dotfiles-autoupdate approvals     # check Discord gateway history for approval replies
```

The scanner tracks high-confidence drift only:

- repo working-tree changes such as `config/codex-config.toml`
- copied host systemd unit drift between `config/host/systemd/` and the live unit locations
- dotbot link health from `install.conf.yaml`
- package drift between package manifests and explicit live installs, reported only

Package drift is report-only unless explicitly classified and approved. The apply step refuses to continue if the repo branch, HEAD, live unit hashes, or working-tree state changed after the scan. `approve dotfiles <id>` is preferred, but a bare `Approved` also works when exactly one pending dotfiles request exists.

## Repo layout

```
endeavouros-dotfiles/
├── config/                          # everything dotbot symlinks
│   ├── i3/, nvim/, fcitx5/ ...      # standard application configs
│   ├── agent-skills/, agent-agents/, codex-agents/, claude-alerts/
│   ├── packages-{repo,aur}.txt      # package lists for install-packages
│   ├── bin/                         # scripts → ~/.local/bin/ including dotfiles-autoupdate
│   └── host/                        # machine-specific (NOT symlinked)
│       ├── sync-drives.sh           # called by drive-sync.service
│       ├── credit-claim/claim.sh    # called by credit-claim.service
│       ├── jellyfin/                # docker-compose for Jellyfin
│       ├── change-backup-uuid.sh    # one-off util
│       ├── find-drive-uuids.sh      # one-off util
│       └── systemd/{system,user}/   # unit files installed and enabled by host-install
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
- Adding a new systemd unit: drop it under `config/host/systemd/{system,user}/`, choose `default.target`, `work.target`, or `timers.target`, extend `host-install` if it needs automatic enablement, then re-run it.

## Manual host steps (not automated)

These aren't run by any script — do them once per machine:

- **Drive sync UUIDs**: edit `config/host/sync-drives.sh` and set `MAIN_UUID` / `BACKUP_UUID`. See `config/host/DRIVE-SYNC-SETUP.md`.
- **Credit-claim**: drop the bearer token at `~/.config/credit-claim/token` and the target URL at `~/.config/credit-claim/api_url` (the script reads both from there).
- **Jellyfin**: data lives at `/opt/jellyfin/{config,cache}` and media at `/mnt/Main/Videos/`. Start with `cd config/host/jellyfin && docker compose up -d`.
- **Laptop battery indicator**: uncomment the `[battery]` block in `config/i3/i3blocks.conf` (~line 144) — requires `acpi`.
