---
name: dotfiles-autoupdate
description: Handle Discord approval replies for the EndeavourOS dotfiles scheduled host scan. Use when the user says approve, show, or reject dotfiles.
---

# Dotfiles Autoupdate Approval Flow

Use this skill when the user asks from Discord or CLI to approve, show, or reject the current dotfiles autoupdate snapshot, especially messages like:

- `approve dotfiles`
- `show dotfiles`
- `reject dotfiles`


## Repository and command

- Repo: `/home/howis/git/endeavouros-dotfiles`
- Command: `/home/howis/git/endeavouros-dotfiles/config/bin/dotfiles-autoupdate`
- Current snapshot: `~/.cache/dotfiles-autoupdate/pending.json`

## Show

For `show dotfiles`:

1. Run:
   ```bash
   /home/howis/git/endeavouros-dotfiles/config/bin/dotfiles-autoupdate show
   ```
2. Return the detailed snapshot output to the user.
3. Do not commit or push.

## Reject

For `reject dotfiles`:

1. Run:
   ```bash
   /home/howis/git/endeavouros-dotfiles/config/bin/dotfiles-autoupdate reject
   ```
2. Tell the user the current snapshot was cleared.
3. Do not commit or push.

## Approve

For `approve dotfiles`:

1. Run:
   ```bash
   /home/howis/git/endeavouros-dotfiles/config/bin/dotfiles-autoupdate show
   ```
2. Confirm the current snapshot exists and the summary matches the user's approval.
3. Run:
   ```bash
   /home/howis/git/endeavouros-dotfiles/config/bin/dotfiles-autoupdate apply
   ```
4. If apply succeeds, report the changed paths, commit SHA, and push result.
5. If apply fails, report the exact blocker and do not retry destructive steps unless the user approves a revised action.

## Automated approval monitor

Hermes runs `dotfiles-autoupdate approvals` every 5 minutes via a script-only cron job. It reads `~/.hermes/logs/gateway.log` for Discord DM approvals and applies the current snapshot when either:

- the message is exactly `approve dotfiles`.

The snapshot is only eligible for an approval message received after the scan. Each new scan replaces the previous snapshot, so there is no queue. Because cron deliveries are not mirrored into the active Discord gateway session, the approval monitor is the durable path.

The daily Discord notification is deliberately concise. It says when the repo
is behind the current machine, lists every changed repo file with its Git status
marker, and summarizes other actions. Ignoring it does nothing; a later scan
replaces the current unapproved snapshot, so there is no approval queue.
Notify-only drift must not ask for approval because the apply path cannot change
it.

## Safety rules

- Apply only the current snapshot shown by the scan.
- Package-only drift can create a snapshot. Extra native packages may be approved into `config/packages-repo.txt`; extra AUR/foreign packages may be approved into `config/packages-aur.txt`.
- `config/codex-config.toml` and `config/fcitx5/profile` are machine state; the scan job intentionally stays silent and creates no snapshot when either or both are the only drift.
- Missing package drift is notify-only. Do not install missing packages from this flow.
- Do not run `./install` or `./host-install` automatically after approval. Mention them as follow-up only if needed.
- If the command reports that HEAD, branch, `origin`, live unit hashes, or repo
  contents changed since scan, stop and ask for a fresh scan. Snapshots that
  add package-manifest entries also require the installed package state to
  match. Apply only from `main`; a successful apply commits, pushes directly
  to `origin/main`, and verifies the local repo is clean.
- If the commit succeeds but the push fails, the current snapshot retains that
  exact local commit and the approval monitor retries only the push. It must
  not create a second commit or allow a daily scan to replace the retry state.
- Deliver summaries in the same Discord DM/channel where the approval came from unless the user says otherwise.
