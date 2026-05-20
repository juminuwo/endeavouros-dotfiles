---
name: kanban-sync
description: Sync the Imoto Labs Obsidian Kanban board with git commit history, OR compose a git commit that includes a `Kanban:` trailer and then sync. Triggers on "sync the kanban", "update the kanban", "update the board", `/kanban-sync`, "commit and update kanban", "commit with kanban trailer", `/kanban-sync commit`, or any commit request where the user mentions the kanban / board. Two modes — sync-only and commit-then-sync. (For read-only planning queries — "what's next?", `/kanban`, "tell me about DSH-009" — delegate to the `kanban-planner` agent instead, do NOT load this skill.)
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Kanban sync

Reconciles the Obsidian Kanban board at `~/Documents/online-personal/Imoto Labs/Kanban.md` with git commit history across tracked Imoto Labs repos. Single source of truth for "what's done": commits with `Kanban:` trailers.

For deeper detail, lazy-load these sibling docs as needed (don't pre-load):
- `REFERENCE.md` — what `sync.py` does, on-disk card format, edge cases, failure modes, conventions, post-commit hook
- `PORTABILITY.md` — moving to a new machine

## Trailer format

Every commit that should affect the board carries one or more `Kanban:` trailer lines:

```
Kanban: DSH-042              # link this commit to card DSH-042, no column move
Kanban: DSH-042 done         # move card to Done, link commit, stamp @{date}
Kanban: DSH-042 progress     # move card to In Progress
Kanban: DSH-042 blocked      # move card to Blocked / Waiting
Kanban: DSH-042 backlog      # move back to Backlog
Kanban: DSH-042 next         # move to Up Next
Kanban: new "Title here" #driver-shield #pilot #hardware #p0 done    # create new card
```

Commits without a `Kanban:` trailer are ignored — that's the noise filter.

For `Kanban: new`, the project tag (`#driver-shield`, `#business-scout`, etc.) determines the ID prefix. If omitted, the script infers from the originating repo via `config.json`.

## Mode picker

| User says… | Mode |
|---|---|
| "sync the kanban", "update the board", `/kanban-sync` | **Mode 1** — sync only |
| "check latest merges against the board", "forgot to review merges", "audit recent merges vs kanban" | **Mode 1b** — merge/board audit, then patch board if asked |
| "commit and update kanban", "commit with kanban trailer", `/kanban-sync commit` | **Mode 2** — commit + sync |
| "what's next?", `/kanban`, "kanban status", "tell me about DSH-009" | **Delegate to `kanban-planner` agent** — read-only, returns a dashboard |
| "commit this" (no kanban mention) | NOT this skill — standard commit flow |
| Question about how trailers work | Answer from this doc; don't run anything |

If ambiguous, ask. Better to clarify than to commit something the user didn't intend.

## Mode 1 — sync only

User said "sync the kanban", "update the board", `/kanban-sync`. They've already committed and want the board to catch up. Just run:

```bash
python3 ~/git/endeavouros-dotfiles/config/agent-skills/kanban-sync/scripts/sync.py
```

Pure stdlib — no Python deps needed.

Useful flags:
- `--dry-run` — print what would change without touching files
- `--repo <name>` — only sync that one project (matches keys in `config.json`)
- `--no-archive` — skip the 30-day archive sweep this run
- `--assign-ids` — one-shot: walk existing cards and assign IDs to any without one

Report back: cards moved, commits linked, cards archived, WIP warning if any.

## Mode 1b — merge/board audit

Use this when the user asks whether recent merges were missed, forgot to review merged PRs against the board, or asks for a `/kanban-sync` board audit rather than a mechanical sync.

1. Fetch first, then compare the remote default branch, not just the local branch. A local branch may be behind, and `sync.py --dry-run` can report "no new commits" only because it scans the local checkout. Discover the default branch with `git symbolic-ref refs/remotes/origin/HEAD` or inspect `origin/master`/`origin/main`.
2. Inspect recent merged PRs with GitHub (`gh pr list --state merged --limit N --json number,title,mergedAt,headRefName,mergeCommit,commits,files,url`) and compare against the board's card text + commit links.
3. Treat commits with `Kanban:` trailers as strong evidence, but also flag merged PRs without trailers whose title/body mentions a card ID or whose files clearly belong to an active/recent card.
4. Report the exact card actions: move column, add date, add commit links, or leave untracked. If the user says to apply the recommendations, patch the board directly rather than running sync unless the missing trailers are present and local history is up to date.
5. When adding commit links manually, verify the full SHA before writing the URL. Do not invent full hashes from abbreviated hashes or tool output snippets.
6. After patching, verify each touched card appears in the intended column exactly once and that expected short hashes + full commit URLs are present. Watch for duplicate `Commits:` lines when replacing an existing single-link line.

## Mode 2 — commit + sync

User said "commit and update kanban", "commit with kanban trailer", `/kanban-sync commit`. Compose the trailer, commit, then sync.

### Step 1 — inspect what's staged

```bash
git status --short
git diff --cached --stat
git diff --cached
git log -3 --oneline
```

If nothing is staged, ask whether to `git add -A` or stage specific files. Don't auto-stage — risks committing unrelated junk.

### Step 2 — identify candidate card(s)

Read the kanban (`config.json` → `kanban_path`). For each non-Done card whose project tag matches the **current repo's project key** (look up cwd's repo in `config.json`):

- Card title or scratchpad-link section overlaps semantically with what's staged → propose linking that ID.
- Multiple match → list, ask the user to pick.
- None match → propose `Kanban: new "<title>" #<project-tag> [#additional-tags] [<column>]`.

For ambiguous cases, propose your best guess but show the alternatives.

### Step 3 — propose state suffix

| Diff looks like… | Suffix |
|---|---|
| Final fix / feature complete / test passing / closes a thread | `done` |
| Mid-flight progress, partial work | `progress` |
| Just a doc update or scratchpad addendum | (no suffix — link only) |
| Reverts / unblocks something | the inverse move |
| Discovery / investigation only, no card exists yet | `new "..." backlog` or skip the trailer |

If unclear, ask. The suffix is a deliberate signal — getting it wrong means the board lies.

### Step 4 — compose the commit message

Format (HEREDOC, mirrors the project's existing style — short subject, body explains *why*, trailer at bottom):

```
<subject under 70 chars>

<1-3 sentences on the why, optional>

Kanban: <ID> [<state>]
[Kanban: <other-ID> <state>]    # multiple trailers if multiple cards advance
```

Show the proposed message and ask for confirmation BEFORE running `git commit`. The user can approve, edit the trailer or body, or cancel.

### Step 5 — commit

```bash
git commit -m "$(cat <<'EOF'
<subject>

<body>

Kanban: DSH-NNN done
EOF
)"
```

Follow normal commit safety rules — never `--no-verify`, never bypass hooks, never amend unless explicitly asked.

### Step 6 — run sync

```bash
python3 ~/git/endeavouros-dotfiles/config/agent-skills/kanban-sync/scripts/sync.py
```

Report back: what got committed, the SHA, the cards that moved, any WIP warning.

### Step 7 — never push automatically

The user pushes when they're ready. Don't `git push` as part of this skill.

## Edge cases (commit composition)

- **Repo not in config**: warn, ask if they want to add it. Don't compose a trailer for an untracked project.
- **User wants to commit without touching the board**: respect that — skip the trailer, normal commit, no sync.
- **Work is already committed but missing/needs trailers**: if `git status --branch --short` shows the branch ahead of remote and the latest commit is clearly the just-finished work, inspect `git log -1 --format='%H%n%B'` and `git show --stat --format=fuller HEAD`. With explicit user intent to close/create board cards, amend the unpushed commit to add/update `Kanban:` trailers, then run sync. Do not create a second empty/docs-only commit just to move the board. If the commit is already pushed, do not rewrite it unless the user explicitly asks for a force-push-safe amend; otherwise add a follow-up commit with the trailers.
- **User explicitly asks to push after the Kanban commit/amend**: pushing is allowed because the user asked. Still verify `git status --branch --short` and push only the current branch to its configured remote (for example `git push origin master`), then verify the remote SHA. The default rule remains: never push automatically as part of `/kanban-sync` when the user did not request it.
- **`Kanban: new` with no quoted title**: shlex-fail. Always quote: `Kanban: new "Some title" #tags`.
- **Card already in target column**: still fine — trailer becomes a commit-link append, no move.
- **Follow-up commits for an active Kanban card**: if the current work is already tied to a card created/moved earlier in the session, do not make trailer-less follow-up commits even for docs or benchmark notes. Add a link-only trailer such as `Kanban: DSH-049` so `sync.py` appends the commit to the card. If the commit was already pushed without a trailer, do not rewrite public history; manually patch the card's `Commits:` line after verifying the full SHA and URL.
- **Staged changes span multiple cards**: emit multiple `Kanban:` trailers, one per card.
- **User typed a trailer in their staged commit message** (via editor): don't add a duplicate. Inspect their draft first.

For sync.py internals, full failure modes, post-commit hook, and on-disk conventions, see `REFERENCE.md`. For moving to a new machine, see `PORTABILITY.md`.
