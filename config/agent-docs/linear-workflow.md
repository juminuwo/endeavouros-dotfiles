# Shared Linear Workflow

Status: Active cross-project convention

This is the shared Linear operating convention for Imoto Labs projects. Project-specific overlays live in each repo at `docs/technical/linear-workflow.md` when that repo actively uses Linear.

Linear is execution tracking. Repo docs are the durable decision log. Issues should point to docs, PRs, commits, and decisions; they should not replace architecture notes, runbooks, compliance notes, or research records.

## Default Shape

Use this hierarchy unless a project overlay explicitly says otherwise:

```text
Project -> Milestone -> Issue
```

- Use one Linear Project per active product or substantial workstream.
- Use Project Milestones for stages, workstreams, migration groups, or customer feedback rounds.
- Use Issues for concrete outcomes that can be implemented, reviewed, and verified.
- Avoid broad placeholder issues such as "Backend", "Frontend", or "Compliance".
- Use parent/sub-issues only when the parent is itself a concrete deliverable and the sub-issues are real implementation steps.

Recommended project issue view:

- Group by: Status.
- Optional subgroup or filter: Project Milestone.
- Filter out: Canceled for day-to-day execution views.

## Statuses

Use statuses consistently:

- `Backlog` - plausible future work, not committed as near-term execution.
- `Todo` - approved or near-term work that is ready to pick up.
- `In Progress` - someone is actively working it.
- `In Review` - implementation is ready for review, testing, merge, or owner acceptance.
- `Done` - committed, verified, and no immediate follow-up is required.
- `Canceled` - intentionally not doing it, duplicate, superseded, or migrated away.

Move status only when it reflects reality.

## Writing Issues

An issue should describe one useful outcome, not an area of responsibility.

Good titles are imperative and specific:

```text
Create initial Supabase migration baseline
Scaffold the Next.js portal baseline
Add driver profile list page
```

Avoid broad titles:

```text
Database work
Frontend
Compliance stuff
```

Use this body shape:

```md
## Context

Why this matters and what decision, doc, customer input, bug, or source it comes from.

## Scope

- Concrete thing to build or change.
- Relevant repo paths.
- External systems involved, if any.

## Acceptance

- Observable condition that proves this is done.
- Test, command, screenshot, or review condition where possible.
- Security, privacy, hardware, or data expectation if relevant.

## Out of Scope

- Nearby work that should not be pulled into this issue.

## Links

- Repo docs, PRs, commits, customer notes, infra links, or prior issues if useful.
```

Keep acceptance criteria short. Three to six bullets is usually enough. If an issue needs a large checklist, split it.

## Issue Size

Prefer issues that can be completed in one focused session to two working days.

Split the issue when:

- Acceptance describes multiple user-visible outcomes.
- It touches unrelated systems.
- It cannot be reviewed without a long explanation.
- It would remain `In Progress` for more than a few days.

## Milestones And Labels

Use milestones for coherent workstreams, stages, or feedback rounds. Each active issue should normally belong to exactly one milestone.

Use labels lightly:

- `Feature` for new capability.
- `Bug` for incorrect behavior.
- `Improvement` for cleanup, hardening, docs, or non-blocking enhancement.

Do not create custom labels until there is repeated need.

## Branches, Commits, And PRs

When working from a Linear issue, include the issue ID in branch names, meaningful commits, and PR titles.

Branch names:

```text
imo-8-scaffold-nextjs-portal-baseline
adrianliu95/imo-102-harden-full-flow-protocol-failure-coverage
```

Linear-generated branch names are acceptable. Keep the `IMO-123` identifier somewhere in the branch.

Commit subjects:

```text
IMO-8 scaffold Next.js portal baseline
IMO-102 harden full-flow protocol boundaries
```

For multi-line commit messages, add a footer:

```text
Linear: IMO-8
```

Pull request titles:

```text
IMO-8 Scaffold Next.js portal baseline
```

Pull request body:

```md
Linear: IMO-8

## Summary

- What changed.

## Verification

- Commands or checks run.
```

Use closing magic words such as `Fixes IMO-8` only when the PR fully completes the issue and automation is configured to move the issue correctly. For partial work, prefer `Linear: IMO-8` or `Refs IMO-8`.

## Agent Workflow

Agents must not create, update, or link Linear resources unless the user explicitly asks for Linear Project, Milestone, or Issue work, or the user names a Linear issue as the current task.

When a Linear issue is active:

1. Read the issue before making code or doc changes.
2. Read the project overlay at `docs/technical/linear-workflow.md` when present.
3. Keep implementation scoped to the issue.
4. Include the issue ID in branch names and commits when committing.
5. Move status only when it reflects reality.
6. Add a short Linear comment only for useful execution context, such as a blocker, PR link, verification note, or completion handoff.

Do not use Linear comments as the durable place for architecture, infrastructure, security, privacy, compliance, product-scope, or hardware decisions. Update the relevant repo doc instead.

## Completing Issues

When marking an issue complete, do the completion handoff in Linear before or at the same time as the status change:

1. Identify the relevant commit or commits.
2. Add GitHub commit URLs to the issue, usually in a completion comment.
3. Post a short completion comment with summary, verification, and commit links.
4. Move the issue to `Done` only when the work is committed, verified, and ready to push or already pushed.

If one commit completes multiple Linear issues, add that same commit link and completion comment to each issue.

If an issue is canceled, archived, superseded, or migrated without an implementation commit, post a short comment explaining why no commit is linked.

Completion comment template:

```md
Completed.

Summary:
- ...

Verification:
- `npm run test:standard`
- ...

Commits:
- https://github.com/Imoto-Labs/<repo>/commit/<sha>
```

## Creating New Issues

For larger planning work:

1. Draft the proposed issues in chat or docs first.
2. Ask for approval before adding them to Linear.
3. Create only the next actionable set of issues.
4. Assign each issue to one milestone.
5. Link issues to relevant repo docs, PRs, commits, and decisions where useful.
6. Keep ownership clear; only one person or agent should actively drive an issue at a time.

Do not bulk-import a whole requirements document as Linear issues. Create issues when work is close enough to be actionable. Bulk imports are reserved for explicit migration work where preserving history is the goal.

## New Project Bootstrap

When a repo starts using Linear:

1. Create a short project overlay from `~/git/docs/templates/linear-project-workflow.md`.
2. Add a pointer to the overlay in the repo `AGENTS.md`.
3. Create the Linear Project and a small milestone set.
4. Create only the next few actionable issues unless the user explicitly asks for a history migration.
5. Keep durable decisions in repo docs from the start.

## References

- Linear custom views: https://linear.app/docs/custom-views
- Linear project milestones: https://linear.app/docs/project-milestones
- Linear GitHub integration: https://linear.app/docs/github-integration
- Linear delete/archive issues: https://linear.app/docs/delete-archive-issues
- Linear MCP: https://linear.app/docs/mcp
