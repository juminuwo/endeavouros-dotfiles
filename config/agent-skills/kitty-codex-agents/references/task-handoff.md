# Task handoff

Write a short brief to a task-specific file and send the agent its absolute
path. Scratch briefs may live outside Git; durable decisions belong in the
product repository. Never include secrets or real driver data.

```text
Task / revision:
Role and requested model / effort:
Outcome and acceptance conditions:
Approved decisions / pending owner decisions:
Repository / worktree / owned responsibility:
Base commit / integration branch / review commit if applicable:
Shared services, ports, and mutation ownership:
Allowed actions / forbidden operations:
Existing verification: commit, environment, command, result, evidence path:
Required focused checks and missing evidence:
Return result at:
Stop when:
```

Tell writers that other agents may be working in the repository; preserve
their changes. Do not give a reviewer the author's defense or discovery
conclusions. A review result identifies the exact commit, findings, checks,
and limitations. An author result includes changed behavior, commit, checks,
open decisions, and confirmation that editing has stopped.

For a follow-up, confirm the TUI is alive, increment the revision, name the
superseded instruction, and obtain acknowledgement before dependent work.
For resumption, reconcile the latest brief with Git and owned services; reuse
valid evidence instead of repeating completed investigation.
