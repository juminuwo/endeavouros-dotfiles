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
- **`Kanban: new` with no quoted title**: shlex-fail. Always quote: `Kanban: new "Some title" #tags`.
- **Card already in target column**: still fine — trailer becomes a commit-link append, no move.
- **Staged changes span multiple cards**: emit multiple `Kanban:` trailers, one per card.
- **User typed a trailer in their staged commit message** (via editor): don't add a duplicate. Inspect their draft first.

For sync.py internals, full failure modes, post-commit hook, and on-disk conventions, see `REFERENCE.md`. For moving to a new machine, see `PORTABILITY.md`.
