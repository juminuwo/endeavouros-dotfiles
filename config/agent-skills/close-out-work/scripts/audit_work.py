#!/usr/bin/env python3
"""Read local Git evidence for task close-out. Never fetch or delete."""

import argparse
import json
import os
from pathlib import Path
import subprocess


def git(repo, *args):
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, env=env,
        encoding="utf-8", errors="surrogateescape",
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout


def commit(repo, ref):
    return git(repo, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").strip()


def divergence(repo, left, right):
    a, b = git(repo, "rev-list", "--left-right", "--count", left + "..." + right).split()
    return {"left_only": int(a), "right_only": int(b)}


def worktrees(repo):
    rows = []
    row = {}
    for field in git(repo, "worktree", "list", "--porcelain", "-z").split("\0"):
        if not field:
            if row:
                rows.append(row)
                row = {}
            continue
        key, _, value = field.partition(" ")
        row[key] = value
    if row:
        rows.append(row)
    return rows


def status(repo):
    fields = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored=matching").split("\0")
    entries = []
    i = 0
    while i < len(fields):
        value = fields[i]
        i += 1
        if not value:
            continue
        entry = {"status": value[:2], "path": value[3:]}
        if "R" in value[:2] or "C" in value[:2]:
            entry["original_path"] = fields[i]
            i += 1
        entries.append(entry)
    return entries


def audit(repo, target, release=None):
    target_sha = commit(repo, target)
    rows = []
    inventory = worktrees(repo)
    for index, item in enumerate(inventory):
        path = item["worktree"]
        row = {"path": path, "head": item.get("HEAD"), "branch": item.get("branch"),
               "primary": index == 0, "activity": "unverified"}
        reasons = []
        if index == 0:
            reasons.append("primary-checkout")
        if Path(path).resolve() == Path(repo).resolve():
            reasons.append("requested-checkout")
        branch = item.get("branch", "").removeprefix("refs/heads/")
        if branch and (branch in ("main", "master", "dev") or
                       any(ref == branch or ref.endswith("/" + branch)
                           for ref in (target, release or ""))):
            reasons.append("integration-or-protected-branch")
        for flag in ("locked", "prunable", "bare", "detached"):
            if flag in item:
                reasons.append(flag)
        try:
            row["files"] = status(path)
            if row["files"]:
                reasons.append("local-files-require-review")
            row["head_not_in_target"] = int(git(repo, "rev-list", "--count", target_sha + ".." + commit(repo, item["HEAD"])).strip())
            row["integrated_by_ancestry"] = row["head_not_in_target"] == 0
            if not row["integrated_by_ancestry"]:
                reasons.append("integration-unproven")
        except (RuntimeError, KeyError) as error:
            row["error"] = str(error)
            reasons.append("inspection-failed")
        row["classification"] = "retain-or-verify" if reasons else "candidate-pending-ownership-and-activity"
        row["reasons"] = reasons
        rows.append(row)

    branches = []
    fmt = "%(refname)%00%(objectname)%00%(upstream)"
    for line in git(repo, "for-each-ref", "--format=" + fmt, "refs/heads/").splitlines():
        ref, sha, upstream = line.split("\0")
        row = {"ref": ref, "head": sha, "upstream": upstream or None,
               "worktrees": [r["path"] for r in rows if r["branch"] == ref],
               "versus_target": divergence(repo, sha, target_sha)}
        if upstream:
            try:
                row["versus_upstream"] = divergence(repo, sha, commit(repo, upstream))
            except RuntimeError:
                row["upstream_status"] = "missing-local-ref"
        branches.append(row)
    remote_branches = []
    fmt = "%(refname)%00%(objectname)%00%(symref)"
    for line in git(repo, "for-each-ref", "--format=" + fmt, "refs/remotes/").splitlines():
        ref, sha, symbolic = line.split("\0")
        if not symbolic:
            remote_branches.append({"ref": ref, "head": sha,
                                    "versus_target": divergence(repo, sha, target_sha)})
    result = {"repository": str(Path(repo).resolve()), "target": target,
              "target_commit": target_sha, "freshness": "local refs only; no fetch performed",
              "worktrees": rows, "branches": branches, "remote_tracking_branches": remote_branches,
              "counts_meaning": "left_only is work/target ahead; right_only is comparison ahead"}
    if release:
        release_sha = commit(repo, release)
        result["release"] = {"ref": release, "commit": release_sha,
                             "target_vs_release": divergence(repo, target_sha, release_sha)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--target", required=True, help="Explicit integration ref, e.g. origin/dev")
    parser.add_argument("--release", help="Optional separate release ref, e.g. origin/main")
    args = parser.parse_args()
    try:
        result = audit(args.repo, args.target, args.release)
    except (RuntimeError, OSError) as error:
        parser.exit(2, f"audit failed: {error}\n")
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
