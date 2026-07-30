# Interactive Codex tab spawn + prompt handoff

Session learning: when the user says "spawn Codex" in a repo, they expect a visible interactive Codex TUI tab first, not a one-shot `codex exec` tab.

Verified workflow on Adrian's machine:

```bash
kitty @ launch --type=tab \
  --tab-title codex-auth-interactive \
  --var hermes_agent=codex-auth-interactive \
  --cwd /home/howis/git/driver-shield-codex-auth \
  --env PATH=/home/howis/.local/bin:$PATH \
  --hold \
  /usr/bin/codex
```

Then verify the TUI is open:

```bash
kitty @ get-text --match 'var:hermes_agent=codex-auth-interactive' --extent screen
```

Then send the task prompt:

```bash
kitty @ send-text --match 'var:hermes_agent=codex-auth-interactive' 'Implement the requested auth change in this worktree. Run only the focused auth tests and report the diff and test result.'
kitty @ send-key --match 'var:hermes_agent=codex-auth-interactive' enter
```

Monitor:

```bash
kitty @ get-text --match 'var:hermes_agent=codex-auth-interactive' --extent all
```

Close only when the user asks:

```bash
kitty @ close-window --match 'var:hermes_agent=codex-auth-interactive'
```

Pitfalls:

- Do not interpret "spawn Codex" as `codex exec` unless the user asks for a one-shot/non-interactive run.
- For one-shot tasks, use `codex exec --sandbox workspace-write`; interactive TUI spawning should just launch `/usr/bin/codex`.
- Include `/home/howis/.local/bin` in PATH for spawned Codex tabs so repo tools like `uv` are available to commands Codex runs.
- Match by `--var hermes_agent=...`, never by tab title.
