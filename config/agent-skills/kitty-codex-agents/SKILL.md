---
name: kitty-codex-agents
description: Spawn, monitor, and coordinate live-visible Codex coding agents in kitty tabs using Kitty remote control. Use when the user invokes kitty-codex-agents or kitty-agents, or asks to open, message, inspect, or coordinate Codex agents in kitty; prefer this workflow over tmux on Adrian's machine.
---

# Kitty Codex Agents

Keep the calling agent tab as coordinator and run each Codex agent in a normal kitty tab that the user can watch, enter, and control. Prefer kitty over tmux unless the user asks for tmux or kitty remote control is unavailable.

For an authorized delegated coding task, complete the launch preflight and open
an interactive agent. Do not launch merely to edit this skill, discuss the
workflow, or inspect an existing tab.

Keep GPT-6 Astra as coordinator and explicitly launch GPT-6.1 Sol for execution
and review, unless the user selects another model. Start with `high` effort for
substantial implementation or review; use a lower supported effort for narrow
mechanical work. Verify the actual model and effort in the TUI before sending
work. Independent Kitty sessions do not inherit the coordinator's context or
permissions: include the task's authority boundaries in the brief and inspect
the child permission mode. Do not silently broaden permissions.

For Imoto work, resolve the handbook using the repository instructions and read
`standards/agent-orchestration.md`. It owns role sequencing and evidence rules;
this skill owns Kitty control. Use [the task handoff](references/task-handoff.md)
when assigning work or resuming a task.

## Guardrails

- Default to one narrow author. Add reviewers required by the user or repository. Imoto stateful work needs fresh discovery before implementation and a different fresh verifier afterward. These can run sequentially; concurrency limits do not remove required stages.
- The author normally owns focused testing. Use a separate validator only for a distinct acceptance task with explicit resource ownership and no duplicate broad run.
- Share evidence with its commit, environment, command, and result. Repeat checks only when changes invalidate evidence, a failure needs diagnosis, or a material gap remains.
- Give each author one git worktree. Put worktrees in a disk-backed sibling directory under `/home/howis/git`, never `/tmp`.
- Do not let multiple agents edit the same checkout. A reviewer may inspect the author's worktree only after the author is idle and must return issues to the author rather than edit.
- Launch the interactive Codex TUI. `--hold` only leaves a shell after exit; it does not make `codex exec` interactive. Use one-shot exec only when the user explicitly requests a non-interactive run.
- Pin launches to the coordinator’s existing Kitty OS window, preserving its desktop workspace. Never rely on whichever window happens to be focused.
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

   Capture `coordinator_window_id=$KITTY_WINDOW_ID` before launching anything.
   Confirm this window appears exactly once in `kitty @ ls` and record its
   containing OS-window ID. The remote-control endpoint (`KITTY_LISTEN_ON`, or
   an explicitly verified `--to` address) must belong to that coordinator.
   If the ID is absent or stale, resolve the calling terminal through the
   process tree and Kitty inventory; ask which window only if still ambiguous.
   Do not substitute a focused window, an arbitrary socket, or a new OS window.

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
   # Set base_ref from the approved integration branch, e.g. origin/dev.
   base_sha=$(git -C "$repo" rev-parse --verify "$base_ref^{commit}")
   git -C "$repo" worktree add -b "codex/$agent_name" "$worktree_path" "$base_sha"
   ```

   Resolve and record the integration branch and current base before running
   the example; never assume `main`. Reuse a clean worktree only when its branch
   and ownership match the task. Assign shared database, browser, and port
   ownership separately; a worktree does not isolate them.

4. Launch interactive Codex directly:

   ```bash
   kitty @ launch --match "window_id:$coordinator_window_id" --type=tab --tab-title "$agent_name" --var "hermes_agent=$agent_name" --cwd "$worktree_path" --env PATH=/home/howis/.local/bin:$PATH --hold /usr/bin/codex --model gpt-6.1-sol --config 'model_reasoning_effort="high"'
   ```

5. Fetch the screen to handle startup or trust prompts, then send the narrow task:

   ```bash
   kitty @ get-text --match "var:hermes_agent=$agent_name" --extent screen
   kitty @ send-text --match "var:hermes_agent=$agent_name" 'Implement the requested change. Stay within the assigned area and run focused changed-area tests only.'
   kitty @ send-key --match "var:hermes_agent=$agent_name" enter
   ```

After launch, use the returned window ID and `kitty @ ls` to verify the child
is in the coordinator's recorded OS window. Inspect its screen for the actual
Codex TUI and ready input prompt before sending work. An open terminal or held
shell is not sufficient. If placement is wrong, close only that new unused tab
and correct targeting before retrying. Do not move the user's existing windows
or switch desktop workspaces to conceal a misplaced launch.

Keep prompts concise. See `references/interactive-spawn-and-prompt.md` only when prompt handoff or trust-screen behavior needs troubleshooting.

## Coordinate and Review

Poll the visible screen without duplicating the agent's work:

```bash
kitty @ get-text --match "var:hermes_agent=$agent_name" --extent screen
```

Use `--extent all` only when needed for scrolled-off context. Before each follow-up, verify the agent TUI is still running; never send task prose to a held shell after Codex exits. Send follow-ups with `send-text` followed by `send-key ... enter`.

The coordinator owns scope, handoffs, resource checks, diff inspection, integration, and cleanup. Inspect repository state directly rather than relying only on an agent summary:

```bash
git -C "$worktree_path" status --short
git -C "$worktree_path" diff --stat "$base_sha" HEAD
git -C "$worktree_path" diff "$base_sha" HEAD
git -C "$worktree_path" diff --cached
git -C "$worktree_path" diff
```

Before verification, confirm the author is idle and pin the review commit.
Give the reviewer the approved contract, raw changes, and neutral test evidence,
not the author's defense. Return findings to the author. Re-review the revised
commit after fixes; invalidate the evidence affected by those fixes.

## Test Budget

Use one shared test budget for the task:

1. **Author:** run focused tests, type checks, or lint commands covering the changed area. Do not run the full suite by default.
2. **Reviewer, only when warranted:** inspect the diff first. Rerun only issue-specific workflows needed to confirm or disprove a concrete concern.
3. **Coordinator:** assign a broader integration or full suite to one owner or CI at the merge or milestone boundary.

Do not run broad checks concurrently or repeat valid passing evidence solely
because a different role wants its own run. Relevant code, dependency, schema,
configuration, or integration changes can require another run. Record why.
Recheck memory and disk first; if required checks cannot run, report the gap
rather than treating a narrower run as sufficient.

## Finish and Clean Up

Use [close-out-work](../close-out-work/SKILL.md) for the final audit and any
authorized cleanup. Check the actual integration target, including squash-merge
evidence when needed. Report `dev` integration separately from release to `main`.

Keep task tabs until results are captured. Before closing a specific tagged tab
or stopping a service, confirm it belongs to this completed task and is idle.
Preserve dirty, untracked, uncertain, or still-used artifacts. Use normal
`git worktree remove`, never forced removal or `rm -rf`.

## Failure Modes

- If `kitty @ ls` fails, verify the command runs inside kitty or use the configured `KITTY_LISTEN_ON`.
- If Codex shows a trust prompt, handle it before sending the task.
- If a title changes, continue matching `var:hermes_agent=<agent-name>`.
- If quoting becomes fragile, shorten the prompt; do not build giant shell one-liners.
- If resource pressure appears, stop broad work first, preserve useful state, and clean only worktrees proven clean and merged.
