---
name: kanban-sync
description: Sync the Imoto Labs Obsidian Kanban board with git commit history, OR compose a git commit that includes a `Kanban:` trailer and then sync. Triggers on: "sync the kanban", "update the kanban", "update the board", `/kanban-sync`, "commit and update kanban", "commit with kanban trailer", `/kanban-sync commit`, or any commit request where the user mentions the kanban / board. Two modes — sync-only (default) and commit-then-sync (when the user wants both in one step).
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Kanban Sync

Reconciles the Obsidian Kanban board at `~/Documents/online-personal/Imoto Labs/Kanban.md` with git commit history across tracked Imoto Labs repos. Single source of truth for "what's done": commits with `Kanban:` trailers.

## Setup / portability

**This skill is not portable as-shipped.** Several paths are hardcoded for the author's machine (`howis` user on EndeavourOS). Before using on a different machine you must update:

1. **`config.json`** — 7 absolute paths under `/home/howis/...`:
   - `kanban_path` (Obsidian board location)
   - `archive_dir` (where Done cards >30 days get moved)
   - `projects.<key>.repo_path` × 5 (local repo locations for each tracked project)

2. **`SKILL.md`** (this file) — 3 invocation examples reference `/home/howis/.claude/skills/kanban-sync/scripts/sync.py`. If your `~/.claude/skills/` lives elsewhere, update or use `~/...` form.

3. **`projects.<key>.github_url`** in `config.json` — currently points at `Imoto-Labs/<repo>` on GitHub. Update if forking or using a different org.

The script itself (`scripts/sync.py`) has zero hardcoded paths — it locates its config via `Path(__file__).resolve().parent.parent` and reads everything else from `config.json`. So a future "make this portable" pass is mostly a config refactor (e.g. expand `$HOME` in path values, ship a `config.example.json`, gitignore the actual `config.json`). Not done yet — single-machine use is fine.

The other obvious dependency is the Obsidian vault structure (`Imoto Labs/Kanban.md` + `Imoto Labs/Archive/`) and the kanban-plugin frontmatter conventions. Both are encoded in the parser and renderer; deviating from "Backlog / Up Next / In Progress / Blocked / Done" column names would require code edits.

`state.json` is gitignored — it's runtime cruft (last-synced commit SHA per repo) that gets rewritten on every sync. Each machine maintains its own.

## Trailer format

Every commit that should affect the board carries one (or more) `Kanban:` trailer lines at the bottom:

```
Kanban: DSH-042              # link this commit to card DSH-042, no column move
Kanban: DSH-042 done         # move card to Done, link commit, stamp @{date}
Kanban: DSH-042 progress     # move card to In Progress, link commit
Kanban: DSH-042 blocked      # move card to Blocked / Waiting, link commit
Kanban: DSH-042 backlog      # move back to Backlog, link commit
Kanban: DSH-042 next         # move to Up Next, link commit
Kanban: new "Title here" #driver-shield #pilot #hardware #p0 done    # create new card
```

Commits without a `Kanban:` trailer are ignored — that's the noise filter.

For `Kanban: new`, the project tag (`#driver-shield`, `#business-scout`, etc.) determines the ID prefix; the script picks the next free number. If the project tag is omitted, the script infers it from the originating repo via `config.json`.

## Card format on the board

```markdown
- [ ] DSH-042 · Camera weatherproofing decision #driver-shield #pilot #hardware #p0
	[[Driver Shield 360]] · [Pilot Install §Plan B](github-url) · gating step
```

When moved to Done, the script appends a `Commits:` line and the `@{date}`:

```markdown
- [x] DSH-042 · Camera weatherproofing decision #driver-shield #pilot #hardware #p0 @{2026-05-14}
	[[Driver Shield 360]] · [Pilot Install §Plan B](github-url) · gating step
	Commits: [`c0d7639`](github-url/commit/c0d7639) · [`670fb8d`](github-url/commit/670fb8d)
```

Multiple commits stack newest-first.

## What `sync.py` does on each run

1. Reads `config.json` (project→repo map, kanban path, archive policy).
2. For each tracked repo, gets commits since the SHA recorded in `state.json` for that repo.
3. Parses every `Kanban:` trailer; ignores commits without one.
4. Applies card moves / commit-link appends / new-card creation to `Kanban.md`.
5. Auto-archives Done cards with `@{date}` older than 30 days into `Archive/Kanban Archive YYYY-MM.md` next to the kanban.
6. Prints a soft warning if In Progress holds more than 3 cards.
7. Updates `state.json` with the latest synced SHA per repo so reruns are idempotent.

## Two invocation modes

### Mode 1 — sync only (the default)

The user said something like "sync the kanban", "update the board", or `/kanban-sync`. They have already committed (or someone else has) and want the board to catch up.

Just run:

```bash
python3 /home/howis/.claude/skills/kanban-sync/scripts/sync.py
```

Pure stdlib — no Python deps needed.

Useful flags:
- `--dry-run` — print what would change without touching files
- `--repo <name>` — only sync that one project (matches keys in `config.json`)
- `--no-archive` — skip the 30-day archive sweep this run
- `--assign-ids` — one-shot: walk existing cards and assign IDs to any without one

### Mode 2 — commit + sync (compose the trailer + run sync after)

The user said something like "commit and update kanban", "commit this with a kanban trailer", or `/kanban-sync commit`. They want the staged work committed AND the board updated in one operation. Walk through the **Commit composition workflow** below, then run sync.

## Commit composition workflow

Use this when the user asks to commit AND update the kanban. The goal: produce a commit message with a clean subject, brief body, and one or more `Kanban:` trailers, then commit, then sync.

### Step 1 — inspect what's staged

```bash
git status --short
git diff --cached --stat
git diff --cached    # or a diff summary if huge
git log -3 --oneline  # match repo's commit-message style
```

If nothing is staged, ask the user whether to `git add -A` or stage specific files. Don't auto-stage without consent — risks committing unrelated junk.

### Step 2 — identify candidate card(s)

Read the kanban file (`config.json` → `kanban_path`). For each non-Done card whose project tag matches the **current repo's project key** (look up the cwd's repo in `config.json` projects → match `repo_path`):

- Check if the card's title or scratchpad-link section overlaps semantically with what's staged.
- If exactly one card matches → propose linking to that ID.
- If multiple match → list them, ask the user to pick.
- If none match → propose `Kanban: new "<title>" #<project-tag> [#additional-tags] [<column>]`.

For ambiguous cases, propose your best guess but show the alternatives.

### Step 3 — propose state suffix

Default rule of thumb based on the diff:

| Diff looks like… | Suggested suffix |
|---|---|
| Final fix / feature complete / test passing / closes a thread | `done` |
| Mid-flight progress, partial work | `progress` |
| Just a doc update or scratchpad addendum | (no suffix — link only) |
| Reverts / unblocks something | the inverse move (`progress` if it was Done, etc.) |
| Discovery / investigation only, no card exists yet | `new "..." backlog` or skip the trailer |

If unclear, ask the user. The suffix is a deliberate signal — getting it wrong means the board lies.

### Step 4 — compose the commit message

Format (HEREDOC, mirrors the project's existing style — short subjects, body explains *why*, trailer at bottom):

```
<subject under 70 chars>

<1-3 sentences on the why, optional>

Kanban: <ID> [<state>]
[Kanban: <other-ID> <state>]    # multiple trailers if multiple cards advance
```

Show the proposed message to the user and ask for confirmation BEFORE running `git commit`. The user can:
- Approve → proceed
- Edit the trailer (different ID, different state)
- Edit the body
- Cancel

### Step 5 — commit

Use a HEREDOC to preserve formatting:

```bash
git commit -m "$(cat <<'EOF'
<subject>

<body>

Kanban: DSH-NNN done
EOF
)"
```

Follow normal Claude Code commit safety rules (never `--no-verify`, never bypass hooks, never amend unless explicitly asked, etc. — see the standard commit guidance).

### Step 6 — run sync

```bash
python3 /home/howis/.claude/skills/kanban-sync/scripts/sync.py
```

Report back to the user: what got committed, the SHA, the card(s) that moved, and any WIP warning.

### Step 7 — never push automatically

The user pushes when they're ready. Don't `git push` as part of this skill.

## Edge cases for commit composition

- **Repo not in config**: warn the user, ask if they want to add it to `config.json`. Don't compose a trailer that points at an untracked project.
- **User wants to commit without touching the board**: respect that. Skip the trailer, do a normal commit, skip sync. (They'll have invoked us in error or changed their mind — fine.)
- **`Kanban: new` with no quote-wrapped title**: shlex-fail. Always quote: `Kanban: new "Some title" #tags`.
- **Card already in target column**: still fine — trailer becomes a commit-link append, no move. Don't second-guess; the user's reasons are their own.
- **Staged changes span multiple cards**: emit multiple `Kanban:` trailers, one per card. The script handles them independently.
- **User explicitly types a trailer in the staged commit message** (e.g. via an editor): don't add a duplicate. Inspect their draft message first if there is one.

## Picking the right mode from natural language

| User says… | Mode |
|---|---|
| "sync the kanban", "update the board", `/kanban-sync` | Mode 1 — sync only |
| "commit and update kanban", "commit with kanban trailer", `/kanban-sync commit` | Mode 2 — commit + sync |
| "commit this" (no kanban mention, while inside a tracked repo) | NOT this skill — use the standard commit flow |
| Just a question about how trailers work | Answer from this doc; don't run anything |

If ambiguous, ask. Better to clarify than to commit something the user didn't intend.

## Operational notes

1. **First run on a new machine:** confirm `config.json` lists the right repos with right `id_prefix` values; run `--assign-ids` once to backfill IDs onto existing manual cards.
2. **Routine sync:** just run the script. Report the summary back to the user (cards moved, commits linked, cards archived, WIP warning if any).
3. **If a commit references an unknown card ID:** the script prints a warning and does not create a phantom card. Surface this to the user — the user either typoed the ID or the card was archived.
4. **If a commit's project can't be resolved** (repo not in config, or `Kanban: new` without a project tag): script warns and skips. Surface to the user.

## Optional: post-commit hook (opt-in only)

The skill is designed for manual invocation. A user who wants automatic sync per commit can add a post-commit hook:

```bash
# .git/hooks/post-commit
#!/usr/bin/env bash
python3 /home/howis/.claude/skills/kanban-sync/scripts/sync.py --repo "$(basename $(git rev-parse --show-toplevel))" --quiet &
```

Don't enable this by default — WIP/amend/rebase churn produces noisy partial states. Manual sync at meaningful checkpoints is the recommended pattern.

## Conventions to keep

- Cards are **1-line pointers** to detail in scratchpads. The skill never expands card bodies beyond title, tags, link, commit list. Detail belongs in the repo's docs/.
- IDs are **stable** (`DSH-042` never gets reused or renumbered, even if the card is archived).
- Commit links use **commit-pinned** GitHub URLs (`/commit/<sha>`), not branch URLs — links don't rot when scratchpads get edited later.
- The skill **never deletes** cards. Archive moves them; manual deletion is the user's prerogative.
- The skill **never edits scratchpads** in repos. One-way sync: commits → kanban only.

## Failure modes to handle gracefully

- **Repo path doesn't exist** — config has stale entry; skip that project, warn.
- **Kanban file has manual edits since last sync** — the skill works on a markdown read/write basis; manual edits are preserved as long as IDs are intact. If a card's ID was removed manually, it can't be moved by trailer; print a warning.
- **Trailer references a card already in the target column** — append the commit link, don't redundantly "move".
- **Same commit SHA already linked to a card** — dedupe; don't double-link on rerun.
- **Two trailers in one commit** — process each independently.
