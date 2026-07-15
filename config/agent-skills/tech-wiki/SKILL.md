---
name: tech-wiki
description: Research a technology from a URL and create a wiki entry in the Obsidian Technologies directory. Use when adding a new technology to the personal knowledge base.
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, WebFetch, WebSearch, Agent]
---

# Tech Wiki Entry Generator

Research a technology from a provided URL and create a structured wiki entry in the Obsidian Technologies directory.

## Usage

- `/tech-wiki https://docs.example.com/` — research and create entry (name inferred from page)
- `/tech-wiki https://github.com/org/repo FastAPI` — research with explicit name
- `/tech-wiki https://arxiv.org/abs/... Mamba` — works with papers, docs, repos, landing pages

## Input

Use the URL supplied in the user's request. Treat any accompanying technology name as an explicit name; otherwise infer it from the source.

If no URL is provided, ask the user for one.

## Configuration

- **Technologies directory**: `/home/howis/Documents/online-personal/Resources/Technologies/`
- **Index file**: `/home/howis/Documents/online-personal/Resources/Technologies/Technologies.md`

## Workflow

### Step 1: Fetch the Source URL

Use WebFetch to retrieve the content at the provided URL. This is the primary source material.

If the URL is a GitHub repo, also fetch the README. If it's an arxiv paper, fetch the abstract page.

### Step 2: Research the Technology

Use WebSearch to find additional context:
- Official documentation
- GitHub repository (if not already the source)
- Key blog posts or announcements
- How the technology compares to alternatives

Gather enough to write authoritatively about what it is, how it works, and where it fits.

### Step 3: Check for Existing Entry

Read the index file and check if an entry already exists:

```bash
ls /home/howis/Documents/online-personal/Resources/Technologies/
```

If an entry already exists for this technology, read it and update it rather than creating a duplicate. Tell the user you're updating an existing entry.

### Step 4: Determine Metadata

Figure out:

- **category**: Which section of the index does this belong in? Look at the existing categories in `Technologies.md` (3D Reconstruction, Computer Vision, Dev Tools, Infrastructure, Other). Use an existing category if it fits, or create a new one if needed.
- **status**: Default to `watching` for new entries (we're researching it, not using it yet). If the user specifies otherwise, honour that.
- **projects**: Leave as empty list `[]` unless the user mentions a specific project connection.
- **filename**: Use the technology's proper name as the filename (e.g., `FastAPI.md`, `3D Gaussian Splatting.md`). Match the capitalisation and spacing the project itself uses.

### Step 5: Write the Entry

Create the file at `/home/howis/Documents/online-personal/Resources/Technologies/{Name}.md` with this structure:

```markdown
---
category: {category}
status: {status}
updated: {TODAY's date YYYY-MM-DD}
projects: [{projects}]
---

#reference

## What It Is
{1-2 paragraphs. What is this technology? Who made it? When? What problem does it solve? What's the elevator pitch? Be specific — mention the language, paradigm, key differentiator.}

## How It Works
{1-3 paragraphs. Technical explanation of the core mechanism. Not a tutorial — explain the architecture, key concepts, or algorithm at a level useful for deciding whether and how to use it. Include trade-offs (speed vs accuracy, simplicity vs flexibility, etc).}

## Why It's Interesting
{1-2 paragraphs. Why did we bookmark this? What potential does it have for our work? How does it compare to what we currently use? Be honest — if it's just "looks cool, worth tracking" that's fine.}

## Links
{3-6 links. Always include:
- Official docs
- GitHub repo (if open source)
- 1-2 other useful resources (paper, announcement blog post, good tutorial)
Format as markdown links, not bare URLs.}

## See Also
{Obsidian wikilinks to related entries that already exist in the Technologies directory. Check what's in the directory first. Only link to entries that actually exist. Omit this section entirely if there are no related entries.}
```

**Section notes:**
- Use "How We Use It" instead of "Why It's Interesting" if `status` is `using` and there's a project connection. Follow the style of the YOLOv8 and COLMAP entries — describe the specific role in the specific project.
- The `#reference` tag goes right after frontmatter, before any headings.
- Keep it concise but substantive. The YOLOv8 entry is the minimum bar. The COLMAP entry shows how detailed it can get for tools we actually use.
- Write in a technical but accessible voice. No marketing language. No "powerful" or "cutting-edge".

### Step 6: Update the Index

Read the current `Technologies.md` and add the new entry to the appropriate category table. Follow the existing format:

```
| [[{Name}]] | {status} | {one-line relevance description} |
```

If the category doesn't exist, add a new section following the existing pattern (## heading, then table).

### Step 7: Report

Tell the user:
- What file was created/updated
- The category and status assigned
- A one-line summary of what was written
- Any related entries that already existed (useful for the user to check cross-references)

## Quality Standards

**Good entry characteristics:**
- Explains the technology to someone technical but unfamiliar with it
- Distinguishes it from similar tools/libraries (e.g., "unlike X, this does Y")
- Includes honest assessment of maturity, adoption, trade-offs
- Links are real and useful, not filler

**Avoid:**
- Marketing copy or hype ("revolutionary", "game-changing")
- Vague descriptions that could apply to anything ("a tool for building applications")
- Tutorial content (save that for a separate note if needed)
- Speculation about features — only describe what the technology actually does today
