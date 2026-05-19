---
name: kitty-codex-agents
description: Use when spawning, monitoring, or coordinating Codex agents in kitty tabs with live user visibility and Hermes remote control. Prefer this over tmux for interactive spawned-agent workflows on Adrian's machine.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [codex, kitty, agents, multi-agent, remote-control]
    related_skills: [codex, hermes-agent]
---

# Kitty Codex Agents

## Overview

Use kitty tabs as the live control surface for spawned Codex agents. The main Hermes session remains the coordinator, while each Codex agent runs in a normal kitty tab the user can switch to, watch, and type into directly.

This workflow is preferred over tmux for this user. Use tmux only when the user explicitly asks for it or kitty remote control is unavailable.

Core idea:

```text
main Hermes tab       = coordinator
codex-auth tab        = Codex in repo/worktree A
codex-ui tab          = Codex in repo/worktree B
codex-tests tab       = Codex in repo/worktree C
```

Hermes can spawn the tabs, send messages into them, fetch their screen output, and verify filesystem/git/test results independently.

## When to Use

Use this skill when the user asks to:

- spawn a Codex agent
- open a Codex agent in kitty
- send a message to a Codex tab
- check what a Codex tab is doing
- coordinate multiple Codex agents
- run live-visible coding agents without taking over the current Hermes session

Do not use this for:

- quick hidden subtasks where `delegate_task` is enough
- scheduled/durable background jobs; use cron instead
- non-interactive one-shot shell tasks that do not benefit from live visibility

## Prerequisites

Verify the tools and remote control before relying on the workflow:

```bash
command -v kitty
kitty --version
command -v codex
codex --version
kitty @ ls
```

Expected:

- `kitty @ ls` returns JSON describing the current kitty windows/tabs.
- Codex runs inside a git repository. For scratch work, create a temporary git repo first.

If `kitty @ ls` fails outside a kitty window, the environment may need `KITTY_LISTEN_ON` or a configured `listen_on` in `kitty.conf`. From inside an active kitty session, remote control normally works through the controlling terminal.

## Naming and Targeting

Always set a stable kitty user variable when launching an agent:

```text
--var hermes_agent=<agent-name>
```

Use that variable for later targeting:

```text
--match 'var:hermes_agent=<agent-name>'
```

Do not rely on tab titles alone. Titles can be changed by Codex, shell integration, prompts, or the user.

Good names:

```text
codex-auth
codex-ui
codex-tests
codex-review-123
```

## Spawn an Interactive Codex Tab

Use this when the user wants a live Codex session they can enter and drive:

```bash
kitty @ launch --type=tab --tab-title '<agent-name>' --var hermes_agent=<agent-name> --cwd <repo-path> --hold zsh -lc 'exec codex'
```

Example:

```bash
kitty @ launch --type=tab --tab-title codex-auth --var hermes_agent=codex-auth --cwd /home/howis/git/my-project --hold zsh -lc 'exec codex'
```

Notes:

- The command prints the new kitty window id.
- `--hold` keeps the tab open after Codex exits so the final output is visible.
- Codex may first ask whether the repository is trusted.
- If the trust prompt appears, the user can answer in the tab, or Hermes can send the appropriate choice if instructed.

## Spawn a One-Shot Codex Task Tab

Use this when the task is known up front but the user still wants live visibility:

```bash
kitty @ launch --type=tab --tab-title '<agent-name>' --var hermes_agent=<agent-name> --cwd <repo-path> --hold zsh -lc 'exec codex exec --full-auto "$TASK"'
```

For short prompts, direct quoting is fine:

```bash
kitty @ launch --type=tab --tab-title codex-auth --var hermes_agent=codex-auth --cwd /home/howis/git/my-project --hold zsh -lc 'exec codex exec --full-auto "Fix the auth bug, run tests, and summarize the diff"'
```

For complex prompts, avoid giant shell one-liners. Prefer writing the prompt to a temporary file and launching a small wrapper command that reads it:

```bash
prompt_file=$(mktemp)
printf '%s\n' 'Fix the auth bug, run tests, and summarize the diff.' > "$prompt_file"
kitty @ launch --type=tab --tab-title codex-auth --var hermes_agent=codex-auth --cwd /home/howis/git/my-project --hold zsh -lc "exec codex exec --full-auto \"$(cat "$prompt_file")\""
```

If quoting becomes fragile, create a short script file and launch the script instead of embedding the whole task in the `kitty @ launch` command.

## Send a Message to a Codex Tab

Send text, then press Enter:

```bash
kitty @ send-text --match 'var:hermes_agent=<agent-name>' '<message>'
kitty @ send-key --match 'var:hermes_agent=<agent-name>' enter
```

Example:

```bash
kitty @ send-text --match 'var:hermes_agent=codex-auth' 'Please run the auth tests now.'
kitty @ send-key --match 'var:hermes_agent=codex-auth' enter
```

For multi-line messages, prefer sending a concise instruction or using the clipboard/user handoff. Long pasted prompts can be brittle in terminal UIs.

## Fetch Output from a Codex Tab

Fetch the current visible screen:

```bash
kitty @ get-text --match 'var:hermes_agent=<agent-name>' --extent screen
```

Fetch screen plus scrollback:

```bash
kitty @ get-text --match 'var:hermes_agent=<agent-name>' --extent all
```

Example:

```bash
kitty @ get-text --match 'var:hermes_agent=codex-auth' --extent screen
```

Use `screen` for quick status checks. Use `all` when you need prior context or final results that scrolled off screen.

## Multi-Agent Coding Workflow

For parallel coding work, isolate file edits with git worktrees:

```bash
git worktree add -b codex/auth /tmp/codex-auth main
git worktree add -b codex/ui /tmp/codex-ui main
git worktree add -b codex/tests /tmp/codex-tests main
```

Then spawn one Codex tab per worktree:

```bash
kitty @ launch --type=tab --tab-title codex-auth --var hermes_agent=codex-auth --cwd /tmp/codex-auth --hold zsh -lc 'exec codex'
kitty @ launch --type=tab --tab-title codex-ui --var hermes_agent=codex-ui --cwd /tmp/codex-ui --hold zsh -lc 'exec codex'
kitty @ launch --type=tab --tab-title codex-tests --var hermes_agent=codex-tests --cwd /tmp/codex-tests --hold zsh -lc 'exec codex'
```

Hermes should coordinate the agents:

1. Assign one narrow task per tab.
2. Poll tab output with `kitty @ get-text`.
3. Send follow-ups with `kitty @ send-text` and `send-key enter`.
4. Inspect git diffs directly from Hermes.
5. Run tests directly from Hermes.
6. Merge or cherry-pick useful work only after verification.

Do not let multiple agents edit the same checkout unless the task is read-only.

## Closing Agent Tabs

The user can close tabs manually. If asked to close a tab from Hermes, target by variable:

```bash
kitty @ close-window --match 'var:hermes_agent=<agent-name>'
```

Only close tabs when the user asks or the task lifecycle clearly requires cleanup.

## Common Pitfalls

1. **Trust prompt blocks the first message.** Codex may ask whether the repository is trusted. Fetch the screen after spawning and handle the prompt before sending task instructions.

2. **Matching by title is brittle.** Codex or shell integration may rename the tab/window. Always launch with `--var hermes_agent=<agent-name>` and match on that variable.

3. **Editing the same checkout from multiple agents causes conflicts.** Use one git worktree per active coding agent.

4. **Long prompt quoting breaks shell commands.** For complex prompts, write a temporary file or script instead of embedding a giant prompt in a single `zsh -lc` string.

5. **`--hold` matters.** Without `--hold`, a one-shot task tab may close before the user can read final output.

6. **Current Hermes session does not become the Codex session.** The Codex tab is independent. Hermes can send/read via kitty remote control, but the user can also interact directly.

7. **Remote control may require kitty context.** `kitty @` is most reliable from inside an existing kitty window. Outside kitty, use `KITTY_LISTEN_ON` or configure `listen_on`.

## Verification Checklist

After setting up or using this workflow, verify:

- [ ] `kitty @ ls` works.
- [ ] Spawn command returns a kitty window id.
- [ ] The new tab is visible in kitty.
- [ ] `kitty @ get-text --match 'var:hermes_agent=<agent-name>' --extent screen` returns the Codex screen.
- [ ] `kitty @ send-text` plus `kitty @ send-key ... enter` reaches Codex.
- [ ] Codex replies and Hermes can fetch the reply.
- [ ] For coding tasks, changes are isolated in a repo or worktree and verified with git diff/tests.

## Proven Test Case

This workflow was validated on Adrian's machine with:

```text
kitty 0.46.2
codex-cli 0.131.0
```

A tab launched with:

```bash
kitty @ launch --type=tab --tab-title codex-test --var hermes_agent=codex-test --cwd /home/howis/git/endeavouros-dotfiles --hold zsh -lc 'exec codex'
```

Hermes then sent:

```bash
kitty @ send-text --match 'var:hermes_agent=codex-test' 'hi'
kitty @ send-key --match 'var:hermes_agent=codex-test' enter
```

and fetched Codex's reply with:

```bash
kitty @ get-text --match 'var:hermes_agent=codex-test' --extent screen
```
