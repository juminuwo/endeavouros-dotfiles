# Invocation means launch

Session lesson: when Adrian invokes the `kitty-codex-agents` skill alongside a coding request, treat that as an explicit workflow command, not just contextual guidance.

Required behavior:

1. Open a new interactive Codex tab in the current kitty window before doing the coding work yourself.
2. Use the current repo/worktree unless the user names a different path.
3. Set a stable kitty variable: `--var hermes_agent=<agent-name>`.
4. Fetch the tab screen after launch to catch startup/trust prompts.
5. Send the user's task into Codex with `kitty @ send-text` and `kitty @ send-key ... enter`.
6. Continue as coordinator: poll the tab, inspect git diffs directly, run tests directly, and report verified results.

Pitfall this prevents:

A prior session treated the loaded skill as optional background context and began debugging directly. The user corrected this: invoking this skill specifically means they want live-visible Codex opened in a kitty tab for coding work.