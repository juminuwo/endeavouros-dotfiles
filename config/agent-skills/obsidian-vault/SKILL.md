---
name: obsidian-vault
description: Apply Adrian's local conventions and privacy boundaries when working in ~/Documents/online-personal/, including Imoto Labs notes and Quartz wiki publishing. Use alongside the official Obsidian skills for vault work.
---

# Adrian's vault

Vault root: `~/Documents/online-personal/`. Read its `CLAUDE.md` and any
`AGENTS.md` / `CLAUDE.md` in the target subtree; these live outside the usual
Git workspace and may not auto-load. The root guide has stale `imoto_labs/`
and Career layout references: use `Imoto Labs/` and `Personal/Career/`, and
inspect the target directory before choosing a new location.

## Official skills

Use the relevant upstream skill alongside this local context. Their canonical
copies are sibling directories under `~/git/endeavouros-dotfiles/config/agent-skills/`:

- `obsidian-markdown`: note syntax, wikilinks, embeds, callouts and properties.
- `obsidian-bases`: `.base` views, filters and formulas.
- `obsidian-cli`: operations through the running desktop app. Target
  `vault="online-personal"` explicitly as the first parameter.
- `defuddle`: extracting web pages as Markdown.
- `knap`: rendering notes from templates and structured data.
- `obsidian-headless`: only for requested Headless Sync/Publish work. This vault
  uses desktop Obsidian Sync and the Imoto wiki uses Quartz; keep those existing
  workflows unless the user requests a migration.

Load only the skills relevant to the task. Canvas is not part of the current
vault workflow.

## Locations and local conventions

| Content | Location / canonical guidance |
|---|---|
| Company notes | `Imoto Labs/`; read `Imoto Labs/CLAUDE.md` for naming, frontmatter, meeting/release/project placement and index updates |
| Messaging | `Imoto Labs/Messaging/Messaging.md`, then the relevant product note; current Driver Shield procurement decisions live in `Messaging/Driver Shield.md` |
| Personal notes | `Personal/`; follow the target collection's existing pattern |
| Career | `Personal/Career/AGENTS.md`; use `career-search` or `job-market-tracker` for their respective workflows |
| Personal project ideas | `Projects/` |
| Technology entries | `Resources/Technologies/`; use `tech-wiki` |
| Attachments | `Attachments/` |
| Excalidraw diagrams | `Resources/Diagrams/` |

Use Title Case filenames and folder-named indexes (`<Folder>/<Folder>.md`),
with YAML `type` and `status`; add dates for time-bound notes. Keep the affected
indexes current. Do not create task checkboxes unless explicitly requested
(the vault uses the Tasks plugin). Do not add new material to `Archive/`.

For a personal collection saved from chat, preserve the requested folder/title
spelling. Put each draft in its own note (`type: reference`, `status: draft`,
`date`), create the collection index (`type: index`, `status: active`, `updated`),
and link new collections under `Personal/Personal.md` → `Sections`.

## Privacy and the Imoto wiki

`Personal/` and personal `Projects/` are private. Only `Imoto Labs/` is synced
into the Quartz wiki. Store Imoto credentials in `Imoto Labs/Credentials/`,
which the publish script excludes from the Git copy.

Ordinary Imoto notes, including Messaging and Discovery, are intended for the
org wiki: omit `draft` or use `draft: false`. Use `draft: true` only when a note
should be hidden. A note's `status: draft` is separate from publish visibility.
Quartz draft/ignore filters hide rendered pages; they do not keep source files
out of the wiki Git history. Keep secrets out of synced content.

Publishing details and commands are in [references/publishing.md](references/publishing.md).
Read that reference when publishing, changing visibility, or restructuring
Imoto navigation.
