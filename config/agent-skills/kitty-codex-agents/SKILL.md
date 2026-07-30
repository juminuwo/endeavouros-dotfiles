---
name: kitty-codex-agents
description: Spawn, monitor, and coordinate live-visible Codex coding agents in kitty tabs with Hermes remote control. Use when the user invokes kitty-codex-agents or asks to open, message, inspect, or coordinate Codex agents in kitty; prefer this workflow over tmux on Adrian's machine.
---

# Kitty Codex Agents

Keep the main Hermes tab as coordinator and run each Codex agent in a normal kitty tab that the user can watch, enter, and control. Prefer kitty over tmux unless the user asks for tmux or kitty remote control is unavailable.

Invoking this skill with a coding task means opening a new Codex tab immediately. Only skip launch when the user asks to inspect or monitor an existing tab.

## Guardrails

- Default to one narrow author agent. Add one review agent only when the user asks or the change is risk-bearing: security/auth, permissions, state transitions, migrations, concurrency, destructive effects, or a wide cross-cutting diff.
- Never spawn a dedicated test agent.
- Never let agents repeat a full or broad suite. Share test commands and results in handoffs.
- Give each author one git worktree. Put worktrees in a disk-backed sibling directory under `/home/howis/git`, never `/tmp`.
- Do not let multiple agents edit the same checkout. A reviewer may inspect the author's worktree only after the author is idle and must return issues to the author rather than edit.
- Keep every tab live-visible with `--hold`. Set a stable `--var hermes_agent=<agent-name>` and target that variable rather than the mutable tab title.

## Start the Workflow

1. Verify the control surface:

   ```bash
   command -v kitty
   kitty --version
   command -v codex
   codex --version
   kitty @ ls
   ```

2. Check resource headroom before creating a worktree or agent:

   ```bash
   free -h
   df -h /home/howis/git
   ps -eo pid,rss,cmd --sort=-rss | head
   ```

   Stop new agents and broad work when memory is low or swapping heavily, disk has less than 10 GiB or 10% free, an OOM kill occurred, or any command reports `ENOSPC`. Close completed agent tabs, clean eligible worktrees, and resume with a narrower task only after pressure clears. Use a larger disk reserve when the project's known build needs it.

3. Resolve the repository and create the author's sibling worktree:

   ```bash
   repo=/home/howis/git/my-project
   agent_name=codex-auth
   worktree_path=/home/howis/git/my-project-codex-auth
   git -C "$repo" worktree add -b "codex/$agent_name" "$worktree_path" main
   ```

   Reuse a clean existing worktree only when its branch and ownership match the task. Do not create scratch worktrees in `/tmp`.

4. Launch interactive Codex directly:

   ```bash
   kitty @ launch --type=tab --tab-title "$agent_name" --var "hermes_agent=$agent_name" --cwd "$worktree_path" --env PATH=/home/howis/.local/bin:$PATH --hold /usr/bin/codex
   ```

5. Fetch the screen to handle startup or trust prompts, then send the narrow task:

   ```bash
   kitty @ get-text --match "var:hermes_agent=$agent_name" --extent screen
   kitty @ send-text --match "var:hermes_agent=$agent_name" 'Implement the requested change. Stay within the assigned area and run focused changed-area tests only.'
   kitty @ send-key --match "var:hermes_agent=$agent_name" enter
   ```

For a known one-shot task that still needs live visibility, use the same worktree and stable variable:

```bash
kitty @ launch --type=tab --tab-title "$agent_name" --var "hermes_agent=$agent_name" --cwd "$worktree_path" --hold /usr/bin/codex exec --sandbox workspace-write '<concise prompt>'
```

Keep prompts concise. See `references/interactive-spawn-and-prompt.md` only when prompt handoff or trust-screen behavior needs troubleshooting.

## Coordinate and Review

Poll the visible screen without duplicating the agent's work:

```bash
kitty @ get-text --match "var:hermes_agent=$agent_name" --extent screen
```

Use `--extent all` only when needed for scrolled-off context. Send follow-ups with `send-text` followed by `send-key ... enter`.

The coordinator owns scope, handoffs, resource checks, diff inspection, integration, and cleanup. Inspect repository state directly rather than relying only on an agent summary:

```bash
git -C "$worktree_path" status --short
git -C "$worktree_path" diff --stat
git -C "$worktree_path" diff
```

If risk warrants a reviewer, wait for the author to stop editing, then launch at most one review-only tab against the author's worktree. Tell it to inspect the diff, report concrete issues, and rerun only workflows tied to a suspected issue. Do not ask it for a general second implementation or another broad test pass.

## Test Budget

Use one shared test budget for the task:

1. **Author:** run focused tests, type checks, or lint commands covering the changed area. Do not run the full suite by default.
2. **Reviewer, only when warranted:** inspect the diff first. Rerun only issue-specific workflows needed to confirm or disprove a concrete concern.
3. **Coordinator:** run at most one broader integration or full suite, and only at the merge or milestone boundary.

Do not spawn test agents, repeat already-passing broad suites, or run broad checks concurrently. If repository policy requires the author to run a broad suite, that consumes the single broad-run budget; the coordinator does not repeat it. Recheck memory and disk before any broader run; skip or narrow it under pressure and report why.

## Finish and Clean Up

Before removing a completed worktree, confirm both conditions:

```bash
git -C "$worktree_path" status --short
worktree_head=$(git -C "$worktree_path" rev-parse HEAD)
git -C "$repo" merge-base --is-ancestor "$worktree_head" main
```

The first command must be empty and the second must succeed. If the work is dirty or unmerged, preserve the worktree and report it.

After confirming clean and merged:

```bash
kitty @ close-window --match "var:hermes_agent=$agent_name"
git -C "$repo" worktree remove "$worktree_path"
git -C "$repo" worktree prune
```

Use `git worktree remove`; never delete a worktree with `rm -rf`. Keep tabs open until their results have been captured unless the user asks to close them sooner.

## Failure Modes

- If `kitty @ ls` fails, verify the command runs inside kitty or use the configured `KITTY_LISTEN_ON`.
- If Codex shows a trust prompt, handle it before sending the task.
- If a title changes, continue matching `var:hermes_agent=<agent-name>`.
- If quoting becomes fragile, shorten the prompt; do not build giant shell one-liners.
- If resource pressure appears, stop broad work first, preserve useful state, and clean only worktrees proven clean and merged.
