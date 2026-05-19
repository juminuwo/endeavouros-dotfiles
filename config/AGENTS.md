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
- Each project has its own `CLAUDE.md` for project-specific commands and structure
- Python projects use `uv` with `.venv` in the project directory
- Shared personal agent skills live in `~/git/endeavouros-dotfiles/config/agent-skills/`. Claude/Codex use symlinks; Hermes reads the directory via `skills.external_dirs`.

## Obsidian Vault
The vault lives at `~/Documents/online-personal/`. For any vault-related task, the `obsidian-vault` skill loads the full structure, conventions, and publishing flow on trigger — don't duplicate vault content here.

## Imoto Labs Kanban (planning surface)
The portfolio kanban for Imoto Labs work lives at `~/Documents/online-personal/Imoto Labs/Kanban.md`. **For "what's next" / "what should I work on" / "what's in flight" / planning questions**, this is the entry point — invoke the `kanban-sync` skill (Mode 3, read-only). Cards link to repo scratchpads via GitHub URLs; the skill maps those back to local files via its `config.json` so reads stay on-disk. The `kanban-sync` skill also handles syncing the board from commit trailers (Mode 1) and composing a commit with a `Kanban:` trailer (Mode 2).

## Imoto Labs positioning
Imoto Labs is positioned as a **3PL technology company** sitting between carriers and shippers, building custom tech solutions — NOT a carrier that happens to have tech. As of 2026-04, no first customer yet; the existing "5 core products" (tracking portal, route optimization, Samsara integration, dashboards) are POCs/capability demos, not production products. The approach is customer-needs-driven: understand a specific customer's problems, then build to fit. When working on Imoto Labs materials, frame from the customer's perspective and lead with team track record (Food Lion/Instacart, SITA, Network Rail, West Africa delivery startup) for credibility — don't reference the original 5-product framework as current strategy.

## About the user
- **Training:** cyclist + runner. Half marathon PBs: 5k 30:53, 10k 1:12:13, HM ~2:20. Current focus: cycling improvement with running maintenance (1-2 easy runs/week). Uses Intervals.icu, athlete ID `i437227`.
- **Imoto Labs:** founder; tech background spans Food Lion/Instacart, SITA, Network Rail, West Africa delivery startup.

## Working with this user
- **No filler/hedge words.** Drop "honestly", "frankly", "to be clear", "obviously". State recommendations directly; if a tradeoff genuinely needs softening, name the tradeoff itself rather than hedging with filler.
- **No LaTeX.** Kitty doesn't render `$...$` or `$$...$$` — equations show as raw source. Use plain ASCII or Unicode for math (σ, μ, x², `p(1-p)/n`); use fenced code blocks for multi-line equations where monospace alignment beats LaTeX-source-as-text.
- **Run commands locally.** When fixing bugs or verifying new code, run the relevant commands directly via Bash so you see error output and iterate in one turn — don't ask the user to relay stdout. Fall back to asking only when the command (a) needs interactive input, (b) requires hardware/UI you don't have, or (c) is destructive and needs confirmation.
- **SSH paste commands: short separate lines, no `\`-continuations.** When giving the user shell commands to paste into an SSH session, prefer 2–6 short separate commands each fitting one terminal width; never use backslash-newline continuations (they break on paste); never use very long one-liners (Claude Code's auto-wrap injects whitespace mid-token). For genuinely complex sequences, write to a script file and run it remotely.
- **Remote-host debugging split.** For Pi 5 and any other remote-host bring-up: run read-only inspection commands (`cat`, `ls`, `dmesg`, `lsusb`, `dpkg -l`) **directly via SSH** from Bash. Hand the user anything that **mutates state** — `sudo`, `apt install`, system file edits, reboots, service start/stop. Format hand-offs per the SSH-paste rule above.
- **Stage-appropriate engineering.** Default to the simpler version for the current stage. The user is in **Pilot** stage (1 source Pi, 1 cloned Pi at most) and prefers manual bash workflows over engineered automation until evidence motivates the upgrade. For "Pilot vs Fleet" splits, recommend Pilot + a one-line note on the Fleet upgrade trigger. Don't engineer for hypothetical fleet scale until there's an actual second device, an actual incident, or an actual operator-other-than-the-user. Counter-case: when the right-thing-now also happens to be the right-thing-for-Fleet at near-zero extra cost, do the right thing.
- **Don't promote deferred decisions.** When constructing a linear "do these steps" plan, only include steps the user has actually committed to. If a decision is documented as deferred, optional, or behind a measurement gate ("do A, climb to B only if A insufficient"), keep it out of the linear sequence — or mark it explicitly optional with the gating condition cited. Reasoning that justifies an upstream choice ("Trixie has Hailo support, so use Trixie") is fine; that doesn't license adding the downstream optional step ("install Hailo HAT stack").

## Tool gotchas
- **Codex hooks need `/hooks` approval and are hash-pinned.** New hooks in `~/.codex/hooks.json` (or inline in `config.toml`) silently don't fire until the user explicitly approves each command via `/hooks` in an interactive Codex session. Approvals are recorded as `trusted_hash = "sha256:…"` under `[hooks.state."<file>:<event>:<group>:<idx>"]` in `~/.codex/config.toml`. **Any** edit to `hooks.json` (cosmetic, matcher change, reorder) changes the canonical hash and silently invalidates the approval — re-approval required. After editing hooks, always tell the user to re-run `/hooks`.
- **No `co`/`cx` wrapper for Codex.** Codex CLI renames the kitty tab natively, so no parallel to the `cc` zsh function is needed. The `cc` function in `endeavouros-dotfiles/config/zshrc` exists *only* because Claude Code doesn't rename the tab itself.
- **Shared skill tool-name mapping for Hermes:** Bash → `terminal`, Read → `read_file`, Write → `write_file`, Edit → `patch`, Glob/Grep → `search_files`, WebFetch/WebSearch → web/search tools, Agent → `delegate_task`.
