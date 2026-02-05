---
name: update-projects
description: Update the Obsidian Git Projects dashboard with current status of all repositories in ~/git/. Use when user wants to refresh project tracking, check git status across projects, or update the projects page.
allowed-tools: Bash,Read,Write,Edit
---

# Update Git Projects Dashboard

This skill scans all git repositories in `~/git/` and updates the Obsidian projects dashboard at `~/Documents/online-personal/Personal/Projects/Git Projects.md`.

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
    last_commit=$(git -C "$dir" log --oneline -1 2>/dev/null || echo "No commits")
    branch=$(git -C "$dir" branch --show-current 2>/dev/null)

    # Check for uncommitted changes
    staged=$(git -C "$dir" diff --cached --stat 2>/dev/null | tail -1)
    unstaged=$(git -C "$dir" diff --stat 2>/dev/null | tail -1)
    untracked=$(git -C "$dir" ls-files --others --exclude-standard 2>/dev/null | wc -l)

    echo "PROJECT: $name"
    echo "BRANCH: $branch"
    echo "LAST_COMMIT: $last_commit"
    echo "STAGED: $staged"
    echo "UNSTAGED: $unstaged"
    echo "UNTRACKED: $untracked"
    echo "---"
  fi
done
```

### Step 2: Categorize Projects

Use this categorization (adjust based on what you find):

**Work - Customer Portal:**
- customer-tracking-portal
- predictive-maintenance (related to customer-tracking-portal)
- route-optimisation (related to customer-tracking-portal)

**Work - Finance / DD:**
- andre_tryee_finances
- scmt_finances
- financial-dd-skill

**Personal / Hobby:**
- personal_keyboard
- advent-of-code-2025
- dog-instagram-poster
- endeavouros-dotfiles
- linux-utils
- badminton-computer-vision

**Forks / Checkouts:**
- cvat
- InstaPy
- qmk_firmware
- tapestry-skills-for-claude-code
- data

### Step 3: Read Current Dashboard

```bash
cat "/home/howis/Documents/online-personal/Personal/Projects/Git Projects.md"
```

### Step 4: Update the Dashboard

Use the Edit tool to update the Obsidian file at:
`/home/howis/Documents/online-personal/Personal/Projects/Git Projects.md`

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

### Work - Customer Portal
| Project | Status | Notes |
|---------|--------|-------|
| [[customer-tracking-portal]] | Active/Paused/Maintenance | Brief note |
| [[predictive-maintenance]] | Active/Paused/Maintenance | Brief note |
| [[route-optimisation]] | Active/Paused/Maintenance | Brief note |

### Work - Finance / DD
| Project | Status | Notes |
|---------|--------|-------|
| [[project-name]] | Active/Paused/Maintenance | Brief note |

### Personal / Hobby
[... personal projects ...]

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
