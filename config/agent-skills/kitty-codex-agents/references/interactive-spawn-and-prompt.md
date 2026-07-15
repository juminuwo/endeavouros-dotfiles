# Interactive Codex tab spawn + prompt handoff

Session learning: when the user says "spawn Codex" in a repo, they expect a visible interactive Codex TUI tab first, not a one-shot `codex exec` tab.

Verified workflow on Adrian's machine:

```bash
kitty @ launch --type=tab \
  --tab-title codex-tests-interactive \
  --var hermes_agent=codex-tests-interactive \
  --cwd /home/howis/git/driver-shield \
  --env PATH=/home/howis/.local/bin:$PATH \
  --hold \
  /usr/bin/codex
```

Then verify the TUI is open:

```bash
kitty @ get-text --match 'var:hermes_agent=codex-tests-interactive' --extent screen
```

Then send the task prompt:

```bash
kitty @ send-text --match 'var:hermes_agent=codex-tests-interactive' 'Run the full test suite for this repository using the documented command: uv run pytest. Do not modify files. Let the tests run to completion. Report the final pytest summary, including any failing tests or errors if present.'
kitty @ send-key --match 'var:hermes_agent=codex-tests-interactive' enter
```

Monitor:

```bash
kitty @ get-text --match 'var:hermes_agent=codex-tests-interactive' --extent all
```

Close only when the user asks:

```bash
kitty @ close-window --match 'var:hermes_agent=codex-tests-interactive'
```

Pitfalls:

- Do not interpret "spawn Codex" as `codex exec` unless the user asks for a one-shot/non-interactive run.
- For one-shot tasks, use `codex exec --sandbox workspace-write`; interactive TUI spawning should just launch `/usr/bin/codex`.
- Include `/home/howis/.local/bin` in PATH for spawned Codex tabs so repo tools like `uv` are available to commands Codex runs.
- Match by `--var hermes_agent=...`, never by tab title.
