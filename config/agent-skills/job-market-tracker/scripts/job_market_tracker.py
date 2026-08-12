#!/usr/bin/env python3
"""Private UK job-market collector and dashboard renderer (stdlib only)."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "job-market/v1"
RUBRIC_VERSION = "2026-08-11-v1"
DEFAULT_ROOT = Path("/home/howis/Documents/online-personal/Personal/Career/Job Market")
DEFAULT_CREDENTIALS = Path("/home/howis/.config/job-market-tracker/credentials.json")
DEFAULT_CACHE = Path("/home/howis/.cache/job-market-tracker")
USER_STATES = {"unseen", "reviewed", "shortlisted", "applied", "dismissed"}
PRIORITIES = {"A", "B", "C", "Excluded"}
COMPONENT_LIMITS = {
    "role_fit": 25,
    "technical_alignment": 25,
    "delivery_ownership": 20,
    "domain_alignment": 15,
    "logistics": 15,
}
SOURCE_RANK = {"greenhouse": 3, "lever": 3, "reed": 2, "adzuna": 1}
QUERY_FAMILIES = [
    "Senior Applied Scientist",
    "Senior Machine Learning Engineer",
    "Senior Data Scientist",
    "Lead Data Scientist",
    "Machine Learning Scientist",
    "Computer Vision Engineer",
    "Edge AI Engineer",
    "Applied AI Scientist",
]
ROLE_RE = re.compile(
    r"\b(machine learning|applied scientist|research scientist|data scientist|computer vision|edge ai|applied ai|ml engineer|ai scientist)\b",
    re.I,
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_date(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000
        return datetime.fromtimestamp(number, timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(text)
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    except ValueError:
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return None


def clean_html(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def norm(value: Any) -> str:
    text = clean_html(value).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def short_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def canonical_url(value: Any) -> str:
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(str(value))
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if not k.casefold().startswith(("utm_", "lever-source"))]
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc.casefold(), parsed.path.rstrip("/"), urllib.parse.urlencode(query), ""))


def redact(text: str) -> str:
    text = re.sub(r"(?i)(app[_ -]?key|api[_ -]?key|authorization)([\"'=:\s]+)[^\s,}\"]+", r"\1\2[REDACTED]", text)
    return re.sub(r"(?i)basic\s+[A-Za-z0-9+/=]{12,}", "Basic [REDACTED]", text)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Invalid JSON at {path}: {exc}") from exc


def write_json(path: Path, value: Any, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)
    if mode is not None:
        path.chmod(mode)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(value, encoding="utf-8")
    os.replace(temp, path)


class Tracker:
    def __init__(self, root: Path, credentials: Path, cache: Path, opener: Any = None) -> None:
        self.root = root
        self.credentials_path = credentials
        self.cache = cache
        self.data_dir = root / "data"
        self.state_path = self.data_dir / "job-listings.json"
        self.history_path = self.data_dir / "scan-history.jsonl"
        self.config_path = root / "job-market-config.json"
        self.profile_path = root / "match-profile.json"
        self.dashboard_path = root / "Job Market Dashboard.md"
        self.opener = opener or urllib.request.urlopen
        self.state = self._load_state()
        self.config = load_json(self.config_path, {})
        self.profile = load_json(self.profile_path, {})

    def _load_state(self) -> dict[str, Any]:
        default = {
            "schema_version": SCHEMA_VERSION,
            "rubric_version": RUBRIC_VERSION,
            "updated_at": None,
            "jobs": {},
            "source_health": {},
            "last_run": None,
            "workflow_run": None,
        }
        state = load_json(self.state_path, default)
        state.setdefault("jobs", {})
        state.setdefault("source_health", {})
        state.setdefault("last_run", None)
        state.setdefault("workflow_run", None)
        return state

    def save(self) -> None:
        self.state["schema_version"] = SCHEMA_VERSION
        self.state["rubric_version"] = RUBRIC_VERSION
        self.state["updated_at"] = iso_now()
        write_json(self.state_path, self.state)

    def fetch_json(self, url: str, headers: dict[str, str] | None = None, retries: int = 2) -> Any:
        request = urllib.request.Request(url, headers={"User-Agent": "Adrian-Job-Market-Tracker/1.0", **(headers or {})})
        for attempt in range(retries + 1):
            try:
                with self.opener(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                code = exc.code
                exc.close()
                if code in {429, 500, 502, 503, 504} and attempt < retries:
                    time.sleep(0.5 * (2**attempt))
                    continue
                if code in {401, 403}:
                    raise RuntimeError(f"authentication rejected (HTTP {code})") from exc
                raise RuntimeError(f"HTTP {code}") from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt < retries:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise RuntimeError(redact(str(exc))) from exc
        raise RuntimeError("request failed")

    def _credentials(self) -> dict[str, Any]:
        if not self.credentials_path.exists():
            return {}
        if self.credentials_path.stat().st_mode & 0o077:
            raise RuntimeError(f"credentials file permissions must be 0600: {self.credentials_path}")
        return load_json(self.credentials_path, {})

    def collect_adzuna(self, creds: dict[str, Any]) -> list[dict[str, Any]]:
        auth = creds.get("adzuna", {})
        if not auth.get("app_id") or not auth.get("app_key"):
            raise KeyError("missing Adzuna app_id/app_key")
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        base = "https://api.adzuna.com/v1/api/jobs/gb/search/1"
        for query in self.config.get("queries", QUERY_FAMILIES):
            params = {
                "app_id": auth["app_id"],
                "app_key": auth["app_key"],
                "results_per_page": 50,
                "what_phrase": query,
                "sort_by": "date",
                "max_days_old": 30,
                "content-type": "application/json",
            }
            payload = self.fetch_json(base + "?" + urllib.parse.urlencode(params))
            for item in payload.get("results", []):
                normalized = self._normalize_adzuna(item)
                if normalized["source_id"] not in seen and self._ats_candidate(normalized):
                    results.append(normalized)
                    seen.add(normalized["source_id"])
        return results

    def _normalize_adzuna(self, item: dict[str, Any]) -> dict[str, Any]:
        salary = salary_dict(item.get("salary_min"), item.get("salary_max"), "GBP")
        return raw_job(
            source="adzuna",
            source_id=item.get("id"),
            title=item.get("title"),
            company=(item.get("company") or {}).get("display_name"),
            location=(item.get("location") or {}).get("display_name"),
            url=item.get("redirect_url"),
            description=item.get("description"),
            posted_at=item.get("created"),
            expires_at=None,
            workplace=None,
            employment=item.get("contract_time") or item.get("contract_type"),
            salary=salary,
            full_description=False,
        )

    def collect_reed(self, creds: dict[str, Any]) -> list[dict[str, Any]]:
        key = (creds.get("reed") or {}).get("api_key")
        if not key:
            raise KeyError("missing Reed api_key")
        token = base64.b64encode((key + ":").encode()).decode()
        headers = {"Authorization": "Basic " + token}
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        detail_limit = int(self.config.get("limits", {}).get("reed_detail_requests", 80))
        base = "https://www.reed.co.uk/api/1.0/search"
        for query in self.config.get("queries", QUERY_FAMILIES):
            params = {"keywords": query, "locationName": "United Kingdom", "resultsToTake": 100}
            payload = self.fetch_json(base + "?" + urllib.parse.urlencode(params), headers=headers)
            for item in payload.get("results", []):
                preview = self._normalize_reed(item)
                if not preview["source_id"] or preview["source_id"] in seen or not self._ats_candidate(preview):
                    continue
                detail = item
                if item.get("jobId") and len(results) < detail_limit:
                    try:
                        detail = self.fetch_json(f"https://www.reed.co.uk/api/1.0/jobs/{item['jobId']}", headers=headers)
                    except RuntimeError:
                        detail = item
                results.append(self._normalize_reed({**item, **detail}))
                seen.add(preview["source_id"])
        return results

    def _normalize_reed(self, item: dict[str, Any]) -> dict[str, Any]:
        description = item.get("jobDescription") or item.get("jobDescriptionHtml") or item.get("jobDescriptionSnippet")
        return raw_job(
            source="reed",
            source_id=item.get("jobId"),
            title=item.get("jobTitle"),
            company=item.get("employerName"),
            location=item.get("locationName"),
            url=item.get("jobUrl"),
            description=description,
            posted_at=item.get("date"),
            expires_at=item.get("expirationDate"),
            workplace=None,
            employment=item.get("contractType") or item.get("employmentType"),
            salary=salary_dict(item.get("minimumSalary"), item.get("maximumSalary"), item.get("currency") or "GBP"),
            full_description=len(clean_html(description)) >= 500,
        )

    def collect_greenhouse(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for board in self.config.get("ats", {}).get("greenhouse", []):
            token = board["token"]
            url = f"https://boards-api.greenhouse.io/v1/boards/{urllib.parse.quote(token)}/jobs?content=true"
            payload = self.fetch_json(url)
            for item in payload.get("jobs", []):
                normalized = self._normalize_greenhouse(item, board.get("company"))
                if self._ats_candidate(normalized):
                    results.append(normalized)
        return results

    def _normalize_greenhouse(self, item: dict[str, Any], company: str | None) -> dict[str, Any]:
        return raw_job(
            source="greenhouse",
            source_id=item.get("id"),
            title=item.get("title"),
            company=company,
            location=(item.get("location") or {}).get("name"),
            url=item.get("absolute_url"),
            description=item.get("content"),
            posted_at=item.get("updated_at"),
            expires_at=None,
            workplace=None,
            employment=None,
            salary=None,
            full_description=True,
        )

    def collect_lever(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for board in self.config.get("ats", {}).get("lever", []):
            site = board["site"]
            url = f"https://api.lever.co/v0/postings/{urllib.parse.quote(site)}?mode=json"
            payload = self.fetch_json(url)
            if not isinstance(payload, list):
                raise RuntimeError(f"Lever board {site} returned a non-list payload")
            for item in payload:
                normalized = self._normalize_lever(item, board.get("company"))
                if self._ats_candidate(normalized):
                    results.append(normalized)
        return results

    def _normalize_lever(self, item: dict[str, Any], company: str | None) -> dict[str, Any]:
        categories = item.get("categories") or {}
        lists = "\n".join(clean_html(block.get("content")) for block in item.get("lists", []) if isinstance(block, dict))
        description = "\n".join(filter(None, [clean_html(item.get("descriptionPlain") or item.get("description")), lists]))
        return raw_job(
            source="lever",
            source_id=item.get("id"),
            title=item.get("text"),
            company=company,
            location=categories.get("location") or ", ".join(categories.get("allLocations") or []),
            url=item.get("hostedUrl"),
            description=description,
            posted_at=item.get("createdAt"),
            expires_at=None,
            workplace=item.get("workplaceType"),
            employment=categories.get("commitment"),
            salary=None,
            full_description=True,
        )

    def _ats_candidate(self, item: dict[str, Any]) -> bool:
        if not ROLE_RE.search(item.get("title", "")):
            return False
        location = norm(item.get("location"))
        allowed = self.config.get("location_terms", ["united kingdom", "uk", "london", "remote", "cambridge", "oxford", "milton keynes", "birmingham", "manchester", "bristol", "europe"])
        return not location or any(norm(term) in location for term in allowed)

    def _record_health(self, name: str, status: str, count: int = 0, error: str | None = None) -> None:
        old = self.state["source_health"].get(name, {})
        consecutive = old.get("consecutive_failures", 0) + 1 if status == "failed" else 0
        self.state["source_health"][name] = {
            "status": status,
            "last_run": iso_now(),
            "count": count,
            "error": redact(error or "") or None,
            "consecutive_failures": consecutive,
        }

    def pending_count(self) -> int:
        return sum(job.get("scoring", {}).get("status") == "pending" for job in self.state["jobs"].values())

    def _require_complete_workflow(self, action: str) -> None:
        pending = self.pending_count()
        workflow = self.state.get("workflow_run") or {}
        if pending or workflow.get("status") != "complete":
            raise RuntimeError(
                f"cannot {action}: scoring workflow is incomplete "
                f"(status={workflow.get('status') or 'not-started'}, pending={pending})"
            )

    def run_status(self) -> dict[str, Any]:
        workflow = dict(self.state.get("workflow_run") or {})
        pending = self.pending_count()
        workflow.setdefault("status", "not-started")
        workflow["pending_count"] = pending
        workflow["complete"] = workflow.get("status") == "complete" and pending == 0
        return workflow

    def resume_run(self) -> dict[str, Any]:
        workflow = self.state.get("workflow_run")
        if not workflow:
            raise RuntimeError("no scoring workflow exists to resume")
        pending = self.pending_count()
        if workflow.get("status") == "complete" and pending == 0:
            return self.run_status()
        workflow["status"] = "scoring" if pending else "ready-to-finalize"
        workflow["pending_count"] = pending
        workflow["last_resumed_at"] = iso_now()
        workflow["resume_count"] = int(workflow.get("resume_count", 0)) + 1
        workflow["error"] = None
        self.save()
        return self.run_status()

    def fail_run(self, error: str) -> dict[str, Any]:
        workflow = self.state.get("workflow_run")
        if not workflow:
            raise RuntimeError("no scoring workflow exists to fail")
        if workflow.get("status") == "complete":
            raise RuntimeError("cannot fail a completed scoring workflow")
        workflow.update({
            "status": "failed",
            "failed_at": iso_now(),
            "pending_count": self.pending_count(),
            "error": redact(error),
        })
        self.save()
        return self.run_status()

    def collect(self) -> dict[str, Any]:
        workflow = self.state.get("workflow_run") or {}
        pending = self.pending_count()
        if workflow.get("status") not in {None, "complete"} or pending:
            raise RuntimeError(
                "an unfinished scoring workflow already exists; resume and finalize it before collecting again "
                f"(status={workflow.get('status') or 'not-started'}, pending={pending})"
            )
        started = iso_now()
        found: list[dict[str, Any]] = []
        credentials: dict[str, Any] = {}
        credential_error = None
        try:
            credentials = self._credentials()
        except RuntimeError as exc:
            credential_error = str(exc)

        sources = [
            ("greenhouse", lambda: self.collect_greenhouse()),
            ("lever", lambda: self.collect_lever()),
            ("adzuna", lambda: self.collect_adzuna(credentials)),
            ("reed", lambda: self.collect_reed(credentials)),
        ]
        successful: set[str] = set()
        for name, collector in sources:
            source_config = self.config.get("sources", {}).get(name, {})
            if not source_config.get("enabled", True):
                self._record_health(name, "disabled", error=source_config.get("disabled_reason"))
                continue
            if credential_error and name in {"adzuna", "reed"}:
                self._record_health(name, "failed", error=credential_error)
                continue
            try:
                batch = collector()
                found.extend(batch)
                successful.add(name)
                self._record_health(name, "ok", len(batch))
            except KeyError as exc:
                self._record_health(name, "blocked", error=str(exc).strip("'"))
            except Exception as exc:  # isolate sources by design
                self._record_health(name, "failed", error=redact(str(exc)))

        seen_source_ids = {(record["source"], str(record["source_id"])) for record in found}
        stats = self._merge(found)
        self._update_lifecycle(successful, seen_source_ids)
        failures = [name for name, health in self.state["source_health"].items() if health["status"] == "failed"]
        enabled = [name for name, source in self.config.get("sources", {}).items() if source.get("enabled", True)]
        all_failed = bool(enabled) and all(self.state["source_health"].get(name, {}).get("status") == "failed" for name in enabled)
        run = {
            "id": "run-" + short_hash(started + str(stats), 12),
            "started_at": started,
            "finished_at": iso_now(),
            **stats,
            "source_failures": failures,
            "all_sources_failed": all_failed,
        }
        self.state["last_run"] = run
        pending = self.pending_count()
        self.state["workflow_run"] = {
            "id": run["id"],
            "status": "scoring" if pending else "ready-to-finalize",
            "started_at": started,
            "collected_at": run["finished_at"],
            "records_seen": stats["records_seen"],
            "new_jobs": stats["new_jobs"],
            "changed_jobs": stats["changed_jobs"],
            "pending_count": pending,
            "batches_completed": 0,
            "scores_applied": 0,
            "resume_count": 0,
            "error": None,
        }
        run["workflow_run_id"] = run["id"]
        run["pending_count"] = pending
        self.save()
        self._append_history(run)
        self.prune_cache()
        return run

    def _merge(self, records: Iterable[dict[str, Any]]) -> dict[str, int]:
        new_count = changed_count = seen_count = 0
        by_url: dict[str, str] = {}
        by_source: dict[tuple[str, str], str] = {}
        by_fingerprint: dict[str, set[str]] = defaultdict(set)
        for job_id, job in self.state["jobs"].items():
            if job.get("canonical_url"):
                by_url[job["canonical_url"]] = job_id
            if job.get("fingerprint"):
                by_fingerprint[job["fingerprint"]].add(job_id)
            for ref in job.get("sources", []):
                by_source[(ref["source"], str(ref["source_id"]))] = job_id

        for record in records:
            if not record.get("source_id") or not record.get("title"):
                continue
            fp = fingerprint(record)
            url = canonical_url(record.get("url"))
            source_key = (record["source"], str(record["source_id"]))
            job_id = by_source.get(source_key) or by_url.get(url)
            if job_id is None:
                cross_source_candidates = [
                    candidate_id
                    for candidate_id in by_fingerprint.get(fp, set())
                    if all(ref.get("source") != record["source"] for ref in self.state["jobs"][candidate_id].get("sources", []))
                ]
                if len(cross_source_candidates) == 1:
                    job_id = cross_source_candidates[0]
            description = record.pop("description", "")
            content_hash = short_hash(description, 32)
            incoming_rank = SOURCE_RANK.get(record["source"], 0)
            timestamp = iso_now()
            if job_id is None:
                job_id = "job-" + short_hash("|".join(source_key), 12)
                while job_id in self.state["jobs"]:
                    job_id = "job-" + short_hash(job_id + fp, 12)
                job = {
                    "id": job_id,
                    "fingerprint": fp,
                    "title": clean_html(record.get("title")),
                    "company": clean_html(record.get("company")) or "Unknown company",
                    "location": clean_html(record.get("location")) or "Location not stated",
                    "workplace": record.get("workplace"),
                    "employment": record.get("employment"),
                    "salary": record.get("salary"),
                    "canonical_url": url,
                    "posted_at": normalized_iso(record.get("posted_at")),
                    "expires_at": normalized_iso(record.get("expires_at")),
                    "first_seen": timestamp,
                    "last_seen": timestamp,
                    "lifecycle": "active",
                    "full_description": bool(record.get("full_description")),
                    "content_hash": content_hash,
                    "description_source": record["source"],
                    "summary_excerpt": description[:320],
                    "sources": [],
                    "scoring": {"status": "pending", "rubric_version": RUBRIC_VERSION},
                    "user": {"status": "unseen", "rating": None, "note": "", "priority_override": None},
                    "alert": {"pending": False, "last_alert_key": None, "last_alert_priority": None},
                }
                self.state["jobs"][job_id] = job
                new_count += 1
            else:
                job = self.state["jobs"][job_id]
                description_rank = SOURCE_RANK.get(job.get("description_source", ""), 0)
                use_description = bool(description) and incoming_rank >= description_rank
                changed = use_description and job.get("content_hash") != content_hash
                if use_description:
                    job["description_source"] = record["source"]
                    if changed:
                        job["content_hash"] = content_hash
                        job["summary_excerpt"] = description[:320]
                        job["scoring"] = {"status": "pending", "rubric_version": RUBRIC_VERSION}
                        changed_count += 1
                self._prefer_record(job, record)
                job["last_seen"] = timestamp
                job["lifecycle"] = "active"
                job["full_description"] = job.get("full_description", False) or bool(record.get("full_description"))
            self._upsert_source(job, record, url, content_hash)
            if job.get("description_source") == record["source"]:
                self._cache_description(job_id, description, content_hash)
            by_source[source_key] = job_id
            if url:
                by_url[url] = job_id
            by_fingerprint[fp].add(job_id)
            seen_count += 1
        return {"records_seen": seen_count, "new_jobs": new_count, "changed_jobs": changed_count}

    def _prefer_record(self, job: dict[str, Any], record: dict[str, Any]) -> None:
        existing_rank = max((SOURCE_RANK.get(ref["source"], 0) for ref in job.get("sources", [])), default=0)
        if SOURCE_RANK.get(record["source"], 0) < existing_rank:
            return
        for key in ("title", "company", "location", "workplace", "employment", "salary"):
            if record.get(key):
                job[key] = clean_html(record[key]) if isinstance(record[key], str) else record[key]
        if record.get("url"):
            job["canonical_url"] = canonical_url(record["url"])
        for key in ("posted_at", "expires_at"):
            if record.get(key):
                job[key] = normalized_iso(record[key])

    def _upsert_source(self, job: dict[str, Any], record: dict[str, Any], url: str, content_hash: str) -> None:
        key = (record["source"], str(record["source_id"]))
        for ref in job["sources"]:
            if (ref["source"], str(ref["source_id"])) == key:
                ref.update({"url": url, "last_seen": iso_now(), "content_hash": content_hash, "missing_runs": 0})
                return
        job["sources"].append({
            "source": key[0],
            "source_id": key[1],
            "url": url,
            "first_seen": iso_now(),
            "last_seen": iso_now(),
            "content_hash": content_hash,
            "missing_runs": 0,
        })

    def _cache_description(self, job_id: str, description: str, content_hash: str) -> None:
        if not description:
            return
        write_json(self.cache / "descriptions" / f"{job_id}.json", {
            "job_id": job_id,
            "cached_at": iso_now(),
            "content_hash": content_hash,
            "description": description,
        }, mode=0o600)

    def prune_cache(self) -> None:
        cutoff = now_utc() - timedelta(days=7)
        directory = self.cache / "descriptions"
        if not directory.exists():
            return
        for path in directory.glob("*.json"):
            if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
                path.unlink()

    def _update_lifecycle(self, successful: set[str], seen_source_ids: set[tuple[str, str]]) -> None:
        now = now_utc()
        for job in self.state["jobs"].values():
            for ref in job.get("sources", []):
                key = (ref.get("source"), str(ref.get("source_id")))
                if ref.get("source") in {"greenhouse", "lever"} & successful and key not in seen_source_ids:
                    ref["missing_runs"] = int(ref.get("missing_runs", 0)) + 1
            ats_refs = [ref for ref in job.get("sources", []) if ref.get("source") in {"greenhouse", "lever"}]
            non_ats_refs = [ref for ref in job.get("sources", []) if ref.get("source") not in {"greenhouse", "lever"}]
            expiry = parse_date(job.get("expires_at"))
            last_seen = parse_date(job.get("last_seen"))
            if expiry and expiry < now:
                job["lifecycle"] = "expired"
            elif ats_refs and not non_ats_refs and all(ref.get("missing_runs", 0) >= 2 for ref in ats_refs):
                job["lifecycle"] = "closed"
            elif last_seen and last_seen < now - timedelta(days=14):
                job["lifecycle"] = "stale"

    def _append_history(self, run: dict[str, Any]) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(run, ensure_ascii=False) + "\n")

    def pending(self, limit: int) -> dict[str, Any]:
        workflow = self.state.get("workflow_run")
        if not workflow:
            raise RuntimeError("collect must start a scoring workflow before requesting pending jobs")
        if workflow.get("status") == "failed":
            raise RuntimeError("scoring workflow is failed; run resume-run before requesting another batch")
        if workflow.get("status") == "complete":
            return {"run_id": workflow.get("id"), "rubric_version": RUBRIC_VERSION, "profile": self.profile, "pending_count": 0, "jobs": []}
        jobs = []
        ordered = sorted(self.state["jobs"].values(), key=lambda job: job.get("first_seen") or "", reverse=True)
        for job in ordered:
            if job.get("scoring", {}).get("status") != "pending":
                continue
            cached = load_json(self.cache / "descriptions" / f"{job['id']}.json", {})
            jobs.append({
                "job_id": job["id"],
                "title": job["title"],
                "company": job["company"],
                "location": job["location"],
                "workplace": job.get("workplace"),
                "employment": job.get("employment"),
                "salary": job.get("salary"),
                "posted_at": job.get("posted_at"),
                "full_description": job.get("full_description", False),
                "url": job.get("canonical_url"),
                "description": cached.get("description") or job.get("summary_excerpt", ""),
            })
            if len(jobs) >= limit:
                break
        return {
            "run_id": workflow.get("id"),
            "rubric_version": RUBRIC_VERSION,
            "profile": self.profile,
            "pending_count": self.pending_count(),
            "batch_size": len(jobs),
            "jobs": jobs,
        }

    def apply_scores(self, scores: Any, model: str | None) -> dict[str, Any]:
        workflow = self.state.get("workflow_run")
        workflow_preexisted = workflow is not None
        supplied_run_id = scores.get("run_id") if isinstance(scores, dict) else None
        if isinstance(scores, dict) and "scores" in scores:
            scores = scores["scores"]
        if not workflow:
            pending = self.pending_count()
            workflow = {
                "id": "run-manual-" + short_hash(iso_now(), 12),
                "status": "scoring" if pending else "ready-to-finalize",
                "started_at": iso_now(),
                "pending_count": pending,
                "batches_completed": 0,
                "scores_applied": 0,
                "resume_count": 0,
                "error": None,
            }
            self.state["workflow_run"] = workflow
        if workflow.get("status") not in {"scoring", "ready-to-finalize"}:
            raise RuntimeError(f"cannot apply scores while workflow status is {workflow.get('status')}")
        if workflow_preexisted and supplied_run_id != workflow.get("id"):
            raise ValueError(f"score file run_id does not match active workflow {workflow.get('id')}")
        if not isinstance(scores, list):
            raise ValueError("score file must contain a JSON array")
        applied = skipped = 0
        for item in scores:
            job_id = item.get("job_id") if isinstance(item, dict) else None
            if job_id not in self.state["jobs"]:
                raise ValueError(f"unknown job_id: {job_id}")
            if self.state["jobs"][job_id].get("scoring", {}).get("status") != "pending":
                skipped += 1
                continue
            components = item.get("components") or {}
            if set(components) != set(COMPONENT_LIMITS):
                raise ValueError(f"{job_id}: components must be {sorted(COMPONENT_LIMITS)}")
            for key, maximum in COMPONENT_LIMITS.items():
                value = components[key]
                if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
                    raise ValueError(f"{job_id}: {key} must be an integer from 0 to {maximum}")
            for key in ("matches", "gaps", "uncertainties"):
                if not isinstance(item.get(key), list) or not all(isinstance(value, str) for value in item[key]):
                    raise ValueError(f"{job_id}: {key} must be a list of strings")
            if not isinstance(item.get("summary"), str) or not item["summary"].strip():
                raise ValueError(f"{job_id}: summary is required")
            job = self.state["jobs"][job_id]
            total = sum(components.values())
            priority, caps = self._priority(job, total, components, item)
            job["scoring"] = {
                "status": "scored",
                "rubric_version": RUBRIC_VERSION,
                "model": model or "unspecified",
                "scored_at": iso_now(),
                "lane": item.get("lane") or "other",
                "components": components,
                "total": total,
                "priority": priority,
                "caps": caps,
                "matches": item["matches"][:8],
                "gaps": item["gaps"][:8],
                "uncertainties": item["uncertainties"][:8],
                "summary": item["summary"].strip(),
                "critical_unknown": bool(item.get("critical_unknown")),
                "hard_blocker": bool(item.get("hard_blocker")),
                "hard_blocker_reason": item.get("hard_blocker_reason"),
            }
            new_priority = effective_priority(job)
            alert_key = f"{job['content_hash']}:{new_priority}"
            previously = job.get("alert", {}).get("last_alert_priority")
            first_alert = not job.get("alert", {}).get("last_alert_key")
            increased = priority_rank(new_priority) > priority_rank(previously)
            job.setdefault("alert", {})["pending"] = new_priority in {"A", "B"} and (first_alert or increased) and job["alert"].get("last_alert_key") != alert_key
            applied += 1
        pending = self.pending_count()
        workflow["pending_count"] = pending
        workflow["batches_completed"] = int(workflow.get("batches_completed", 0)) + (1 if applied else 0)
        workflow["scores_applied"] = int(workflow.get("scores_applied", 0)) + applied
        workflow["last_progress_at"] = iso_now()
        workflow["status"] = "scoring" if pending else "ready-to-finalize"
        self.save()
        return {"applied": applied, "skipped": skipped, "pending_count": pending, "run_id": workflow.get("id"), "status": workflow["status"]}

    def finalize_run(self) -> dict[str, Any]:
        workflow = self.state.get("workflow_run")
        if not workflow:
            raise RuntimeError("no scoring workflow exists to finalize")
        pending = self.pending_count()
        if pending:
            raise RuntimeError(f"cannot finalize scoring workflow with {pending} pending jobs")
        if workflow.get("status") not in {"ready-to-finalize", "scoring"}:
            raise RuntimeError(f"cannot finalize workflow with status {workflow.get('status')}")
        workflow.update({
            "status": "complete",
            "pending_count": 0,
            "finished_at": iso_now(),
            "error": None,
        })
        self.save()
        self.render()
        errors = self.validate()
        if errors:
            workflow.update({"status": "failed", "failed_at": iso_now(), "error": "; ".join(errors)})
            self.save()
            raise RuntimeError("workflow finalization validation failed: " + "; ".join(errors))
        return {
            "run_id": workflow.get("id"),
            "status": "complete",
            "pending_count": 0,
            "batches_completed": workflow.get("batches_completed", 0),
            "scores_applied": workflow.get("scores_applied", 0),
            "dashboard": str(self.dashboard_path),
        }

    def _priority(self, job: dict[str, Any], total: int, components: dict[str, int], item: dict[str, Any]) -> tuple[str, list[str]]:
        if item.get("hard_blocker"):
            return "Excluded", ["hard blocker"]
        caps: list[str] = []
        fresh = parse_date(job.get("posted_at") or job.get("first_seen"))
        if not job.get("full_description"):
            caps.append("incomplete description")
        if not fresh or fresh < now_utc() - timedelta(days=14):
            caps.append("older than 14 days or age unknown")
        if item.get("critical_unknown"):
            caps.append("critical unknown")
        if total >= 85 and components["logistics"] >= 12 and not caps:
            return "A", caps
        if total >= 72:
            return "B", caps
        if total >= 55:
            return "C", caps
        return "Excluded", caps

    def alerts(self) -> dict[str, Any]:
        self._require_complete_workflow("inspect alerts")
        jobs = []
        for job in self.state["jobs"].values():
            if job.get("alert", {}).get("pending"):
                jobs.append(alert_view(job))
        jobs.sort(key=lambda item: (priority_rank(item["priority"]), item["score"]), reverse=True)
        health = self.state.get("source_health", {})
        source_alerts = []
        for name, value in health.items():
            if value.get("status") == "failed" and ("authentication rejected" in (value.get("error") or "") or value.get("consecutive_failures", 0) >= 2):
                source_alerts.append({"source": name, "error": value.get("error"), "consecutive_failures": value.get("consecutive_failures")})
        if (self.state.get("last_run") or {}).get("all_sources_failed"):
            source_alerts.append({"source": "all", "error": "all enabled sources failed"})
        return {"jobs": jobs, "source_alerts": source_alerts}

    def mark_alerted(self, job_ids: list[str]) -> dict[str, int]:
        self._require_complete_workflow("mark alerts")
        marked = 0
        for job_id in job_ids:
            job = self.state["jobs"].get(job_id)
            if not job:
                raise ValueError(f"unknown job_id: {job_id}")
            priority = effective_priority(job)
            job.setdefault("alert", {}).update({
                "pending": False,
                "last_alert_key": f"{job.get('content_hash')}:{priority}",
                "last_alert_priority": priority,
                "last_alerted_at": iso_now(),
            })
            marked += 1
        self.save()
        self.render()
        return {"marked": marked}

    def set_status(self, job_id: str, status: str, rating: int | None, note: str | None, priority_override: str | None) -> dict[str, Any]:
        self._require_complete_workflow("update review status")
        if job_id not in self.state["jobs"]:
            raise ValueError(f"unknown job_id: {job_id}")
        if status not in USER_STATES:
            raise ValueError(f"invalid status: {status}")
        if rating is not None and rating not in range(1, 6):
            raise ValueError("rating must be from 1 to 5")
        clear_override = priority_override == "none"
        if clear_override:
            priority_override = None
        if priority_override is not None and priority_override not in PRIORITIES:
            raise ValueError("priority override must be A, B, C, Excluded, or none")
        user = self.state["jobs"][job_id].setdefault("user", {})
        user["status"] = status
        if rating is not None:
            user["rating"] = rating
            user["rated_at"] = iso_now()
        if note is not None:
            user["note"] = note
        if priority_override is not None or clear_override:
            user["priority_override"] = priority_override
        user["updated_at"] = iso_now()
        self.save()
        self.render()
        return {"job_id": job_id, "user": user}

    def purge_source(self, source: str) -> dict[str, int]:
        self._require_complete_workflow("purge a source")
        removed_refs = removed_jobs = 0
        for job_id in list(self.state["jobs"]):
            job = self.state["jobs"][job_id]
            before = len(job.get("sources", []))
            job["sources"] = [ref for ref in job.get("sources", []) if ref.get("source") != source]
            removed_refs += before - len(job["sources"])
            if not job["sources"]:
                del self.state["jobs"][job_id]
                cache_path = self.cache / "descriptions" / f"{job_id}.json"
                if cache_path.exists():
                    cache_path.unlink()
                removed_jobs += 1
        self.state.get("source_health", {}).pop(source, None)
        self.save()
        self.render()
        return {"removed_source_refs": removed_refs, "removed_jobs": removed_jobs}

    def render(self) -> str:
        self._require_complete_workflow("render dashboard")
        jobs = list(self.state["jobs"].values())
        active = [job for job in jobs if job.get("lifecycle") == "active"]
        scored = [job for job in active if job.get("scoring", {}).get("status") == "scored" and job.get("user", {}).get("status") != "dismissed"]
        new_ab = [job for job in scored if job.get("alert", {}).get("pending") and effective_priority(job) in {"A", "B"}]
        active_ab = [job for job in scored if effective_priority(job) in {"A", "B"}]
        c_jobs = [job for job in scored if effective_priority(job) == "C"][:25]
        lines = [
            "---",
            "type: dashboard",
            "status: active",
            f"updated: {iso_now()}",
            "---",
            "",
            "# Job Market Dashboard",
            "",
            "> Generated by the private job-market tracker. Set review states with the tracker command; do not edit generated tables as source data.",
            "",
            "## Run and source health",
            "",
        ]
        last = self.state.get("last_run") or {}
        lines.append(f"Last scan: {last.get('finished_at') or 'Not run'} · Records seen: {last.get('records_seen', 0)} · New: {last.get('new_jobs', 0)} · Changed: {last.get('changed_jobs', 0)}")
        workflow = self.state.get("workflow_run") or {}
        lines.append(f"Workflow: {workflow.get('status', 'not-started')} · Scored this run: {workflow.get('scores_applied', 0)} · Batches: {workflow.get('batches_completed', 0)} · Pending: {workflow.get('pending_count', self.pending_count())}")
        lines.extend(["", "| Source | Status | Listings | Consecutive failures | Detail |", "|---|---:|---:|---:|---|"])
        for name in ("greenhouse", "lever", "reed", "adzuna"):
            health = self.state.get("source_health", {}).get(name, {})
            lines.append(f"| {name.title()} | {health.get('status', 'not run')} | {health.get('count', 0)} | {health.get('consecutive_failures', 0)} | {md(health.get('error') or '')} |")
        lines.extend(["", "## New priority A/B", ""])
        lines.extend(job_cards(new_ab, empty="No unalerted priority A/B roles."))
        lines.extend(["", "## Active priority A/B", ""])
        lines.extend(job_cards(active_ab, empty="No active scored A/B roles."))
        lines.extend(["", "## Reviewable priority C", ""])
        lines.extend(job_cards(c_jobs, empty="No active scored C roles."))
        lines.extend(["", "## Inventory", ""])
        priority_counts = Counter(effective_priority(job) for job in scored)
        lane_counts = Counter(job.get("scoring", {}).get("lane", "unscored") for job in active)
        source_counts = Counter(ref["source"] for job in active for ref in job.get("sources", []))
        lines.extend([
            f"Active: {len(active)} · Pending scoring: {sum(job.get('scoring', {}).get('status') == 'pending' for job in active)} · Stale/expired: {len(jobs) - len(active)}",
            "",
            "- Priority: " + ", ".join(f"{key} {priority_counts.get(key, 0)}" for key in ("A", "B", "C", "Excluded")),
            "- Lanes: " + (", ".join(f"{key} {value}" for key, value in lane_counts.most_common()) or "none"),
            "- Sources: " + (", ".join(f"{key} {value}" for key, value in source_counts.most_common()) or "none"),
            "",
            "## Scan trend",
            "",
            "| Date | Seen | New | Changed | Failures |",
            "|---|---:|---:|---:|---:|",
        ])
        history = read_history(self.history_path)[-30:]
        for row in reversed(history):
            lines.append(f"| {(row.get('finished_at') or '')[:10]} | {row.get('records_seen', 0)} | {row.get('new_jobs', 0)} | {row.get('changed_jobs', 0)} | {len(row.get('source_failures', []))} |")
        ratings = [(job.get("scoring", {}).get("total"), job.get("user", {}).get("rating")) for job in jobs if job.get("user", {}).get("rating")]
        lines.extend(["", "## Calibration", ""])
        if len(ratings) < 25:
            lines.append(f"{len(ratings)}/25 user ratings recorded before the first calibration review.")
        else:
            by_rating: dict[int, list[int]] = defaultdict(list)
            for score, rating in ratings:
                if isinstance(score, int):
                    by_rating[int(rating)].append(score)
            lines.append("Observed automated-score ranges by user rating (informational only; thresholds are never changed automatically):")
            for rating in sorted(by_rating, reverse=True):
                values = by_rating[rating]
                lines.append(f"- Rating {rating}: n={len(values)}, mean={sum(values)/len(values):.1f}, range={min(values)}–{max(values)}")
        lines.extend(["", "## Review commands", "", "```bash", "python ~/git/endeavouros-dotfiles/config/agent-skills/job-market-tracker/scripts/job_market_tracker.py set-status JOB_ID reviewed --rating 3", "```", ""])
        lines.extend([
            "## Sources",
            "",
            "Vacancies are collected from configured employer ATS boards and official job APIs. [Adzuna](https://www.adzuna.co.uk/) · [Reed](https://www.reed.co.uk/) · [Greenhouse](https://www.greenhouse.com/) · [Lever](https://www.lever.co/)",
            "",
        ])
        output = "\n".join(lines)
        write_text(self.dashboard_path, output)
        return output

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.state.get("schema_version") != SCHEMA_VERSION:
            errors.append("wrong state schema version")
        if not isinstance(self.state.get("jobs"), dict):
            errors.append("jobs must be an object")
        for job_id, job in self.state.get("jobs", {}).items():
            if job.get("id") != job_id:
                errors.append(f"{job_id}: embedded ID mismatch")
            if "description" in job or "raw_description" in job:
                errors.append(f"{job_id}: raw description stored durably")
            if job.get("user", {}).get("status") not in USER_STATES:
                errors.append(f"{job_id}: invalid user state")
            if effective_priority(job) not in PRIORITIES and job.get("scoring", {}).get("status") == "scored":
                errors.append(f"{job_id}: invalid priority")
        workflow = self.state.get("workflow_run") or {}
        if workflow.get("status") == "complete" and self.pending_count() != 0:
            errors.append("completed workflow has pending jobs")
        if workflow.get("status") == "complete":
            unscored = [job_id for job_id, job in self.state.get("jobs", {}).items() if job.get("scoring", {}).get("status") != "scored"]
            if unscored:
                errors.append(f"completed workflow has {len(unscored)} non-terminal jobs")
        state_text = json.dumps(self.state)
        if re.search(r'(?i)"(?:app_key|api_key|authorization)"\s*:', state_text):
            errors.append("credential-shaped key found in durable state")
        if not self.dashboard_path.exists():
            errors.append("dashboard missing")
        elif "# Job Market Dashboard" not in self.dashboard_path.read_text(encoding="utf-8"):
            errors.append("dashboard heading missing")
        else:
            errors.extend(validate_markdown_tables(self.dashboard_path.read_text(encoding="utf-8")))
        return errors


def raw_job(source: str, source_id: Any, title: Any, company: Any, location: Any, url: Any, description: Any, posted_at: Any, expires_at: Any, workplace: Any, employment: Any, salary: Any, full_description: bool) -> dict[str, Any]:
    return {
        "source": source,
        "source_id": str(source_id or ""),
        "title": clean_html(title),
        "company": clean_html(company),
        "location": clean_html(location),
        "url": str(url or ""),
        "description": clean_html(description),
        "posted_at": posted_at,
        "expires_at": expires_at,
        "workplace": workplace,
        "employment": employment,
        "salary": salary,
        "full_description": full_description,
    }


def salary_dict(minimum: Any, maximum: Any, currency: str | None) -> dict[str, Any] | None:
    if minimum in (None, "") and maximum in (None, ""):
        return None
    return {"min": minimum, "max": maximum, "currency": currency or "GBP"}


def normalized_iso(value: Any) -> str | None:
    parsed = parse_date(value)
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z") if parsed else None


def fingerprint(record: dict[str, Any]) -> str:
    return "|".join(norm(record.get(key)) for key in ("company", "title", "location"))


def effective_priority(job: dict[str, Any]) -> str | None:
    return job.get("user", {}).get("priority_override") or job.get("scoring", {}).get("priority")


def priority_rank(priority: str | None) -> int:
    return {None: 0, "Excluded": 0, "C": 1, "B": 2, "A": 3}.get(priority, 0)


def alert_view(job: dict[str, Any]) -> dict[str, Any]:
    scoring = job.get("scoring", {})
    return {
        "job_id": job["id"],
        "title": job["title"],
        "company": job["company"],
        "location": job["location"],
        "workplace": job.get("workplace"),
        "priority": effective_priority(job),
        "score": scoring.get("total"),
        "lane": scoring.get("lane"),
        "fit_reason": (scoring.get("matches") or [None])[0],
        "gap_or_uncertainty": (scoring.get("gaps") or scoring.get("uncertainties") or [None])[0],
        "url": job.get("canonical_url"),
    }


def md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def table_cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", body)]


def validate_markdown_tables(text: str) -> list[str]:
    errors: list[str] = []
    lines = text.splitlines()
    separator_cell = re.compile(r"^:?-{3,}:?$")
    index = 0
    while index < len(lines) - 1:
        if not lines[index].lstrip().startswith("|") or not lines[index + 1].lstrip().startswith("|"):
            index += 1
            continue
        separators = table_cells(lines[index + 1])
        if not separators or not all(re.fullmatch(r":?-+:?", cell) for cell in separators):
            index += 1
            continue
        headers = table_cells(lines[index])
        line_number = index + 1
        if len(headers) != len(separators):
            errors.append(f"dashboard table at line {line_number}: header/separator column mismatch")
        for cell in separators:
            if not separator_cell.fullmatch(cell):
                errors.append(f"dashboard table at line {line_number}: separator cells need at least three hyphens")
                break
        expected = len(headers)
        row_index = index + 2
        while row_index < len(lines) and lines[row_index].lstrip().startswith("|"):
            if len(table_cells(lines[row_index])) != expected:
                errors.append(f"dashboard table at line {row_index + 1}: expected {expected} columns")
            row_index += 1
        index = row_index
    return errors


def job_cards(jobs: list[dict[str, Any]], empty: str) -> list[str]:
    if not jobs:
        return [empty]
    ordered = sorted(jobs, key=lambda job: (priority_rank(effective_priority(job)), job.get("scoring", {}).get("total", 0)), reverse=True)
    lines: list[str] = []
    for job in ordered:
        scoring = job.get("scoring", {})
        title = md(job["title"])
        if job.get("canonical_url"):
            title = f"[{title}]({job['canonical_url']})"
        fit = (scoring.get("matches") or [""])[0]
        gap = (scoring.get("gaps") or scoring.get("uncertainties") or [""])[0]
        lines.extend([
            f"### {effective_priority(job)} · {scoring.get('total', '')} — {title}",
            "",
            f"**{md(job['company'])}** · {md(job['location'])}  ",
            f"`{md(scoring.get('lane'))}` · `{job.get('user', {}).get('status')}` · `{job['id']}`",
            "",
            f"- **Fit:** {md(fit) or 'No fit evidence recorded.'}",
            f"- **Gap:** {md(gap) or 'No gap or uncertainty recorded.'}",
            "",
        ])
    return lines


def read_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def output_json(value: Any, path: str | None) -> None:
    content = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if path:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        write_text(target, content)
        target.chmod(0o600)
    else:
        sys.stdout.write(content)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("collect")
    sub.add_parser("run-status")
    sub.add_parser("resume-run")
    fail_run = sub.add_parser("fail-run")
    fail_run.add_argument("--error", required=True)
    sub.add_parser("finalize-run")
    pending = sub.add_parser("pending")
    pending.add_argument("--limit", type=int, default=30)
    pending.add_argument("--output")
    apply = sub.add_parser("apply-scores")
    apply.add_argument("--file", required=True, type=Path)
    apply.add_argument("--model")
    sub.add_parser("render")
    set_status = sub.add_parser("set-status")
    set_status.add_argument("job_id")
    set_status.add_argument("status", choices=sorted(USER_STATES))
    set_status.add_argument("--rating", type=int)
    set_status.add_argument("--note")
    set_status.add_argument("--priority-override", choices=["A", "B", "C", "Excluded", "none"])
    sub.add_parser("validate")
    purge = sub.add_parser("purge-source")
    purge.add_argument("source", choices=sorted(SOURCE_RANK))
    alerts = sub.add_parser("alerts")
    alerts.add_argument("--output")
    marked = sub.add_parser("mark-alerted")
    marked.add_argument("job_ids", nargs="+")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    tracker = Tracker(args.root.expanduser(), args.credentials.expanduser(), args.cache.expanduser())
    try:
        if args.command == "collect":
            output_json(tracker.collect(), None)
        elif args.command == "run-status":
            output_json(tracker.run_status(), None)
        elif args.command == "resume-run":
            output_json(tracker.resume_run(), None)
        elif args.command == "fail-run":
            output_json(tracker.fail_run(args.error), None)
        elif args.command == "finalize-run":
            output_json(tracker.finalize_run(), None)
        elif args.command == "pending":
            output_json(tracker.pending(args.limit), args.output)
        elif args.command == "apply-scores":
            output_json(tracker.apply_scores(load_json(args.file.expanduser(), []), args.model), None)
        elif args.command == "render":
            tracker.render()
            output_json({"dashboard": str(tracker.dashboard_path)}, None)
        elif args.command == "set-status":
            output_json(tracker.set_status(args.job_id, args.status, args.rating, args.note, args.priority_override), None)
        elif args.command == "validate":
            errors = tracker.validate()
            output_json({"valid": not errors, "errors": errors}, None)
            return 1 if errors else 0
        elif args.command == "purge-source":
            output_json(tracker.purge_source(args.source), None)
        elif args.command == "alerts":
            output_json(tracker.alerts(), args.output)
        elif args.command == "mark-alerted":
            output_json(tracker.mark_alerted(args.job_ids), None)
    except (RuntimeError, ValueError, OSError) as exc:
        print(redact(f"error: {exc}"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
