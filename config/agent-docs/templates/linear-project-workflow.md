# Linear Workflow

Status: Project overlay

This repo follows the shared Imoto Labs Linear convention in `~/git/docs/linear-workflow.md`. This file records only project-specific Linear details.

## Current Linear Shape

Workspace/team:

- Team: `Imoto Labs - Tech`
- Project: `<Linear project name>`
- Project URL: `<Linear project URL>`

Use this hierarchy:

```text
Project -> Milestone -> Issue
```

Current milestones:

- `<Milestone 1>` - `<short purpose>`
- `<Milestone 2>` - `<short purpose>`

## Durable Project Records

Linear is execution tracking. Durable decisions and context for this project belong in:

- `<repo decision doc>`
- `<repo runbook or requirements doc>`
- `<repo research/notes doc>`

Do not use Linear comments as the durable place for architecture, infrastructure, security, privacy, compliance, product-scope, or hardware decisions.

## Project-Specific Rules

- `<Sensitive-data rule, if any>`
- `<Verification or test expectation, if any>`
- `<Legacy ID or migration rule, if any>`
- `<Project-specific milestone/label exception, if any>`

## Agent Notes

When the user asks for Linear Project, Milestone, or Issue work, or names a Linear issue as the active task:

1. Read `~/git/docs/linear-workflow.md`.
2. Read this project overlay.
3. Read the Linear issue before implementation.
4. Keep implementation scoped to the issue.
5. Add commit links, verification, and a completion comment before moving work to `Done`.
