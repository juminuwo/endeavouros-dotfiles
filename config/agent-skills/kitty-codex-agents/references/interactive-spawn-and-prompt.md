# Interactive Codex tab spawn + prompt handoff

Session learning: when the user says "spawn Codex" in a repo, they expect a visible interactive Codex TUI tab first, not a one-shot `codex exec` tab.

Resolve and verify the coordinator window and remote-control endpoint as described in SKILL.md, then launch:

```bash
coordinator_window_id=$KITTY_WINDOW_ID
kitty @ launch --match "window_id:$coordinator_window_id" --type=tab \
  --tab-title codex-auth-interactive \
  --var hermes_agent=codex-auth-interactive \
  --cwd /home/howis/git/driver-shield-codex-auth \
  --env PATH=/home/howis/.local/bin:$PATH \
  --hold \
  /usr/bin/codex --model gpt-6.1-sol --config 'model_reasoning_effort="high"'
```

Verify with `kitty @ ls` that the returned child window belongs to the same OS window as the coordinator. Then verify the Codex TUI is open and ready for input:

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

Close after capturing results when cleanup is authorized, following SKILL.md:

```bash
kitty @ close-window --match 'var:hermes_agent=codex-auth-interactive'
```

Pitfalls:

- Do not interpret "spawn Codex" as `codex exec` unless the user asks for a one-shot/non-interactive run.
- `--hold` leaves a shell after exit; it does not make an exec session interactive. Check the TUI before every follow-up so prose cannot be executed at a shell prompt.
- Do not use untargeted launches or create a new OS window. Focus can change between commands; use the captured coordinator window ID.
- Include `/home/howis/.local/bin` in PATH for spawned Codex tabs so repo tools like `uv` are available to commands Codex runs.
- Match by `--var hermes_agent=...`, never by tab title.
