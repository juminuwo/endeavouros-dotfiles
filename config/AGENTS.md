# Cross-Project Context

This file is the canonical `AGENTS.md` for the user's `~/git/` tree and is symlinked from `~/git/AGENTS.md` and `~/git/CLAUDE.md`. Every project under `~/git/` inherits it. Keep content here strictly to things useful in *every* project — project-specific guidance belongs in that project's own `AGENTS.md`.

## OS & Environment
- **OS:** EndeavourOS (Arch-based, rolling release)
- **Window Manager:** i3
- **Shell:** zsh
- **Terminal:** Kitty
- **Package Manager:** yay (AUR + pacman wrapper)
- **Editor:** Neovim (`vim` is aliased to `nvim`), Cursor IDE

## Development Tools
- **Python 3** — managed per-project with `uv` (creates `.venv/` in the project root)
- **Node.js**, **GitHub CLI** (`gh`), **Docker** — installed system-wide
- For exact versions, run `<tool> --version` — versions drift, don't pin them here

## Conventions
- Git repos live in `~/git/`
- Each project can have its own `AGENTS.md` and/or `CLAUDE.md` for project-specific commands and structure
- Python projects use `uv` with `.venv` in the project directory
- Shared personal agent skills live in `~/git/endeavouros-dotfiles/config/agent-skills/`. Codex/Claude use symlinks; Hermes reads the directory via `skills.external_dirs`.

## Frontend and UI Design
For frontend or UI work, read the repo root `DESIGN.md` when present before making visual changes. If a UI repo lacks one and the task requires design decisions, use the shared convention in `~/git/docs/design-workflow.md` and starter template at `~/git/docs/templates/DESIGN.md`.

## Machine Services
Personal system config lives in `~/git/endeavouros-dotfiles`. User services are grouped as `default.target` (personal always-on), `work.target` (work/project daemons, enabled automatically on MAIN), and `timers.target` (scheduled jobs). Use `services-workflow audit`, `services-workflow work status`, and `systemctl --user list-dependencies work.target`. Do not hand-edit `~/.config/systemd/user` when a repo-managed unit exists; edit `config/host/systemd/user/` in the dotfiles repo and run `./host-install`.

## Obsidian Vault
The vault lives at `~/Documents/online-personal/`. For any vault-related task, the `obsidian-vault` skill loads the full structure, conventions, and publishing flow on trigger — don't duplicate vault content here.

## Imoto Labs Kanban (planning surface)
The portfolio kanban for Imoto Labs work lives at `~/Documents/online-personal/Imoto Labs/Kanban.md`. For read-only planning questions ("what's next?", "what should I work on?", "what's in flight?"), use the `kanban-planner` agent. Use the `kanban-sync` skill only for syncing from commit trailers or composing commits that update the board.

## Linear Work
Linear is execution tracking, not the durable decision log. When the user asks for Linear Project, Milestone, or Issue work, or names a Linear issue as the active task, follow the shared convention in `~/git/docs/linear-workflow.md` and the repo overlay at `docs/technical/linear-workflow.md` when present.

## Imoto Labs positioning
Imoto Labs is positioned as a **3PL technology company** between carriers and shippers, building customer-fit technology solutions — not a carrier that happens to have tech. Treat the old "5 core products" framing as POC/capability-demo context, not current strategy. Check the vault/kanban for current customer status before making claims.

## About the user
- **Training:** cyclist + runner; use Intervals.icu athlete ID `i437227` only for training-related tasks, and verify current plan/status before advising.
- **Imoto Labs:** founder; tech background spans Food Lion/Instacart, SITA, Network Rail, West Africa delivery startup.

## Working with this user
- **No filler/hedge words.** Drop "honestly", "frankly", "to be clear", "obviously". State recommendations directly; if a tradeoff genuinely needs softening, name the tradeoff itself rather than hedging with filler.
- **No LaTeX.** Kitty doesn't render `$...$` or `$$...$$` — equations show as raw source. Use plain ASCII or Unicode for math (σ, μ, x², `p(1-p)/n`); use fenced code blocks for multi-line equations where monospace alignment beats LaTeX-source-as-text.
- **Run commands locally.** When fixing bugs or verifying new code, run the relevant commands directly via Bash so you see error output and iterate in one turn — don't ask the user to relay stdout. Fall back to asking only when the command (a) needs interactive input, (b) requires hardware/UI you don't have, or (c) is destructive and needs confirmation.
- **Basic Q&A should stay cheap.** For simple factual questions, answer from stable model knowledge when safe. If the user asks for "current" facts or the fact is time-sensitive, use exactly one lightweight lookup and answer directly. In noninteractive Hermes sessions, do not use `terminal` for web lookup because command approval can block; use web/search tools if available, otherwise one `browser_navigate` to a reference page. Do not write scripts, scrape pages, use Python pipelines, or perform multi-source verification unless the user asks for deeper research, sources conflict, or the answer supports a consequential decision.
- **Python/tool dependency discipline.** For Python tasks, prefer stdlib when it is enough. Before using non-stdlib imports, either verify availability with `importlib.util.find_spec(...)` or rely on packages already established in this environment. Do not install packages unless asked or the task clearly requires a reusable environment change. System Python has `beautifulsoup4`, `lxml`, and `html5lib` available for real scraping/parsing tasks; Hermes' own app venv is separate and should not be mutated casually.
- **SSH paste commands: short separate lines, no `\`-continuations.** When giving the user shell commands to paste into an SSH session, prefer 2–6 short separate commands each fitting one terminal width; never use backslash-newline continuations (they break on paste); never use very long one-liners (Claude Code's auto-wrap injects whitespace mid-token). For genuinely complex sequences, write to a script file and run it remotely.
- **Remote-host debugging split.** For Pi 5 and any other remote-host bring-up: run read-only inspection commands (`cat`, `ls`, `dmesg`, `lsusb`, `dpkg -l`) **directly via SSH** from Bash. Hand the user anything that **mutates state** — `sudo`, `apt install`, system file edits, reboots, service start/stop. Format hand-offs per the SSH-paste rule above.
- **Stage-appropriate engineering.** Default to the simpler version for the project's current stage. Check the project's own `AGENTS.md`, runbooks, or kanban before assuming Pilot/Fleet/customer status. Don't engineer for hypothetical scale until there is an actual second device/customer/operator/incident, unless the right thing now is also the scalable path at near-zero extra cost.
- **Don't promote deferred decisions.** When constructing a linear "do these steps" plan, only include steps the user has actually committed to. If a decision is documented as deferred, optional, or behind a measurement gate ("do A, climb to B only if A insufficient"), keep it out of the linear sequence — or mark it explicitly optional with the gating condition cited. Reasoning that justifies an upstream choice ("Trixie has Hailo support, so use Trixie") is fine; that doesn't license adding the downstream optional step ("install Hailo HAT stack").

## Tool gotchas
- **Codex hooks need `/hooks` approval and are hash-pinned.** New hooks in `~/.codex/hooks.json` (or inline in `config.toml`) silently don't fire until the user explicitly approves each command via `/hooks` in an interactive Codex session. Approvals are recorded as `trusted_hash = "sha256:…"` under `[hooks.state."<file>:<event>:<group>:<idx>"]` in `~/.codex/config.toml`. **Any** edit to `hooks.json` (cosmetic, matcher change, reorder) changes the canonical hash and silently invalidates the approval — re-approval required. After editing hooks, always tell the user to re-run `/hooks`.
- **No `co`/`cx` wrapper for Codex.** Codex CLI renames the kitty tab natively, so no parallel to the `cc` zsh function is needed. The `cc` function in `endeavouros-dotfiles/config/zshrc` exists *only* because Claude Code doesn't rename the tab itself.
- **Shared skill tool-name mapping for Hermes:** Bash → `terminal`, Read → `read_file`, Write → `write_file`, Edit → `patch`, Glob/Grep → `search_files`, WebFetch/WebSearch → web/search tools, Agent → `delegate_task`.
