# endeavouros-dotfiles

Personal EndeavourOS (i3 + Kitty + zsh) configuration. Installed via [dotbot](https://github.com/anishathalye/dotbot) for user-owned symlinked configs, plus a small `host-install` script for configuration that needs to live in fixed system paths.

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

Driven by `install.conf.yaml`. It first ensures the private Imoto Labs
engineering handbook exists at `~/git/tech-handbook`, cloning it with GitHub CLI
when absent. Existing checkouts are never pulled or modified. The bootstrap
checks the remote default branch and warns when the local checkout is behind or
its freshness cannot be determined. A path collision or checkout with the wrong
origin stops installation instead of overwriting local data.

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
| Shared Imoto Labs engineering guidance | `~/git/tech-handbook` plus its user-scoped team skills |

The handbook bootstrap invokes its idempotent installer, which exposes every
team-owned handbook skill under `~/.agents/skills/`. After symlinking, dotbot
runs `git submodule update --init --recursive` to keep `dotbot/` itself current,
then configures Hermes to read shared personal skills from
`~/git/endeavouros-dotfiles/config/agent-skills` when `hermes` is installed.

### `./host-install`

Installs configuration that needs root access or fixed system paths. Systemd unit files are sourced from `config/host/systemd/`; the Brave managed policy is linked from `config/brave/policies/managed/brave.json`.

| Configuration | Installed to | Purpose |
|---|---|---|
| Brave managed policy | `/etc/brave/policies/managed/brave.json` | Replays the browser debloat policy |

| Unit | Installed to | Purpose |
|---|---|---|
| `drive-sync.{service,timer}` | `/etc/systemd/system/` | Weekly external drive rsync (Sundays 5am) |
| `paccache.timer` | Vendor unit under `/usr/lib/systemd/system/` | Weekly pacman package-cache cleanup; enablement is replayed by `host-install` |
| `credit-claim.{service,timer}` | `~/.config/systemd/user/` | Daily oneshot, starting at 10:10 and moving 30s later after each success |
| `credit-claim-notify.{service,timer}` | `~/.config/systemd/user/` | Hermes Discord failure delivery with 15-minute pending retries |
| `imoto-wiki-publish.{service,timer}` | `~/.config/systemd/user/` | Periodic Imoto wiki publish job |
| `desktop-session-save.{service,timer}` | `~/.config/systemd/user/` | Save all project Kitty workspaces and exact Codex conversations every five minutes |
| `desktop-session-shutdown.service` | `~/.config/systemd/user/` | Capture before logind shutdown/reboot while the graphical session is still alive |
| `hermes-restic-backup.{service,timer}` | `~/.config/systemd/user/` | Encrypted restic backup of Hermes state and canonical agent skills |
| `work.target` | `~/.config/systemd/user/` | Automatic group for work services |
| `driver-shield-main-demo.service` | `~/.config/systemd/user/` | Driver Shield MAIN-demo API on port 8010 |
| `hermes-gateway-driver-shield.service` + `.service.d/10-work-target.conf` | `~/.config/systemd/user/` | Constrained Driver Shield Hermes API and optional Slack gateway; the drop-in preserves `work.target` ownership across Hermes' main-unit self-refresh |
| `hermes-gateway.service` and personal daemons | `~/.config/systemd/user/` | Always-on user services under `default.target` |

After install, timers and service groups are reloaded and enabled. The Hermes restic timer is only enabled when `~/.config/restic/hermes-password` exists. Re-run `./host-install` whenever you edit the unit files in `config/host/systemd/`.

## Whole-desktop session recovery

`save_i3_session.sh` and `restore_i3_session.sh` are compatibility entry points
for `desktop-session`. One startup path coordinates ordinary i3 applications
with the separately owned project windows. The five-minute timer saves only
projects; full-desktop saves run manually and before shutdown, reboot or logout. The earlier
project-only timer is disabled by `host-install`.

- **Automatic:** save all projects every five minutes; restore on graphical login after boot.
  Background saves use nice level 19, idle I/O scheduling and a CPU quota of
  25% of one core for the save service and its children. Manual and shutdown
  saves are not throttled. Work requested from existing Kitty/i3 processes is
  outside that quota.
  Restarting i3 in place preserves running windows and does not relaunch apps.
- **Manual:** Alt+Y → **[ save entire desktop ]**, or the power menu's
  **Save session now**, or `save_i3_session.sh`.
- **Confirmation:** manual saves emit one final notification with timestamp,
  workspace/window counts, and project/Codex counts. It appears only after the
  complete desktop generation is published. Failures say what failed and leave
  the preceding complete desktop snapshot available; the project component may
  have saved a newer independent snapshot before an ordinary capture failed.
- **Status:** Alt+Y → **[ session save status ]**, the power menu's
  **Session save status**, or `desktop-session status`. Status includes the last
  complete desktop snapshot, latest project-save result (including deferrals),
  last-attempt failure if any, and incomplete restore state. A committed project
  save clears an earlier attempt's error without advancing the desktop snapshot.
- **Power menu:** reboot, shutdown and logout all save first and abort if saving
  fails. The old separate Save & Shutdown choice is no longer needed.
- **Other reboot/shutdown requests:** `desktop-session-shutdown.service` holds a
  logind delay inhibitor and requests a final save on `PrepareForShutdown`.
  The host's delay budget is five seconds; if saving fails or exceeds the budget,
  the previous complete snapshot remains. Forced shutdown and power loss cannot
  be intercepted. Autosaving is frozen once shutdown begins, preventing closing
  applications from replacing the snapshot with a partly dismantled desktop.
  Windows changing during capture cause it to retain the previous snapshot.
  External shutdown can close apps before capture starts; use the power menu
  to ensure the desktop is saved before requesting shutdown.

Desktop snapshots are private files under `~/.local/state/desktop-session/`
(or `$XDG_STATE_HOME`); ten complete generations are retained. Ordinary workspace
names are discovered dynamically, including renamed workspaces. Reserved project
workspaces and scratchpad windows are excluded from ordinary restoration.
`i3-resurrect` supplies capture data; restoration uses checked i3 layout commands,
safe argv launches, stable placeholder marks, and verifies that application
windows appear. Existing matching windows are adopted, including autostarted
applications. No parallel per-workspace launch races or unchecked success echoes.
Ordinary Kitty windows also retain their native tabs and Codex conversations.
Obsidian's old and new window identities are both recognized after upgrades;
restore adapts a private layout copy while preserving the original snapshot.
If no project windows are open, ordinary desktop capture still succeeds and
explicitly reports that the prior project snapshot was retained unchanged.

An incomplete restore pauses automatic project saves and gives an error naming
missing applications. Fix the missing app and run `desktop-session restore` to
retry. Completed windows/layouts are not relaunched. Project restoration still
runs even if an ordinary app cannot open. Browser tabs, documents and editor
buffers rely on each application's own session recovery; this saves window
placement and launch state, not process memory or unsaved content.

The shutdown listener uses the installed `python-dbus` and `python-gobject`
packages. Protocol references: [logind inhibitors](https://systemd.io/INHIBITOR_LOCKS/),
[i3 layout restoration](https://i3wm.org/docs/layout-saving.html), and
[i3-resurrect capture](https://github.com/JonnyHaystack/i3-resurrect).

## Project workspace recovery

`project-switch` saves all Kitty windows on its project workspaces (6, 7 and
hidden `_proj_*` workspaces), including inactive projects, tabs, split layouts,
working directories and exact running Codex conversation IDs. Other workspaces
are captured and restored by the whole-desktop coordinator described above.

- Autosave: projects only, every five minutes via `desktop-session-save.timer` (up to five seconds
  timer slack). It starts saving only after i3 startup/restore completes.
  If a foreground Codex has not opened a conversation file yet, autosave defers
  the entire capture, retains the previous snapshot, and retries on the next
  timer tick without a failure notification. Send the first prompt or close an
  unused Codex tab to allow capture. Ambiguous or invalid conversation files
  remain errors; manual and shutdown saves still reject incomplete captures.
- Restore: i3 runs `restore_i3_session.sh` on login, coordinating ordinary
  applications and `project-switch startup`. Saved projects are restored before
  default bootstrap. Repeated startup in the same i3 session leaves live
  windows alone, including windows intentionally closed since startup.
- Manual save: **Alt+Y → [ save all projects ]**, or `project-switch save`.
- Status: `project-switch status`.
- Retry an interrupted restore: `project-switch restore`. Already launched
  windows are recognized by stable classes, including interruption before i3
  marks were assigned.
- The power menu saves the entire desktop before reboot, shutdown and logout.
  A failed save aborts the requested action with a visible error.

Snapshots live under `~/.local/state/project-switch/` (or `$XDG_STATE_HOME`),
outside Git. A complete generation is published atomically through `current.json`;
the ten most recent generations are retained. Failed capture, unavailable Kitty,
an empty desktop, and incomplete restoration do not replace the last complete
snapshot. Save/restore and project mutations share the same lock. The five-minute
interval means a sudden power loss can lose workspace changes since the last
successful save. Check the timer's failures with:

```bash
systemctl --user status desktop-session-save.timer
journalctl --user -u desktop-session-save.service -n 30
```

Codex identity is taken from that process's open main conversation file; subagent
files are excluded. An ambiguous or not-yet-created conversation causes the save
to fail and retry on the next timer tick, rather than guessing by directory.
Restored Codex tabs run `codex resume <id>` without sending a prompt. Codex's own
conversation files must still exist; workspace snapshots are not a backup of
`~/.codex`.

Shell tabs reopen in their saved directories. The agents dashboard also reopens;
other foreground commands, editors and servers are not automatically replayed.
Terminal scrollback, unsaved editor buffers and running processes are not
preserved. If a saved directory no longer exists, the pane explains the problem
and opens in the home directory. Leaving resumed Codex returns to a shell.

After a fresh install, run `./host-install` to install and enable the timer.
For a focused unit update:

```bash
./host-install --user-unit desktop-session-save.service desktop-session-save.timer desktop-session-shutdown.service
systemctl --user enable --now desktop-session-save.timer desktop-session-shutdown.service
```

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
- **Credit-claim**: runtime credentials, endpoint, page URL, dedicated headless Chrome profile, and private notification state stay under `~/.config/credit-claim/`. On an authentication rejection, the service refreshes the JWT once and retries once. Final failures are delivered to the existing Hermes Discord DM and retried every 15 minutes until confirmed. See `config/host/credit-claim/README.md`.
- **Jellyfin**: data lives at `/opt/jellyfin/{config,cache}` and media at `/mnt/Main/Videos/`. Start with `cd config/host/jellyfin && docker compose up -d`.
- **Calibre + Calibre-Web**: native Calibre owns `/mnt/Main/ebooks/calibre-library`; source files and Japanese EPUB repair backups remain under `/mnt/Main/ebooks/archive/`. The tracked Compose file is linked to `~/services/calibre-web/compose.yaml`, and persistent web state lives under `~/services/calibre-web/config/`. Run `repair-japanese-epubs` after importing Japanese EPUBs and follow `config/host/calibre-web/README.md` for repairs and service lifecycle.
- **Laptop battery indicator**: uncomment the `[battery]` block in `config/i3/i3blocks.conf` (~line 144) — requires `acpi`.
