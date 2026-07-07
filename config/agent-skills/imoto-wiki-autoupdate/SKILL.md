---
name: imoto-wiki-autoupdate
description: Weekly Imoto Labs repo-to-Obsidian wiki updater. Use when a cron job or user wants to scan ~/git for GitHub Imoto-Labs repositories and update bounded project-page activity blocks without hallucinating product claims.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Imoto Wiki Autoupdate

Weekly, source-grounded maintenance for the Imoto Labs Obsidian wiki. The job scans local repos under `/home/howis/git`, auto-detects repositories whose remotes point at the GitHub `Imoto-Labs` organization, and updates only bounded, auto-managed sections in the wiki.

This skill is deliberately conservative: it keeps project pages current without rewriting product positioning, messaging docs, strategy, or human-authored notes.

## Scope

Paths:

- Local repo root: `/home/howis/git`
- Imoto vault: `/home/howis/Documents/online-personal/Imoto Labs`
- Project pages: `/home/howis/Documents/online-personal/Imoto Labs/Projects`
- Project index: `/home/howis/Documents/online-personal/Imoto Labs/Projects/Projects.md`
- Canonical scanner script: `/home/howis/git/endeavouros-dotfiles/config/agent-skills/imoto-wiki-autoupdate/scripts/imoto_wiki_repo_scan.py`
- Hermes runtime scanner symlink: `/home/howis/.hermes/scripts/imoto_wiki_repo_scan.py`
- Scanner state: `/home/howis/.hermes/state/imoto-wiki-autoupdate.json`

Auto-include repos when any remote URL matches one of:

- `https://github.com/Imoto-Labs/<repo>`
- `https://github.com/Imoto-Labs/<repo>.git`
- `git@github.com:Imoto-Labs/<repo>.git`

Ignore or treat as diagnostics only:

- `imoto-labs-wiki` — publishing repo, not a product project page source.
- Any non-Imoto-Labs remote.
- Secrets, `.env*`, credentials, `.git` internals, and `/mnt/Main/Project Storage/driver-management-platform`.

## First rule: bounded updates only

The cron agent may only create or replace this block on project pages:

```markdown
<!-- AUTO:IMOTO-WIKI-START repo=Imoto-Labs/<repo> -->
## Recent Repo Activity
...
<!-- AUTO:IMOTO-WIKI-END -->
```

Do not rewrite human-authored summary, Status, ICP, messaging, Strategy, Releases, or Discovery sections. If a project page needs stronger structural edits, report a recommendation instead of editing.

## Run workflow

1. Run the scanner script:
   ```bash
   python3 /home/howis/.hermes/scripts/imoto_wiki_repo_scan.py
   ```
   Completion criterion: stdout contains JSON with `repos`, `unmapped_repos`, `changed_repos`, and either wakes the agent or ends with `{"wakeAgent": false}`.

2. If the scanner output ends with `{"wakeAgent": false}`, stop. No wiki update is needed.

3. For each `changed_repos[]` entry with `wiki_page` set:
   - Read the target wiki page.
   - Read only source files identified by the scanner as safe and useful: `README.md`, docs indexes, `package.json`, `pyproject.toml`, and commit metadata. Do not read credentials or local sensitive storage.
   - Create or replace only the auto-managed block.
   - Mention the update window, branch, latest commit, notable commits, dirty/uncommitted state, and source files reviewed.
   - Treat uncommitted local changes as local-only and not shipped.

4. For `unmapped_repos[]`:
   - Do not invent a full project page by default.
   - Add them only to the cron summary as "unmapped Imoto-Labs repos" with repo path, remote, latest commit, and suggested title.
   - If the user explicitly approves auto-creation later, create minimal `type: project`, `status: draft` or `needs_rewrite` pages and add them to a "Discovered Repos" section rather than making product claims.

5. Patch `Projects/Projects.md` only when:
   - A new project page is explicitly created, or
   - An existing row has a clearly stale deployment/status value grounded in repo docs.
   Otherwise leave the index untouched.

6. Verify:
   - Every modified page still has frontmatter with `type:` and `status:`.
   - Every auto block has exactly one START and one END marker.
   - No file under `Credentials/` or `/mnt/Main/Project Storage/` was read or copied.
   - `git status --short` in `/home/howis/git/driver-management-platform` is not used as proof of vault changes; wiki changes live outside that repo.

## Auto-block format

Use this structure inside the markers:

```markdown
<!-- AUTO:IMOTO-WIKI-START repo=Imoto-Labs/example -->
## Recent Repo Activity

_Last checked: YYYY-MM-DD HH:MM TZ. Source: `/home/howis/git/example` on branch `main`._

- Latest commit: `abc1234` — commit subject (YYYY-MM-DD).
- Recent changes since the previous scan:
  - `abc1234` — commit subject.
  - `def5678` — commit subject.
- Local state: clean / local uncommitted changes present; not treated as shipped.
- Sources reviewed: `README.md`, `docs/README.md`, `package.json`.

Notes:
- Keep this section factual. Update human-authored status/positioning manually when needed.
<!-- AUTO:IMOTO-WIKI-END -->
```

Use "No new commits since previous scan" only when the scanner woke for another reason but this page has no repo changes.

## Grounding rules

Allowed sources:

- Git metadata: `git log`, `git status --short`, branch, remotes.
- Repo docs: `README.md`, `docs/README.md`, other docs indexes explicitly linked from README/indexes.
- Project manifests: `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`.
- Existing wiki project page.

Forbidden claims unless the source explicitly says them:

- Live/production deployment exists.
- Customer/pilot traction exists.
- Compliance, SOC2, HIPAA, DOT/FMCSA readiness.
- Real PII is approved.
- OCR/model accuracy or settlement match rates.
- ROI/time-saved numbers.

Never use commit messages alone to update product positioning. Commit messages can populate `Recent Repo Activity`, but human-authored status changes require docs or explicit user direction.

## Known repo-title aliases

Use deterministic aliases before guessing:

| Repo slug | Wiki project title |
|---|---|
| `business-scout` | `Business Scout` |
| `customer-tracking-portal` | `Customer Tracking Portal` |
| `driver-management-platform` | `Driver Management Platform` |
| `driver-shield` | `Driver Shield 360` |
| `route-optimisation` | `Route Optimization` |
| `predictive-maintenance` | `Predictive Maintenance` |
| `logistics-pricing` | `Logistics Pricing` |
| `logistics-pricing-engine` | `Logistics Pricing` |
| `imoto-event-sourcing-agent` | `Event Sourcing Agent` |
| `financial-dd-skill` | `Financial DD Skill` |

If alias and content matching disagree, do not edit; report ambiguity.

## Cron configuration

Recommended Hermes cron job:

- Name: `imoto-wiki-weekly-autoupdate`
- Schedule: `0 23 * * 5` (weekly Friday 23:00 local time)
- Script: `imoto_wiki_repo_scan.py`
- Skills: `obsidian-vault`, `obsidian`, `imoto-wiki-autoupdate`
- Toolsets: `terminal`, `file`, `code_execution`
- Delivery: `discord:isitokaymimi` if weekly notifications are desired; otherwise `local` in CLI-only sessions.

Cron prompt must be self-contained. It should state that the agent is allowed to update only auto-managed blocks and summarize unmapped repos rather than creating broad new pages.

## Common pitfalls

1. **Hallucinating from repo names.** A repo name can suggest a product, but only README/docs/manifests and existing wiki text can support claims.
2. **Rewriting project pages.** The auto job is a maintenance pass, not a copywriting pass. Use the auto block.
3. **Publishing secrets.** The vault publishes through Quartz; never add credentials or copied sensitive source material to public wiki folders.
4. **Treating dirty state as shipped.** Dirty files are local evidence that work exists, not a release or project status change.
5. **Creating messaging docs automatically.** Messaging docs are strategic artifacts. Flag missing docs; do not create/update them in the weekly job unless the user explicitly asks.
6. **Letting unmapped repos disappear.** Always include unmapped Imoto-Labs repos in the summary so the user can decide whether to create pages.

## Verification checklist

- [ ] Scanner ran successfully or emitted `wakeAgent: false`.
- [ ] Every edited wiki file is under `/home/howis/Documents/online-personal/Imoto Labs/Projects/` unless the user explicitly approved broader edits.
- [ ] Each edited page has valid frontmatter with `type:` and `status:`.
- [ ] Each edited project page has at most one `AUTO:IMOTO-WIKI-START` block for that repo.
- [ ] Summary lists changed repos, skipped repos, and unmapped repos.
- [ ] No production credentials, secrets, or real driver PII were read into or written into the wiki.
