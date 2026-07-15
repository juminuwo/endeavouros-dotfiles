#!/usr/bin/env python3
"""Scan local Imoto-Labs git repos for wiki auto-update context.

Default mode prints one JSON payload and writes a last-scan snapshot. If
nothing needs the LLM, it prints {"wakeAgent": false} as the final line.

After a successful wiki update, run with --mark-reported to move current heads
into the durable reported state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

GIT_ROOT = Path("/home/howis/git")
VAULT_PROJECTS = Path("/home/howis/Documents/online-personal/Imoto Labs/Projects")
STATE_DIR = Path("/home/howis/.hermes/state")
STATE_PATH = STATE_DIR / "imoto-wiki-autoupdate.json"
LAST_SCAN_PATH = STATE_DIR / "imoto-wiki-last-scan.json"
REMOTE_RE = re.compile(r"github\.com[:/]Imoto-Labs/([^\s/]+?)(?:\.git)?(?:\s|$)", re.I)
EXCLUDED_REPOS = {"imoto-labs-wiki"}

ALIASES = {
    "business-scout": "Business Scout",
    "customer-tracking-portal": "Customer Tracking Portal",
    "driver-management-platform": "Driver Management Platform",
    "driver-shield": "Driver Shield 360",
    "route-optimisation": "Route Optimization",
    "predictive-maintenance": "Predictive Maintenance",
    "logistics-pricing": "Logistics Pricing",
    "logistics-pricing-engine": "Logistics Pricing",
    "imoto-event-sourcing-agent": "Event Sourcing Agent",
    "event-sourcing-agent": "Event Sourcing Agent",
    "financial-dd-skill": "Financial DD Skill",
}

SAFE_SOURCE_CANDIDATES = [
    "README.md",
    "docs/README.md",
    "package.json",
    "pyproject.toml",
    "go.mod",
    "Cargo.toml",
    "AGENTS.md",
]


def now_iso() -> str:
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def run(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        return subprocess.check_output(cmd, cwd=str(cwd) if cwd else None, text=True, stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError:
        return ""


def git(repo: Path, args: list[str]) -> str:
    return run(["git", "-C", str(repo), *args])


def is_git_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    return git(path, ["rev-parse", "--is-inside-work-tree"]) == "true"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def normalize_remote_repo(remote_line: str) -> str | None:
    m = REMOTE_RE.search(remote_line)
    if not m:
        return None
    return m.group(1).removesuffix(".git")


def project_pages() -> list[Path]:
    if not VAULT_PROJECTS.exists():
        return []
    return sorted(p for p in VAULT_PROJECTS.rglob("*.md") if p.name != "POC Status.md")


def title_to_project_page(title: str) -> Path:
    return VAULT_PROJECTS / title / f"{title}.md"


def page_for_repo(repo_slug: str, local_path: Path, remote_urls: list[str], pages: list[Path]) -> dict[str, Any]:
    alias_title = ALIASES.get(repo_slug)

    # 1. Alias path exists.
    if alias_title:
        alias_page = title_to_project_page(alias_title)
        if alias_page.exists():
            return {"status": "matched", "method": "alias", "title": alias_title, "path": str(alias_page)}

    # 2. Page text contains exact GitHub remote or local path.
    needles = [str(local_path), f"Imoto-Labs/{repo_slug}"]
    needles.extend(remote_urls)
    for page in pages:
        try:
            text = page.read_text(errors="ignore")
        except Exception:
            continue
        if any(n and n in text for n in needles):
            title = page.stem if page.parent == VAULT_PROJECTS else page.parent.name
            return {"status": "matched", "method": "content", "title": title, "path": str(page)}

    # 3. Slug title path exists.
    guessed = " ".join(part.capitalize() for part in repo_slug.replace("_", "-").split("-"))
    guessed_page = title_to_project_page(guessed)
    if guessed_page.exists():
        return {"status": "matched", "method": "slug-title", "title": guessed, "path": str(guessed_page)}

    return {"status": "unmapped", "method": "none", "title": alias_title or guessed, "path": None}


def dirty_hash(status_short: str) -> str:
    if not status_short:
        return ""
    return hashlib.sha256(status_short.encode()).hexdigest()[:16]


def commit_lines(repo: Path, previous_head: str | None, cap: int = 12) -> tuple[list[str], str]:
    fmt = "%h %cd %s"
    if previous_head:
        # Use range only if previous head is known to this repo.
        if git(repo, ["cat-file", "-e", f"{previous_head}^{{commit}}"]) == "":
            lines = git(repo, ["log", f"{previous_head}..HEAD", "--date=short", f"--pretty=format:{fmt}", f"-{cap}"])
            if lines:
                return lines.splitlines(), f"{previous_head}..HEAD"
    lines = git(repo, ["log", "--date=short", f"--pretty=format:{fmt}", f"-{cap}"])
    return (lines.splitlines() if lines else []), "latest"


def scan() -> dict[str, Any]:
    state = load_json(STATE_PATH, {"repos": {}})
    pages = project_pages()
    repos: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for repo in sorted(GIT_ROOT.iterdir() if GIT_ROOT.exists() else []):
        if not is_git_repo(repo):
            continue

        remotes_lines = git(repo, ["remote", "-v"]).splitlines()
        remote_slugs = [slug for line in remotes_lines if (slug := normalize_remote_repo(line))]
        if not remote_slugs:
            continue

        # Prefer origin's slug if present; otherwise first Imoto slug.
        origin_slug = None
        for line in remotes_lines:
            if line.startswith("origin"):
                origin_slug = normalize_remote_repo(line)
                if origin_slug:
                    break
        repo_slug = origin_slug or remote_slugs[0]
        repo_key = f"Imoto-Labs/{repo_slug}"
        branch = git(repo, ["branch", "--show-current"])
        head = git(repo, ["rev-parse", "HEAD"])
        latest = git(repo, ["log", "--date=short", "--pretty=format:%h %cd %s", "-1"])
        status_short = git(repo, ["status", "--short"])
        safe_sources = [p for p in SAFE_SOURCE_CANDIDATES if (repo / p).exists()]

        entry_base = {
            "repo_key": repo_key,
            "repo_slug": repo_slug,
            "local_name": repo.name,
            "path": str(repo),
            "branch": branch,
            "head": head,
            "latest_commit": latest,
            "dirty": bool(status_short),
            "dirty_hash": dirty_hash(status_short),
            "status_short": status_short.splitlines()[:20],
            "remotes": remotes_lines[:6],
            "safe_sources": safe_sources,
        }

        if repo_slug in EXCLUDED_REPOS or repo.name in EXCLUDED_REPOS:
            excluded.append({**entry_base, "reason": "publisher repo, not product source"})
            continue

        previous = state.get("repos", {}).get(repo_key, {})
        previous_head = previous.get("reported_head")
        commits, commit_range = commit_lines(repo, previous_head)
        mapping = page_for_repo(repo_slug, repo, remotes_lines, pages)
        unmapped = mapping["status"] == "unmapped"
        head_changed = head and head != previous_head
        previously_reported_unmapped = previous.get("reported_unmapped_title") == mapping.get("title")
        needs_update = bool(head_changed or (unmapped and not previously_reported_unmapped))

        repos.append({
            **entry_base,
            "previous_reported_head": previous_head,
            "head_changed": bool(head_changed),
            "commit_range": commit_range,
            "commits_to_report": commits if head_changed else [],
            "wiki_mapping": mapping,
            "wiki_page": mapping.get("path"),
            "needs_update": needs_update,
        })

    changed = [r for r in repos if r["needs_update"] and r["wiki_page"]]
    unmapped = [r for r in repos if r["needs_update"] and not r["wiki_page"]]
    payload = {
        "schema": "imoto-wiki-autoupdate/v1",
        "generated_at": now_iso(),
        "git_root": str(GIT_ROOT),
        "vault_projects": str(VAULT_PROJECTS),
        "state_path": str(STATE_PATH),
        "last_scan_path": str(LAST_SCAN_PATH),
        "repo_count": len(repos),
        "changed_count": len(changed),
        "unmapped_count": len(unmapped),
        "wake_agent": bool(changed or unmapped),
        "changed_repos": changed,
        "unmapped_repos": unmapped,
        "repos": repos,
        "excluded_repos": excluded,
    }
    return payload


def mark_reported() -> dict[str, Any]:
    scan_payload = load_json(LAST_SCAN_PATH, None)
    if not scan_payload:
        raise SystemExit(f"No last scan found at {LAST_SCAN_PATH}")
    state = load_json(STATE_PATH, {"repos": {}})
    state.setdefault("repos", {})
    marked = []
    for repo in scan_payload.get("repos", []):
        key = repo["repo_key"]
        state["repos"].setdefault(key, {})
        state["repos"][key].update({
            "reported_head": repo.get("head"),
            "reported_branch": repo.get("branch"),
            "reported_at": now_iso(),
            "reported_wiki_page": repo.get("wiki_page"),
            "reported_unmapped_title": repo.get("wiki_mapping", {}).get("title") if not repo.get("wiki_page") else None,
        })
        marked.append(key)
    state["last_mark_reported_at"] = now_iso()
    write_json(STATE_PATH, state)
    return {"marked_count": len(marked), "marked_repos": marked, "state_path": str(STATE_PATH)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="do not write the last-scan snapshot")
    parser.add_argument("--mark-reported", action="store_true", help="mark repos from last scan as reported after a successful wiki update")
    args = parser.parse_args()

    if args.mark_reported:
        print(json.dumps(mark_reported(), indent=2, sort_keys=True))
        return 0

    payload = scan()
    if not args.dry_run:
        write_json(LAST_SCAN_PATH, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload.get("wake_agent"):
        print(json.dumps({"wakeAgent": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
