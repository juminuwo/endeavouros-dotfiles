# kanban-sync — portability

**Not portable as-shipped.** Several paths are hardcoded for the author's machine (`howis` user on EndeavourOS). Before using on a different machine, update:

1. **`config.json`** — 7 absolute paths under `/home/howis/...`:
   - `kanban_path` (Obsidian board location)
   - `archive_dir` (where Done cards >30 days get moved)
   - `projects.<key>.repo_path` × 5 (local repo locations for each tracked project)

2. **`SKILL.md`** invocation examples reference `~/git/endeavouros-dotfiles/config/agent-skills/kanban-sync/scripts/sync.py`. If your dotfiles checkout lives elsewhere, update.

3. **`projects.<key>.github_url`** in `config.json` — currently points at `Imoto-Labs/<repo>` on GitHub. Update if forking or using a different org.

The script itself (`scripts/sync.py`) has zero hardcoded paths — it locates its config via `Path(__file__).resolve().parent.parent` and reads everything else from `config.json`. So a future "make this portable" pass is mostly a config refactor (e.g. expand `$HOME` in path values, ship a `config.example.json`, gitignore the actual `config.json`). Not done yet — single-machine use is fine.

The other obvious dependency is the Obsidian vault structure (`Imoto Labs/Kanban.md` + `Imoto Labs/Archive/`) and the kanban-plugin frontmatter conventions. Both are encoded in the parser and renderer; deviating from "Backlog / Up Next / In Progress / Blocked / Done" column names would require code edits.
