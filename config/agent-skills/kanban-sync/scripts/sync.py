#!/usr/bin/env python3
"""Sync Obsidian Kanban board with git commit history across tracked Imoto Labs repos.

Reads `Kanban:` trailers from commits, applies card moves and commit-link appends to
the kanban file, auto-archives Done cards older than the configured threshold.

Trailer grammar:
    Kanban: <ID>                          # link commit, no move
    Kanban: <ID> <column-keyword>         # move card, link commit
    Kanban: new "<title>" #tag1 #tag2 [<column-keyword>]  # create new card

Column keywords: backlog, next, progress, blocked, done. Default for `new` is
"backlog" if column-keyword omitted. The first project tag picks the ID prefix;
if no project tag, the originating repo's tag is used.

Pure stdlib. No external deps.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config.json"
STATE_PATH = SKILL_DIR / "state.json"

COLUMN_KEYWORDS = {
    "backlog": "Backlog",
    "next": "Up Next",
    "progress": "In Progress",
    "blocked": "Blocked / Waiting",
    "done": "Done",
}

# Recognised column headings on the board (order matters for archive walk).
COLUMN_HEADINGS = ["Backlog", "Up Next", "In Progress", "Blocked / Waiting", "Done"]

CARD_LINE_RE = re.compile(r"^- \[( |x)\] (?P<title>.+)$")
ID_IN_TITLE_RE = re.compile(r"^(?P<id>[A-Z]+-\d+) · (?P<rest>.+)$")
DATE_TAG_RE = re.compile(r"@\{(\d{4}-\d{2}-\d{2})\}")
TRAILER_RE = re.compile(r"^Kanban:\s*(?P<rest>.+?)\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Config + state
# ---------------------------------------------------------------------------


def load_config() -> dict:
    with CONFIG_PATH.open() as f:
        return json.load(f)


def load_state() -> dict[str, str]:
    if not STATE_PATH.exists():
        return {}
    with STATE_PATH.open() as f:
        return json.load(f)


def save_state(state: dict[str, str]) -> None:
    with STATE_PATH.open("w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def commits_since(repo: Path, since_sha: str | None) -> list[dict]:
    """Return commits in order (oldest first) since the given SHA, exclusive."""
    range_spec = f"{since_sha}..HEAD" if since_sha else "HEAD"
    # %H short SHA, %ad author date, %B body — separated by NUL between fields,
    # and ASCII RS (0x1e) between commits to keep parsing robust.
    fmt = "%H%x00%h%x00%ad%x00%s%x00%B%x1e"
    try:
        out = git(repo, "log", "--reverse", f"--pretty=format:{fmt}", "--date=short", range_spec)
    except subprocess.CalledProcessError as e:
        # Range invalid (e.g. since_sha not in repo) — fall back to all commits.
        if since_sha:
            print(f"  warning: {since_sha[:8]} not found in repo, falling back to full history")
            out = git(repo, "log", "--reverse", f"--pretty=format:{fmt}", "--date=short")
        else:
            raise e

    commits: list[dict] = []
    for chunk in out.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        parts = chunk.split("\x00")
        if len(parts) < 5:
            continue
        full_sha, short_sha, dt, subject, body = parts[0], parts[1], parts[2], parts[3], parts[4]
        commits.append(
            {
                "sha": full_sha,
                "short": short_sha,
                "date": dt,
                "subject": subject,
                "body": body,
            }
        )
    return commits


# ---------------------------------------------------------------------------
# Trailer parsing
# ---------------------------------------------------------------------------


@dataclass
class TrailerOp:
    raw: str
    project_key: str  # which project owns this commit (from repo)
    commit_sha: str
    commit_short: str
    commit_date: str
    commit_subject: str
    # For existing-card ops:
    card_id: str | None = None
    column: str | None = None  # canonical column name from COLUMN_KEYWORDS
    # For new-card ops:
    new_title: str | None = None
    new_tags: list[str] = field(default_factory=list)


def parse_trailers(commit: dict, project_key: str, project_prefix: str) -> list[TrailerOp]:
    ops: list[TrailerOp] = []
    for match in TRAILER_RE.finditer(commit["body"]):
        rest = match.group("rest").strip()
        op = _parse_one_trailer(rest, project_key, project_prefix, commit)
        if op is not None:
            ops.append(op)
    return ops


def _parse_one_trailer(rest: str, project_key: str, project_prefix: str, commit: dict) -> TrailerOp | None:
    # Form 1: "new \"Title\" #tag1 #tag2 [column]"
    if rest.startswith("new "):
        return _parse_new_trailer(rest, project_key, project_prefix, commit)

    # Form 2: "<ID> [column]"
    parts = rest.split()
    card_id = parts[0]
    if not re.match(r"^[A-Z]+-\d+$", card_id):
        print(f"  warning: trailer in {commit['short']} has malformed ID: {rest!r}")
        return None
    column = None
    if len(parts) > 1:
        column_word = parts[1].lower()
        if column_word in COLUMN_KEYWORDS:
            column = COLUMN_KEYWORDS[column_word]
        else:
            print(f"  warning: unknown column keyword in {commit['short']}: {column_word!r}")
            return None
    return TrailerOp(
        raw=rest,
        project_key=project_key,
        commit_sha=commit["sha"],
        commit_short=commit["short"],
        commit_date=commit["date"],
        commit_subject=commit["subject"],
        card_id=card_id,
        column=column,
    )


def _parse_new_trailer(rest: str, project_key: str, project_prefix: str, commit: dict) -> TrailerOp | None:
    # Strip leading "new " then shlex-split to peel off the quoted title.
    payload = rest[len("new "):].strip()
    try:
        tokens = shlex.split(payload)
    except ValueError as e:
        print(f"  warning: malformed `new` trailer in {commit['short']}: {e}")
        return None
    if not tokens:
        print(f"  warning: empty `new` trailer in {commit['short']}")
        return None
    title = tokens[0]
    tags: list[str] = []
    column = "Backlog"
    for tok in tokens[1:]:
        if tok.startswith("#"):
            tags.append(tok)
        elif tok.lower() in COLUMN_KEYWORDS:
            column = COLUMN_KEYWORDS[tok.lower()]
        else:
            print(f"  warning: unknown token in `new` trailer: {tok!r}")
    return TrailerOp(
        raw=rest,
        project_key=project_key,
        commit_sha=commit["sha"],
        commit_short=commit["short"],
        commit_date=commit["date"],
        commit_subject=commit["subject"],
        new_title=title,
        new_tags=tags,
        column=column,
    )


# ---------------------------------------------------------------------------
# Kanban file model
# ---------------------------------------------------------------------------


@dataclass
class Card:
    checkbox: str  # " " or "x"
    card_id: str | None
    title: str  # the part after "ID · " (or the whole title if no ID)
    body_lines: list[str] = field(default_factory=list)  # indented continuation lines
    column: str = ""  # which column this card lives in (for tracking; not serialised here)

    def render(self) -> list[str]:
        if self.card_id:
            head = f"- [{self.checkbox}] {self.card_id} · {self.title}"
        else:
            head = f"- [{self.checkbox}] {self.title}"
        return [head, *self.body_lines]

    @property
    def date_tag(self) -> date | None:
        m = DATE_TAG_RE.search(self.title)
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None

    @property
    def linked_shas(self) -> set[str]:
        """SHAs (short) that already appear in body lines, for dedup."""
        shas: set[str] = set()
        for line in self.body_lines:
            for m in re.finditer(r"`([0-9a-f]{6,40})`", line):
                shas.add(m.group(1)[:7])
        return shas


@dataclass
class Extras:
    """Non-card content interleaved between cards (e.g. `**Recent**` subheaders)."""
    lines: list[str] = field(default_factory=list)


@dataclass
class Board:
    """In-memory model of the kanban file.

    Per column, items is an ordered mix of Card and Extras, preserving
    the original interleaving (subheaders stay between their cards).
    """

    pre_columns: list[str]
    items: dict[str, list]  # column → list[Card | Extras]
    column_order: list[str]
    post_columns: list[str]

    @property
    def columns(self) -> dict[str, list[Card]]:
        """Cards-only view per column. Mutating this list does NOT mutate items."""
        return {col: [it for it in self.items[col] if isinstance(it, Card)]
                for col in self.column_order}

    def cards_in(self, col: str) -> list[Card]:
        return [it for it in self.items.get(col, []) if isinstance(it, Card)]

    def all_cards(self) -> list[tuple[str, Card]]:
        out = []
        for col in self.column_order:
            for it in self.items[col]:
                if isinstance(it, Card):
                    out.append((col, it))
        return out

    def remove_card(self, card: Card) -> None:
        for col in self.column_order:
            if card in self.items[col]:
                self.items[col].remove(card)
                return

    def append_card(self, col: str, card: Card) -> None:
        if col not in self.items:
            self.items[col] = []
            self.column_order.append(col)
        self.items[col].append(card)
        card.column = col

    def render(self) -> str:
        out: list[str] = list(self.pre_columns)
        # Ensure pre_columns ends cleanly
        while out and out[-1] == "":
            out.pop()
        out.append("")
        for col in self.column_order:
            out.append("")
            out.append(f"## {col}")
            out.append("")
            for it in self.items[col]:
                if isinstance(it, Card):
                    out.extend(it.render())
                    out.append("")
                else:
                    # Extras: emit verbatim, then a blank line if not already trailing
                    out.extend(it.lines)
                    if not (it.lines and it.lines[-1].strip() == ""):
                        out.append("")
        out.append("")
        out.extend(self.post_columns)
        return "\n".join(out).rstrip() + "\n"


def parse_board(text: str) -> Board:
    lines = text.split("\n")
    pre: list[str] = []
    post: list[str] = []
    items: dict[str, list] = {}
    column_order: list[str] = []

    i = 0
    n = len(lines)

    # 1) Pre-columns: everything up to the first known column heading
    while i < n:
        line = lines[i]
        if line.startswith("## ") and line[3:].strip() in COLUMN_HEADINGS:
            break
        pre.append(line)
        i += 1
    if i == n:
        for c in COLUMN_HEADINGS:
            items[c] = []
            column_order.append(c)
        return Board(pre_columns=pre, items=items, column_order=column_order, post_columns=[])

    # 2) Walk columns
    current_col: str | None = None
    pending_extras: list[str] = []
    cur_card: Card | None = None

    def flush_card():
        nonlocal cur_card
        if cur_card is not None:
            while cur_card.body_lines and cur_card.body_lines[-1].strip() == "":
                cur_card.body_lines.pop()
            items[current_col].append(cur_card)
            cur_card = None

    def flush_extras():
        nonlocal pending_extras
        # Trim leading/trailing blank lines from extras blob to avoid huge gaps
        trimmed = list(pending_extras)
        while trimmed and trimmed[0].strip() == "":
            trimmed.pop(0)
        while trimmed and trimmed[-1].strip() == "":
            trimmed.pop()
        if trimmed:
            items[current_col].append(Extras(lines=trimmed))
        pending_extras = []

    while i < n:
        line = lines[i]
        if line.strip().startswith("%% kanban:settings") or line.strip() == "%%":
            if current_col is not None:
                flush_card()
                flush_extras()
            post = lines[i:]
            return Board(pre_columns=pre, items=items, column_order=column_order, post_columns=post)
        if line.startswith("## "):
            heading = line[3:].strip()
            if heading in COLUMN_HEADINGS:
                if current_col is not None:
                    flush_card()
                    flush_extras()
                current_col = heading
                items[current_col] = []
                column_order.append(current_col)
                cur_card = None
                pending_extras = []
                i += 1
                if i < n and lines[i].strip() == "":
                    i += 1
                continue
        if current_col is None:
            pre.append(line)
            i += 1
            continue
        m = CARD_LINE_RE.match(line)
        if m:
            flush_card()
            flush_extras()
            checkbox = m.group(1)
            title = m.group("title")
            id_match = ID_IN_TITLE_RE.match(title)
            if id_match:
                card_id = id_match.group("id")
                rest_title = id_match.group("rest")
            else:
                card_id = None
                rest_title = title
            cur_card = Card(
                checkbox=checkbox, card_id=card_id, title=rest_title,
                body_lines=[], column=current_col,
            )
            i += 1
            continue
        if cur_card is not None:
            if line.startswith("\t") or line.startswith("    "):
                cur_card.body_lines.append(line)
                i += 1
                continue
            if line.strip() == "":
                # Blank line — peek ahead. If the next non-blank line looks like
                # extras (e.g. `**Recent**`), flush card and start collecting extras.
                j = i + 1
                while j < n and lines[j].strip() == "":
                    j += 1
                if j < n and (CARD_LINE_RE.match(lines[j]) or lines[j].startswith("## ") or lines[j].strip().startswith("%%")):
                    flush_card()
                    i = j
                    continue
                else:
                    flush_card()
                    pending_extras.append(line)
                    i += 1
                    continue
            else:
                # Non-indented non-card line — flush card, treat as extras
                flush_card()
                pending_extras.append(line)
                i += 1
                continue
        else:
            pending_extras.append(line)
            i += 1

    if current_col is not None:
        flush_card()
        flush_extras()
    return Board(pre_columns=pre, items=items, column_order=column_order, post_columns=post)


# ---------------------------------------------------------------------------
# Card operations
# ---------------------------------------------------------------------------


def find_card(board: Board, card_id: str) -> tuple[str, Card] | None:
    for col, card in board.all_cards():
        if card.card_id == card_id:
            return col, card
    return None


def next_id_for_prefix(board: Board, prefix: str) -> str:
    nums: list[int] = []
    for _, card in board.all_cards():
        if card.card_id and card.card_id.startswith(f"{prefix}-"):
            try:
                nums.append(int(card.card_id.split("-", 1)[1]))
            except ValueError:
                continue
    next_n = (max(nums) + 1) if nums else 1
    return f"{prefix}-{next_n:03d}"


def append_commit_link(card: Card, op: TrailerOp, github_url: str) -> bool:
    """Append `Commits:` line entry. Return True if added, False if dedup-skipped."""
    if op.commit_short[:7] in card.linked_shas:
        return False

    new_link = f"[`{op.commit_short}`]({github_url}/commit/{op.commit_sha})"
    # Find existing Commits line
    for idx, line in enumerate(card.body_lines):
        stripped = line.strip()
        if stripped.startswith("Commits:"):
            # Append at the front (newest-first)
            indent = line[: len(line) - len(line.lstrip())]
            existing = stripped[len("Commits:"):].strip()
            card.body_lines[idx] = f"{indent}Commits: {new_link} · {existing}".rstrip(" ·")
            return True
    # No existing Commits line — add one
    card.body_lines.append(f"\tCommits: {new_link}")
    return True


def stamp_done_date(card: Card, when: str) -> None:
    """Ensure the title carries an @{date} tag for when it landed in Done."""
    if DATE_TAG_RE.search(card.title):
        return
    card.title = f"{card.title} @{{{when}}}"


def move_card(board: Board, card: Card, target_col: str) -> bool:
    if card.column == target_col:
        return False
    board.remove_card(card)
    board.append_card(target_col, card)
    return True


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


def archive_old_done(board: Board, archive_dir: Path, threshold_days: int, dry_run: bool) -> list[Card]:
    cutoff = date.today() - timedelta(days=threshold_days)
    moved: list[Card] = []
    by_month: dict[str, list[Card]] = {}
    done_items = board.items.get("Done", [])
    new_done_items = []
    for item in done_items:
        if isinstance(item, Card):
            d = item.date_tag
            if d is not None and d < cutoff:
                by_month.setdefault(d.strftime("%Y-%m"), []).append(item)
                moved.append(item)
                continue
        new_done_items.append(item)
    if not moved:
        return moved
    if not dry_run:
        archive_dir.mkdir(parents=True, exist_ok=True)
        for month_key, cards in by_month.items():
            archive_path = archive_dir / f"Kanban Archive {month_key}.md"
            if archive_path.exists():
                existing = archive_path.read_text()
            else:
                existing = (
                    f"---\nkanban-plugin: board\ntype: archive\nmonth: {month_key}\n---\n\n"
                    f"## Archived\n\n"
                )
            new_block: list[str] = []
            for card in cards:
                new_block.extend(card.render())
                new_block.append("")
            archive_path.write_text(existing.rstrip() + "\n\n" + "\n".join(new_block).rstrip() + "\n")
        board.items["Done"] = new_done_items
    return moved


# ---------------------------------------------------------------------------
# Main sync
# ---------------------------------------------------------------------------


def find_repo_for_cwd(config: dict) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
        cwd_repo = Path(result.stdout.strip()).resolve()
    except subprocess.CalledProcessError:
        return None
    for key, proj in config["projects"].items():
        if Path(proj["repo_path"]).resolve() == cwd_repo:
            return key
    return None


def sync_repo(
    project_key: str,
    project: dict,
    board: Board,
    state: dict[str, str],
    dry_run: bool,
    verbose: bool,
) -> dict:
    if not project.get("repo_path"):
        if verbose:
            print(f"  {project_key}: virtual project (no repo), skipping commit scan")
        return {"new_commits": 0}
    repo_path = Path(project["repo_path"])
    if not (repo_path / ".git").exists():
        print(f"  skip {project_key}: repo not present at {repo_path}")
        return {"skipped": True}

    since = state.get(project_key)
    commits = commits_since(repo_path, since)
    if not commits:
        if verbose:
            print(f"  {project_key}: no new commits")
        return {"new_commits": 0}

    stats = {
        "new_commits": len(commits),
        "trailers_processed": 0,
        "cards_moved": 0,
        "commits_linked": 0,
        "cards_created": 0,
        "warnings": 0,
    }

    last_sha = since
    for commit in commits:
        ops = parse_trailers(commit, project_key, project["id_prefix"])
        for op in ops:
            stats["trailers_processed"] += 1
            apply_op(op, project, board, stats)
        last_sha = commit["sha"]

    if not dry_run:
        state[project_key] = last_sha
    return stats


def apply_op(op: TrailerOp, project: dict, board: Board, stats: dict) -> None:
    github_url = project["github_url"]

    if op.new_title is not None:
        # Determine project for new card. Default = current commit's project.
        # If user supplied a project tag, look it up to override the prefix.
        target_project = project
        for tag in op.new_tags:
            for proj in _global_config["projects"].values():
                if proj["tag"] == tag:
                    target_project = proj
                    break
        new_id = next_id_for_prefix(board, target_project["id_prefix"])
        tags = list(op.new_tags)
        if target_project["tag"] not in tags:
            tags.insert(0, target_project["tag"])
        title = f"{op.new_title} {' '.join(tags)}".strip()
        if op.column == "Done":
            title = f"{title} @{{{op.commit_date}}}"
        card = Card(
            checkbox="x" if op.column == "Done" else " ",
            card_id=new_id,
            title=title,
            body_lines=[],
            column=op.column or "Backlog",
        )
        # Optionally include a project page wikilink — best-effort (only if we know one)
        # Skipped for generality; user can edit body after creation.
        target_col = op.column or "Backlog"
        board.append_card(target_col, card)
        append_commit_link(card, op, github_url)
        stats["cards_created"] += 1
        stats["commits_linked"] += 1
        print(f"  + created {new_id} in {target_col}: {op.new_title}")
        return

    found = find_card(board, op.card_id)
    if found is None:
        print(f"  warning: trailer references unknown card {op.card_id} in {op.commit_short}")
        stats["warnings"] += 1
        return
    col, card = found

    moved = False
    if op.column is not None and op.column != col:
        # Move
        moved = move_card(board, card, op.column)
        if moved:
            stats["cards_moved"] += 1
            print(f"  → moved {card.card_id}: {col} → {op.column}")
        if op.column == "Done":
            card.checkbox = "x"
            stamp_done_date(card, op.commit_date)
        elif op.column != "Done":
            # Re-opened
            card.checkbox = " "
    elif op.column == "Done":
        # Already in Done; ensure date stamp
        card.checkbox = "x"
        stamp_done_date(card, op.commit_date)

    if append_commit_link(card, op, project["github_url"]):
        stats["commits_linked"] += 1
        if not moved:
            print(f"  · linked {op.commit_short} → {card.card_id}")


_global_config: dict = {}


def assign_ids(board: Board, config: dict) -> int:
    """Walk all cards without an ID and assign one based on tags. Skip the legend card."""
    project_by_tag = {p["tag"]: p for p in config["projects"].values()}
    assigned = 0
    for _, card in board.all_cards():
        if card.card_id:
            continue
        if "Card legend" in card.title or "Card tag legend" in card.title or "don't move" in card.title.lower():
            continue
        target = None
        for tag, proj in project_by_tag.items():
            if tag in card.title:
                target = proj
                break
        if target is None:
            continue
        new_id = next_id_for_prefix(board, target["id_prefix"])
        card.card_id = new_id
        assigned += 1
        print(f"  + assigned {new_id} ← {card.title[:60]}")
    return assigned


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Obsidian Kanban with git commits.")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    parser.add_argument("--repo", help="Sync only this project key from config")
    parser.add_argument("--no-archive", action="store_true", help="Skip the 30-day archive sweep")
    parser.add_argument("--assign-ids", action="store_true",
                        help="One-shot: assign IDs to existing cards lacking one, then exit")
    parser.add_argument("--quiet", action="store_true", help="Less verbose output")
    parser.add_argument("--verbose", action="store_true", help="More verbose output")
    args = parser.parse_args()

    global _global_config
    _global_config = load_config()
    config = _global_config

    kanban_path = Path(config["kanban_path"])
    if not kanban_path.exists():
        print(f"error: kanban file not found at {kanban_path}", file=sys.stderr)
        return 1

    text = kanban_path.read_text()
    board = parse_board(text)

    if args.assign_ids:
        n = assign_ids(board, config)
        if n == 0:
            print("No cards needed an ID.")
            return 0
        if args.dry_run:
            print(f"\n[dry-run] Would assign {n} IDs.")
            return 0
        kanban_path.write_text(board.render())
        print(f"\nAssigned {n} IDs.")
        return 0

    state = load_state()
    projects = config["projects"]
    if args.repo:
        if args.repo not in projects:
            print(f"error: --repo {args.repo!r} not in config", file=sys.stderr)
            return 1
        projects = {args.repo: projects[args.repo]}

    overall = {"new_commits": 0, "cards_moved": 0, "commits_linked": 0, "cards_created": 0, "warnings": 0}
    for key, proj in projects.items():
        if not args.quiet:
            print(f"== {key} ==")
        stats = sync_repo(key, proj, board, state, args.dry_run, args.verbose or not args.quiet)
        for k in overall:
            if k in stats:
                overall[k] += stats[k]

    archived: list[Card] = []
    if not args.no_archive:
        archive_dir = Path(config["archive_dir"])
        archived = archive_old_done(board, archive_dir, config["archive_after_days"], args.dry_run)

    # WIP soft warning
    in_progress = len(board.cards_in("In Progress"))
    threshold = config.get("wip_warning_threshold", 3)

    if not args.dry_run:
        kanban_path.write_text(board.render())
        save_state(state)

    print()
    print("Summary:")
    print(f"  commits scanned: {overall['new_commits']}")
    print(f"  cards created:   {overall['cards_created']}")
    print(f"  cards moved:     {overall['cards_moved']}")
    print(f"  commits linked:  {overall['commits_linked']}")
    print(f"  cards archived:  {len(archived)}")
    if overall["warnings"]:
        print(f"  warnings:        {overall['warnings']}")
    if in_progress > threshold:
        print(f"\n⚠ WIP warning: {in_progress} cards In Progress (threshold {threshold}). Consider focusing.")
    if args.dry_run:
        print("\n[dry-run] No files written.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
