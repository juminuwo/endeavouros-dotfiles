---
name: dotfiles-autoupdate
description: Handle Discord approval replies for the EndeavourOS dotfiles scheduled host scan. Use when the user says approve/show/reject dotfiles <id>.
---

# Dotfiles Autoupdate Approval Flow

Use this skill when the user asks from Discord or CLI to approve, show, or reject a dotfiles autoupdate request, especially messages like:

- `approve dotfiles <request-id>`
- `show dotfiles <request-id>`
- `reject dotfiles <request-id>`
- bare `Approved` in Discord when exactly one pending request exists; the `dotfiles-autoupdate-approvals` Hermes cron job handles this without relying on the active chat context

## Repository and command

- Repo: `/home/howis/git/endeavouros-dotfiles`
- Command: `/home/howis/git/endeavouros-dotfiles/config/bin/dotfiles-autoupdate`
- Pending requests: `~/.cache/dotfiles-autoupdate/pending/<request-id>.json`

## Show

For `show dotfiles <request-id>`:

1. Run:
   ```bash
   /home/howis/git/endeavouros-dotfiles/config/bin/dotfiles-autoupdate show <request-id>
   ```
2. Return the output to the user.
3. Do not commit or push.

## Reject

For `reject dotfiles <request-id>`:

1. Run:
   ```bash
   /home/howis/git/endeavouros-dotfiles/config/bin/dotfiles-autoupdate reject <request-id>
   ```
2. Tell the user the request was rejected.
3. Do not commit or push.

## Approve

For `approve dotfiles <request-id>`:

1. Run:
   ```bash
   /home/howis/git/endeavouros-dotfiles/config/bin/dotfiles-autoupdate show <request-id>
   ```
2. Confirm the request id exists and the summary matches the user's approval.
3. Run:
   ```bash
   /home/howis/git/endeavouros-dotfiles/config/bin/dotfiles-autoupdate apply <request-id>
   ```
4. If apply succeeds, report the changed paths, commit SHA, and push result.
5. If apply fails, report the exact blocker and do not retry destructive steps unless the user approves a revised action.

## Automated approval monitor

Hermes also runs `dotfiles-autoupdate approvals` every 5 minutes via a script-only cron job. It reads `~/.hermes/logs/gateway.log` for Discord DM approvals and applies one pending request when either:

- the message is `approve dotfiles <request-id>`, or
- the message is bare `Approved` / `approve` and exactly one pending dotfiles request exists.

Because cron deliveries are not mirrored into the active Discord gateway session, do not assume a plain `Approved` message will have the scan summary in LLM context. The approval monitor is the durable path for that case.

## Safety rules

- Apply only the request id the user approved.
- Do not auto-classify package drift. Package drift is report-only unless the user gives explicit package additions/removals.
- Do not run `./install` or `./host-install` automatically after approval. Mention them as follow-up only if needed.
- If the command reports that HEAD, branch, live unit hashes, or repo status changed since scan, stop and ask for a fresh scan.
- Deliver summaries in the same Discord DM/channel where the approval came from unless the user says otherwise.
