# endeavouros-dotfiles

Personal EndeavourOS (i3 + Kitty + zsh) configuration. Installed via [dotbot](https://github.com/anishathalye/dotbot) for symlinked configs, plus a small `host-install` script for systemd units that need to live in fixed system paths.

## Installation on a fresh machine

```bash
git clone --recursive https://github.com/<you>/endeavouros-dotfiles ~/git/endeavouros-dotfiles
cd ~/git/endeavouros-dotfiles

./install-packages    # 1. install pacman + AUR packages (uses yay)
gh auth login         # 2. required once for private Imoto Labs repositories
./install             # 3. clone shared handbook and symlink local config
./host-install        # 4. install systemd units (asks for sudo once)
```

Each step is idempotent. Re-run any of them after edits.

## What each step does

### `./install-packages`

Reads `config/packages-repo.txt` and `config/packages-aur.txt` and installs every uncommented package via `pacman` and `yay` respectively. Edit those lists to add/remove packages.

### `./install` (dotbot)

Driven by `install.conf.yaml`. It first ensures the private Imoto Labs engineering handbook exists at `~/git/tech-handbook`, cloning it with GitHub CLI when absent. Existing checkouts are never pulled or modified. A path collision or checkout with the wrong origin stops installation instead of overwriting local data.

Dotbot then creates symlinks from `~` into `config/`, replacing any existing files at the destination (`relink: true`). Categories:

| What | Destination |
|---|---|
| i3 / Kitty / picom / fcitx5 / nvim configs | `~/.config/{i3,kitty,picom,fcitx5,nvim}` |
| zsh, X11, git | `~/.zshrc`, `~/.xprofile`, `~/.Xmodmap`, `~/.gitconfig`, `~/.config/git/ignore` |
| SSH client config | `~/.ssh/config` |
| Hermes/Codex/Claude agent config | `~/.codex/{config.toml,hooks.json,agents/*}`, `~/.agents/skills/*`, `~/.claude/{settings.json,keybindings.json,skills/*}`; Hermes reads `config/agent-skills/` via `skills.external_dirs` |
| User scripts in PATH | `~/bin/{clip-img,claude-notify}`, `~/.local/bin/{agents-dashboard,agents-dashboard-spawn,restore_i3_session,save_i3_session,soundwire-tray,backup-hermes-restic,hermes-notify-hook,dotfiles-autoupdate,services-workflow}` |
| User systemd units | `~/.config/systemd/user/mmo-mouse-workspaces.service`; host install also copies host-specific user units such as `hermes-restic-backup.{service,timer}` |
| Personal/global agent context | `~/.codex/AGENTS.md`, `~/git/AGENTS.md`, `~/git/CLAUDE.md` |
| Shared Imoto Labs engineering guidance | `~/git/tech-handbook` plus its user-scoped setup skill |

The handbook bootstrap invokes its idempotent installer, which exposes the
team-owned `setup-imoto-project` skill at
`~/.agents/skills/setup-imoto-project`. After symlinking, dotbot runs
`git submodule update --init --recursive` to keep `dotbot/` itself current, then
configures Hermes to read shared personal skills from
`~/git/endeavouros-dotfiles/config/agent-skills` when `hermes` is installed.

### `./host-install`

Installs the systemd units that **can't** be symlinked because they need to live at fixed system paths. The unit files are sourced from `config/host/systemd/`.

| Unit | Installed to | Purpose |
|---|---|---|
| `drive-sync.{service,timer}` | `/etc/systemd/system/` | Weekly external drive rsync (Sundays 5am) |
| `paccache.timer` | Vendor unit under `/usr/lib/systemd/system/` | Weekly pacman package-cache cleanup; enablement is replayed by `host-install` |
| `credit-claim.{service,timer}` | `~/.config/systemd/user/` | Daily oneshot, starting at 10:10 and moving 30s later after each success |
| `imoto-wiki-publish.{service,timer}` | `~/.config/systemd/user/` | Periodic Imoto wiki publish job |
| `hermes-restic-backup.{service,timer}` | `~/.config/systemd/user/` | Encrypted restic backup of Hermes state and canonical agent skills |
| `work.target` | `~/.config/systemd/user/` | Automatic group for work services |
| `driver-shield-main-demo.service` | `~/.config/systemd/user/` | Driver Shield MAIN-demo API on port 8010 |
| `hermes-gateway-driver-shield.service` + `.service.d/10-work-target.conf` | `~/.config/systemd/user/` | Constrained Driver Shield Hermes API and optional Slack gateway; the drop-in preserves `work.target` ownership across Hermes' main-unit self-refresh |
| `hermes-gateway.service` and personal daemons | `~/.config/systemd/user/` | Always-on user services under `default.target` |

After install, timers and service groups are reloaded and enabled. The Hermes restic timer is only enabled when `~/.config/restic/hermes-password` exists. Re-run `./host-install` whenever you edit the unit files in `config/host/systemd/`.

## Hermes state and backups

Do **not** Git-track the full `~/.hermes` directory. It contains live state,
sessions, credentials, gateway routing data, caches, and SQLite databases.
Only declarative/rebuildable Hermes pieces belong in this repo, such as shared
skills and helper scripts under `config/agent-skills/`.

Live Hermes state is backed up by the systemd user timer
`hermes-restic-backup.timer`, installed from
`config/host/systemd/user/hermes-restic-backup.timer`. The timer runs
`~/.local/bin/backup-hermes-restic`, sourced from
`config/bin/backup-hermes-restic`, and writes encrypted restic snapshots to:

```text
rclone:Gdrive_howismypielola:HermesRestic
```

The backup includes:

- `~/.hermes`
- `~/git/endeavouros-dotfiles/config/agent-skills`

Intentional excludes keep large/regenerable or noisy paths out of the backup:

- `~/.hermes/hermes-agent`
- `~/.hermes/logs`
- `~/.hermes/audio_cache`
- `~/.hermes/checkpoints`
- `~/.hermes/state-snapshots`

Retention is `7` daily, `4` weekly, and `6` monthly snapshots with prune.
The password file is `~/.config/restic/hermes-password`; store it in a
password manager, because the cloud backup is unrecoverable without it.

Useful checks:

```bash
systemctl --user status hermes-restic-backup.timer --no-pager
systemctl --user status hermes-restic-backup.service --no-pager
journalctl --user -u hermes-restic-backup.service -n 80 --no-pager
backup-hermes-restic
```

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

`config/bin/dotfiles-autoupdate` is the approval-gated scanner for keeping this repo aligned with the live machine. Hermes runs the scanner daily at 19:00 and delivers drift only to the Discord DM `discord:1506284995818553374`. A second Hermes cron job checks that DM every 5 minutes for an approval reply and applies the current snapshot without relying on the active chat context. There is no request queue: each scan replaces the previous snapshot.
The scanner stays silent when the only drift is one or both machine-state files: `config/codex-config.toml` and `config/fcitx5/profile`.
The Discord notification lists every changed repo file with its Git status marker, summarizes other drift, and asks whether to update the repo only when the snapshot has applicable actions. Ignoring it does nothing; the next scan replaces the current unapproved snapshot, so there is no approval queue. `show dotfiles` returns the detailed snapshot. Notify-only drift is reported without an approval prompt.

Commands:

```bash
dotfiles-autoupdate scan          # read-only; prints nothing when there are no actionable changes
dotfiles-autoupdate show          # show the current Discord approval snapshot
dotfiles-autoupdate apply         # apply the current snapshot, commit, and push main
dotfiles-autoupdate reject        # clear the current snapshot
dotfiles-autoupdate approvals     # check Discord gateway history for approval replies
```

The scanner tracks high-confidence drift only:

- repo working-tree changes, excluding the machine-state-only Codex and Fcitx files above
- copied host systemd unit drift between `config/host/systemd/` and the live unit locations
- dotbot link health from `install.conf.yaml`
- package drift between package manifests and live installs. Extra-package drift is
  based on explicitly installed packages; missing-package drift is based on whether
  manifest packages are installed at all, including dependencies.

Native packages that are intentionally explicit on this host but should not be
portable install targets live in `config/host/packages-extra-native-baseline.txt`.
This keeps EndeavourOS/bootstrap packages out of daily drift alerts while still
surfacing newly explicit native packages that need a keep/remove decision.

Package drift creates a notification even when it is the only drift. Extra native packages are added to `config/packages-repo.txt`; extra AUR/foreign packages are added to `config/packages-aur.txt` after Discord approval. Missing packages remain report-only, are not installed by the scanner, and do not produce an approval prompt by themselves. Reply `approve dotfiles` only when the notification asks to update the repo; any other reply does nothing. The apply step commits and pushes the current snapshot directly to `main`, but refuses to continue unless the repo is checked out to the scanned `main` branch and the HEAD, `origin`, live unit hashes, and content-fingerprinted working tree still match the scan. Snapshots with package-manifest additions also require the installed package state to match. A successful apply verifies that the local repo is clean on `main` after the push.

If the local commit succeeds but `git push` fails, the snapshot retains that
exact commit and the approval monitor retries only the push. Daily scans do not
replace pending push recovery, and a retry never creates a second commit.

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
- **Credit-claim**: drop the bearer token at `~/.config/credit-claim/token` and the target URL at `~/.config/credit-claim/api_url` (the script reads both from there). See `config/host/credit-claim/README.md`.
- **Jellyfin**: data lives at `/opt/jellyfin/{config,cache}` and media at `/mnt/Main/Videos/`. Start with `cd config/host/jellyfin && docker compose up -d`.
- **Laptop battery indicator**: uncomment the `[battery]` block in `config/i3/i3blocks.conf` (~line 144) — requires `acpi`.
