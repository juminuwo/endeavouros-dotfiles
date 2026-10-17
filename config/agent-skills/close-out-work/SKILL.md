---
name: close-out-work
description: Audit delivery and clean up completed task worktrees, branches, and owned processes. Use for "have we merged to dev?", "is the workspace clean?", "any hanging branches or worktrees?", or explicit post-merge cleanup. Status questions inspect only; cleanup never implies a release or discarding unfinished work.
---

# Close out work

Report what landed, what remains, and what can be removed without losing work.
Keep integration, release, and housekeeping as separate outcomes.

## Establish scope and evidence

Resolve the repository, completed task, intended integration branch, and any
separate release branch from the request and repository workflow. For DMP,
integration commonly targets `dev`; `main` is a separate release. Never infer
the target from the remote default branch. Reuse earlier authorization: a
status question is read-only; "clean up after this merge" authorizes removal
of this task's proven integrated, inactive local artifacts.

Inspect Git's worktree inventory, not guessed directory names. Run the bundled
stdlib helper using its absolute source path (resolve relative to this skill):

```sh
python scripts/audit_work.py --repo /path/to/repo --target origin/dev --release origin/main
```

The helper emits JSON with worktrees, local and remote-tracking branches, upstream divergence,
integration ancestry, and optional release divergence. It does not fetch,
delete, query PRs, or determine whether an agent is active. It labels results
as local-ref evidence; a candidate is not permission to delete.

For current hosted status, fetch the relevant remote refs without pruning and
rerun. If fetch fails, report stale/unknown remote status; do not claim current
integration or remove artifacts based on stale evidence. Inspect the task PR
when needed, including exact head, base, merge commit, and merged state.
Do not infer success from a closed PR, missing remote branch, green CI, or a
previous agent's report.

## Classify each task artifact

- **Retain:** primary checkout, current session checkout, protected/integration/
  release branches, locked worktrees, active agents or services, open PRs,
  dirty tracked files, untracked files, or work owned by another task.
- **Verify:** missing/inaccessible worktrees, unknown ownership, detached work,
  ignored files, stale refs, or changes not proven integrated.
- **Candidate:** the current head is integrated into the intended target and
  the worktree is clean. Still verify task ownership and inactivity.

Check ignored files before removal too: ignored does not mean disposable.
Preserve local credentials, unique evidence, and fixtures. Remove only identified
regenerable build artifacts when needed and authorized; never blanket-clean.
Use Kitty inventory and task handoffs to establish ownership and activity.
A sleeping process or old session timestamp alone does not prove abandonment.
Do not scan unrelated projects' transcripts.

Ancestry proves a normal merge. For squash/rebase, require a merged PR against
the intended target, exact reviewed head matching the current branch tip, and
the resulting merge commit reachable from the refreshed target. Inspect any
later commits and compare the task diff if provenance remains ambiguous.
A branch name, patch similarity, or closed PR alone is insufficient. When proof
is incomplete, retain it and state the missing evidence.

## Perform authorized cleanup

Recheck the exact path, head, status including untracked/ignored files, target
commit, and inactivity immediately before removal. Stop the task's own services
and close only its identified idle agent tabs after capturing results. Never
kill by a broad process name or stop shared services someone else owns.

Use normal `git worktree remove` on the verified path. Never use `--force`,
`git clean`, `reset --hard`, or `rm -rf` to make removal succeed. If removal
refuses, inspect and retain the artifact until its cause is resolved.

After removal, delete a task's local branch with `git branch -d` only after
independently proving integration into the intended target; Git may otherwise
check a different upstream. Do not rely on `-d` alone as the merge proof. If
squash/rebase history causes refusal, retain the branch and report why. Forced
branch deletion needs explicit authorization for that exact ref, verified
integration, and a recorded recovery commit. Do not repeatedly ask for this
when the user has already authorized the exact action in the current task.

Remote branch deletion requires explicit authorization naming the task branch
or an already approved remote cleanup scope. Verify its current tip has no new
work and no open or stacked PR depends on it; preserve protected branches.
Do not merge, push code, release to `main`, mutate Linear, reset/reseed databases,
or delete Storage as housekeeping. Cleanup cannot expand release authority.

Prune only verified stale worktree registrations after inspection. Never remove
registrations for temporarily unavailable disks or locked worktrees.

## Verify and report

Rerun the audit after cleanup. Report:

- integration target and whether the task's current head landed, with evidence;
- release branch relation separately, including ahead/behind counts;
- local versus remote freshness and any unpushed commits;
- removed worktrees, branches, and owned services;
- retained artifacts with a concrete reason and next action, if any.

Do not equate a clean current checkout with a clean repository. If the user
asked only for status, present the verified cleanup candidates without deleting.
