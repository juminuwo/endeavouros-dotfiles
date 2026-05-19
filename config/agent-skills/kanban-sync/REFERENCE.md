# kanban-sync — reference

Lazy-loaded reference material. Read on demand from `SKILL.md` (or the `kanban-planner` agent) when a specific question comes up. Keeping it out of the always-loaded SKILL.md keeps the parent context lean.

## What `sync.py` does on each run

1. Reads `config.json` (project→repo map, kanban path, archive policy).
2. For each tracked repo, gets commits since the SHA recorded in `state.json` for that repo.
3. Parses every `Kanban:` trailer; ignores commits without one.
4. Applies card moves / commit-link appends / new-card creation to `Kanban.md`.
5. Auto-archives Done cards with `@{date}` older than 30 days into `Archive/Kanban Archive YYYY-MM.md`.
6. Prints a soft warning if In Progress holds more than 3 cards.
7. Updates `state.json` with the latest synced SHA per repo so reruns are idempotent.

## Card format on the board

```markdown
- [ ] DSH-042 · Camera weatherproofing decision #driver-shield #pilot #hardware #p0
	[[Driver Shield 360]] · [Pilot Install §Plan B](github-url) · gating step
```

When moved to Done, the script appends `@{date}` and a `Commits:` line:

```markdown
- [x] DSH-042 · Camera weatherproofing decision #driver-shield #pilot #hardware #p0 @{2026-05-14}
	[[Driver Shield 360]] · [Pilot Install §Plan B](github-url) · gating step
	Commits: [`c0d7639`](github-url/commit/c0d7639) · [`670fb8d`](github-url/commit/670fb8d)
```

Multiple commits stack newest-first.

## Operational notes

1. **First run on a new machine:** confirm `config.json` lists the right repos with the right `id_prefix` values; run `--assign-ids` once to backfill IDs onto existing manual cards.
2. **Routine sync:** just run the script. Report the summary back (cards moved, commits linked, cards archived, WIP warning if any).
3. **Commit references unknown card ID:** the script prints a warning and does not create a phantom card. Surface to the user — typo or archived card.
4. **Commit's project can't be resolved** (repo not in config, or `Kanban: new` without a project tag): script warns and skips. Surface to user.

## Failure modes

- **Repo path doesn't exist** — config has stale entry; skip that project, warn.
- **Kanban file has manual edits since last sync** — markdown read/write basis preserves manual edits as long as IDs are intact. If a card's ID was removed manually, it can't be moved by trailer; warning is printed.
- **Trailer references a card already in the target column** — append commit link, don't redundantly "move".
- **Same commit SHA already linked to a card** — dedupe; don't double-link on rerun.
- **Two trailers in one commit** — process each independently.

## Conventions to keep

- Cards are **1-line pointers** to detail in scratchpads. The skill never expands card bodies beyond title, tags, link, commit list. Detail belongs in repo `docs/`.
- IDs are **stable** (`DSH-042` never gets reused or renumbered, even if archived).
- Commit links use **commit-pinned** GitHub URLs (`/commit/<sha>`), not branch URLs — links don't rot.
- The skill **never deletes** cards. Archive moves them; manual deletion is the user's prerogative.
- The skill **never edits scratchpads** in repos. One-way sync: commits → kanban only.

## Optional: post-commit hook (opt-in only)

The skill is designed for manual invocation. For automatic sync per commit:

```bash
# .git/hooks/post-commit
#!/usr/bin/env bash
python3 ~/git/endeavouros-dotfiles/config/agent-skills/kanban-sync/scripts/sync.py --repo "$(basename $(git rev-parse --show-toplevel))" --quiet &
```

Don't enable by default — WIP/amend/rebase churn produces noisy partial states. Manual sync at meaningful checkpoints is the recommended pattern.

## state.json

Gitignored — runtime cruft (last-synced commit SHA per repo) that gets rewritten on every sync. Each machine maintains its own.
