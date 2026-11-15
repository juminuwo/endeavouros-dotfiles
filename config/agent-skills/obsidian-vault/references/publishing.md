# Imoto Quartz publishing

- Repo: `~/git/imoto-labs-wiki/` (`Imoto-Labs/imoto-labs-wiki`, private).
- Site: https://imoto-labs-wiki.adrianliu95.workers.dev/ — Cloudflare Access
  restricts readers to the `Imoto-Labs` GitHub org.
- `publish.sh` copies only `~/Documents/online-personal/Imoto Labs/` into
  `content/`, excludes `Credentials/`, renames folder indexes to `index.md`,
  strips Founding/Meetings links from the root index, commits and pushes.
  Cloudflare Workers Builds builds Quartz and deploys pushes to `v4`.
- `imoto-wiki-publish.timer` runs hourly with `Persistent=true`. Units live in
  dotfiles at `config/host/systemd/user/`.

For an on-demand publish, run `~/git/imoto-labs-wiki/publish.sh`.
Inspect recent runs with `journalctl --user -u imoto-wiki-publish.service -n 50`.

The publisher refuses when local HEAD differs from its upstream. Inspect the
state before following its instruction to run `~/git/imoto-labs-wiki/pull.sh`:
that script pulls and copies changed wiki content back into the vault, reversing
index renames. It refuses dirty `content/`; the root index is skipped and needs
manual reconciliation if changed remotely.

For visibility changes, inspect the actual `publish.sh` exclusions and
`quartz.config.ts` `ignorePatterns` (case-sensitive). The former controls what
enters Git; the latter and `draft: true` control what Quartz renders. Remove
navigation links to excluded notes to avoid broken published links. For a new
Imoto section, decide its visibility and update `Imoto Labs.md` accordingly.

If a secret reached wiki Git history, flag it and recommend rotation; deleting
the current file does not remove history. Ask before rewriting history.
