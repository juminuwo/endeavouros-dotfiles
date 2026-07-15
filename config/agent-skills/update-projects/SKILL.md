---
name: update-projects
description: Update the Obsidian Git Projects dashboard with current status of all repositories in ~/git/. Use when user wants to refresh project tracking, check git status across projects, or update the projects page.
allowed-tools: Bash,Read,Write,Edit
---

# Update Git Projects Dashboard

This skill scans all git repositories in `~/git/` and updates the Obsidian projects dashboard at `~/Documents/online-personal/Projects/Git Projects.md`.

## When to Use This Skill

Activate this skill when the user:
- Says `/update-projects`
- Wants to refresh their project tracking page
- Asks "what's the status of my projects?"
- Wants to update the Obsidian dashboard
- Asks to check uncommitted work across repos

## Workflow

### Step 1: Scan All Git Repositories

Run the following to get status of all repos:

```bash
for dir in /home/howis/git/*/; do
  if [ -d "$dir/.git" ]; then
    name=$(basename "$dir")
    last_commit=$(git -C "$dir" log -1 --format='%h %s' 2>/dev/null || echo "No commits")
    last_commit_date=$(git -C "$dir" log -1 --format='%cI' 2>/dev/null || true)
    branch=$(git -C "$dir" branch --show-current 2>/dev/null)

    # Check for uncommitted changes
    staged=$(git -C "$dir" diff --cached --stat 2>/dev/null | tail -1)
    unstaged=$(git -C "$dir" diff --stat 2>/dev/null | tail -1)
    untracked=$(git -C "$dir" ls-files --others --exclude-standard 2>/dev/null | wc -l)

    echo "PROJECT: $name"
    echo "BRANCH: $branch"
    echo "LAST_COMMIT: $last_commit"
    echo "LAST_COMMIT_DATE: $last_commit_date"
    echo "STAGED: $staged"
    echo "UNSTAGED: $unstaged"
    echo "UNTRACKED: $untracked"
    echo "---"
  fi
done
```

### Step 2: Read Current Dashboard

```bash
cat "/home/howis/Documents/online-personal/Projects/Git Projects.md"
```

### Step 3: Categorize Projects

Build categories from current evidence instead of a hardcoded repository list:

1. Preserve the existing dashboard category for repositories already listed unless their purpose clearly changed.
2. For a new repository, inspect its remote and the first useful section of its `README.md` or project manifest.
3. Put external upstream checkouts and forks under `Forks / Checkouts`.
4. Add clearly owned repositories to the most specific existing work or personal category supported by their documentation.
5. Put uncertain repositories under `Uncategorised` and report them; do not guess from the repository name alone.
6. Remove entries that no longer have a checkout only when the dashboard is intended to track current local repositories; otherwise mark them missing.

### Step 4: Update the Dashboard

Use the Edit tool to update the Obsidian file at:
`/home/howis/Documents/online-personal/Projects/Git Projects.md`

Update these sections:
1. **Project tables** - Update status and notes based on recent commits
2. **Uncommitted Work callout** - List repos with uncommitted changes (exclude forks/checkouts)
3. **Project Notes** - Update with latest commit messages and pending work

### Step 5: Summarize Changes

After updating, provide a brief summary:
- Number of projects scanned
- Projects with uncommitted changes
- Most recently active projects (by commit date)
- Any new projects detected

## Output Format

The dashboard should maintain this structure:

```markdown
# Git Projects Dashboard

Quick overview of all projects in `~/git/`

---

## Active Projects

### Existing category name
| Project | Status | Notes |
|---------|--------|-------|
| [[project-name]] | Active/Paused/Maintenance | Brief note |

### Uncategorised
| Project | Status | Notes |
|---------|--------|-------|
| [[new-project]] | Active/Paused/Maintenance | Needs categorisation |

---

## Forks / Checkouts
| Project | Purpose |
|---------|---------|
| project-name | Brief description |

---

## Quick Status

> [!warning] Uncommitted Work
> - `repo-name` - description of changes
> (Only show your own projects here, not forks/checkouts)

---

## Project Notes

### project-name
- Last commit: commit message
- [ ] Pending tasks
```

## Tips

- Use `Active` for projects with recent commits (last 2 weeks)
- Use `Paused` for projects with older commits
- Use `Maintenance` for config/dotfile repos
- Keep notes concise - one line per project
- Link to existing Obsidian notes where relevant (e.g., `[[Keyboard]]`)
- The `> [!warning]` syntax creates an Obsidian callout box
