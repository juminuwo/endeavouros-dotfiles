---
name: obsidian-vault
description: Work with Adrian's Obsidian vault at ~/Documents/online-personal/ — add meeting notes, releases, messaging docs, projects; update navigation; publish the Imoto Labs wiki. Triggers on any task involving the vault, Imoto Labs notes, Personal notes, Technologies wiki entries, or wiki publishing.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

# Obsidian Vault

The user's Obsidian vault lives outside `~/git/`, so its CLAUDE.md files do **not** auto-load when cwd is `~/git/`. This skill bundles vault context so any vault-related task can be done without the user manually linking files.

## Vault Layout

**Root:** `/home/howis/Documents/online-personal/`

```
online-personal/
├── Imoto Labs/             # Company knowledge base (published to Quartz wiki)
├── Personal/               # Personal notes
├── Projects/               # Project ideas and planning
├── Resources/
│   └── Technologies/       # Tech wiki entries (managed by tech-wiki skill)
└── …
```

When uncertain about a subtree's structure, list it before writing — the vault evolves and this SKILL.md may lag reality.

## Imoto Labs (most common target)

**Path:** `/home/howis/Documents/online-personal/Imoto Labs/`

```
Imoto Labs/
├── CLAUDE.md               # Detailed conventions — READ when doing non-trivial Imoto work
├── Imoto Labs.md           # Root index (MOC)
├── Credentials/            # PRIVATE — production logins, excluded from publishing
├── Discovery/              # Customer-facing materials, competitor research
├── Founding/               # Archived: how the company started
├── Meetings/               # Chronological call notes (YYYY-MM-DD.md)
├── Messaging/              # Internal source-of-truth messaging docs (one per product)
├── Projects/               # POCs (one subfolder per project, with internal index)
├── Reference/              # Tooling, dashboards, links
├── Releases/               # Product launch announcements (YYYY-MM-DD <Name>.md)
└── Strategy/               # Strategic direction, positioning, open questions
```

**Always read `Imoto Labs/CLAUDE.md` before doing non-trivial Imoto work** — it has the canonical conventions (frontmatter schema, naming rules, what goes where, messaging-doc structure, publishing details).

### Quick conventions cheat sheet

- **Naming:** `Title Case` for dirs and files (e.g. `Customer Tracking Portal/`, `Driver Shield.md`).
- **Folder index:** every folder has `<Folder Name>.md` (the MOC). When publishing, `publish.sh` renames these to `index.md` for Quartz.
- **Meeting note:** `Meetings/YYYY-MM-DD.md` AND add a row to the `Meetings/Meetings.md` table under the right year.
- **Release note:** `Releases/YYYY-MM-DD <Name>.md` AND add a row to `Releases/Releases.md`.
- **New project:** `Projects/<Name>/<Name>.md` AND add a row to `Projects/Projects.md`.
- **Publish status:** `draft: true` blocks publishing. Do not add `draft: true` by default to Imoto Labs docs; use `draft: false` or omit the field unless the user explicitly wants a file hidden.
- **Frontmatter:** every file needs YAML frontmatter — `type:` (meeting | decision | spec | strategy | reference | release | index | project | messaging-doc | messaging-doc-guide | credentials), `status:` (active | archived | needs_rewrite | draft), and `date:` for time-bound docs.
- **Linking:** Obsidian `[[wikilinks]]` for internal navigation, `[text](url)` for external.
- **Publishing visibility:** `draft: true` prevents a file from publishing. Do not add it unless the user explicitly wants the note hidden; for normal Imoto Labs work, prefer `draft: false`.
- **Hidden from publishing:** private folders are excluded via publishing config or per-file `draft: true` where already present. Do not assume `Messaging/` or `Discovery/` should be draft-hidden; Driver Shield messaging and ordinary discovery/strategy docs are intended to publish unless explicitly hidden.

## Publishing the wiki

The Imoto Labs vault is published as a static site via Quartz 4.

- **Quartz repo:** `~/git/imoto-labs-wiki/` (remote: `Imoto-Labs/imoto-labs-wiki`, **private**)
- **Live site:** https://imoto-labs-wiki.adrianliu95.workers.dev/ (Cloudflare Workers Static Assets, no custom domain).
- **Auth:** Cloudflare Access with GitHub Org rule — only members of the `Imoto-Labs` GitHub org can read.
- **Publish script:** `~/git/imoto-labs-wiki/publish.sh` — rsyncs vault → `content/`, renames folder indexes to `index.md`, strips `[[Founding]]`/`[[Meetings]]` links from root, commits and pushes to `v4`. Cloudflare Workers Builds picks up the push, runs `npx quartz build` then `npx wrangler deploy`. Refuses to run if the remote has unmerged commits — tells you to run `pull.sh` first.
- **Pull script:** `~/git/imoto-labs-wiki/pull.sh` — the inverse. `git pull --rebase --autostash`, then for each file changed in the pull, copies it into the vault while reversing publish.sh's folder-index rename. Use after a PR merges so those edits land in your local vault (and via Obsidian Sync, on mobile). Skips the root index — publish.sh's link strip would clobber it; manually merge if needed.
- **Wrangler config:** `wrangler.jsonc` at repo root — `assets.directory: ./public`, `not_found_handling: 404-page`.
- **Automatic publish:** systemd user timer `imoto-wiki-publish.timer` (hourly, with `Persistent=true`). Units in `~/git/endeavouros-dotfiles/config/host/systemd/user/`. The timer invokes publish.sh; if remote is ahead, the run fails and the user must run `pull.sh` manually before the next publish succeeds.

To publish on demand:
```bash
~/git/imoto-labs-wiki/publish.sh                          # run script directly
systemctl --user start imoto-wiki-publish.service         # equivalent via systemd
journalctl --user -u imoto-wiki-publish.service -n 50     # check recent runs
```

To change Quartz behaviour (e.g. add a folder to `ignorePatterns`), edit `~/git/imoto-labs-wiki/quartz.config.ts`. Patterns are case-sensitive and match against paths under `content/`.

## Publishing safety rules

- **Never put credentials, API keys, or secrets in any folder that publishes.** `Credentials/` is the only safe place. If unsure, default to `Credentials/`.
- **Before adding a new top-level folder to the vault,** decide whether it should publish. If not, add it to `ignorePatterns` in `quartz.config.ts` *and* avoid linking it from `Imoto Labs.md`.
- **Wikilinks pointing into excluded folders will silently 404 in the published site.** When excluding a folder, also remove or comment out links to it from public navigation.
- **If a sensitive file accidentally got committed to `imoto-labs-wiki`,** removing it in a later commit is not enough — it remains in git history. Flag the leak to the user, recommend rotating the leaked secret, and ask before doing any history rewrite.

## Personal vault

- **Personal notes:** `~/Documents/online-personal/Personal/`
- **Project ideas / planning:** `~/Documents/online-personal/Projects/`

These are private — never publish or expose externally. Lighter conventions than Imoto Labs; follow whatever pattern already exists in the target subdirectory.

### Personal note collections from chat drafts

When the user asks to save a set of personal drafts/ideas into `Personal/`:
1. Preserve the user-requested folder/title spelling unless they ask for correction, even if it contains a typo.
2. Create `Personal/<Collection>/<Collection>.md` as the folder index with `type: index`, `status: active`, and `updated: YYYY-MM-DD`.
3. Create each draft as its own markdown file with frontmatter such as `type: reference`, `status: draft`, and `date: YYYY-MM-DD`.
4. Add each draft to the collection index using Obsidian wikilinks.
5. Add the collection to `Personal/Personal.md` under `## Sections` if it is a new Personal subsection.
6. For rough multilingual text, lightly normalize spelling/grammar for readability while preserving the user's tone, intent, line-item structure, prices, URLs, and any intentionally casual phrasing.

## Common tasks — short playbooks

### Log a meeting
1. Create `Meetings/YYYY-MM-DD.md` with frontmatter (`type: meeting`, `status: active`, `date: YYYY-MM-DD`, `draft: false`).
2. Write up the call (topic, decisions, action items).
3. Append a row to the right year's table in `Meetings/Meetings.md` with key topics.

### Add a release
1. Create `Releases/YYYY-MM-DD <Name>.md` with `type: release`, deployment URL, what shipped, known limitations.
2. Append a row to the year table in `Releases/Releases.md`.
3. Optionally trigger a publish: `~/git/imoto-labs-wiki/publish.sh`.

### Add a new project (Imoto)
1. `mkdir Projects/<Name>/`
2. Create `Projects/<Name>/<Name>.md` (the folder index, `type: index` or `type: project`) with summary, status, repo link, tech stack.
3. Add a row to the appropriate table in `Projects/Projects.md` ("Active POCs" or "Separate Repos").

### Add or update a messaging doc
1. Read `Messaging/Messaging.md` for structure and conventions.
2. Read an existing doc (e.g. `Messaging/Driver Shield.md`) for the template.
3. Create `Messaging/<Product>.md` with `type: messaging-doc`. Set `draft: false` by default; set `draft: true` only if the user explicitly wants the file hidden from publishing.
4. Add a link under "Existing docs" in `Messaging/Messaging.md`.
5. For Driver Shield procurement / pilot-rig cost-basis edits, also consult `references/driver-shield-procurement-messaging.md` for the current framing: fleet-budget new-build is the default path; 4K builds are other/reference paths.

### Update navigation after structural changes
- Touched any folder index (`<Folder>/<Folder>.md`)? Make sure it lists all current children.
- Added a new top-level folder? Decide if public → add link to `Imoto Labs.md`. If private → add to `ignorePatterns` and leave it out of nav.
- Removed/renamed a folder? Update `Imoto Labs.md`, search for stale wikilinks: `grep -rn "\[\[OldName" ~/Documents/online-personal/`.

### Tech wiki entry
Don't reinvent — the `tech-wiki` skill handles this. Defer to it when the task is "add a tech entry".

## When to read the full Imoto Labs CLAUDE.md

Read `~/Documents/online-personal/Imoto Labs/CLAUDE.md` for any of:
- Editing or creating a messaging doc
- Changing publishing behaviour or `quartz.config.ts`
- Restructuring folders or renaming sections
- Adding a frontmatter field that isn't in the cheat sheet above
- Anything where the cheat sheet feels insufficient

For routine "add a meeting note" or "log a release", the cheat sheet above is enough.
