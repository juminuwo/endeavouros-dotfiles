---
name: job-market-tracker
description: Collect, deduplicate, score, and review Adrian's UK applied-ML job market. Use for daily Hermes vacancy scans, the private Obsidian Job Market dashboard, source health, opportunity prioritisation, calibration, or updating job-review status. Never use it to scrape LinkedIn, submit applications, or contact recruiters.
---

# Job Market Tracker

Maintain a private, evidence-based vacancy inventory for senior applied ML, applied science, computer vision, and edge-AI roles. The bundled script owns retrieval, state, deterministic thresholds, dashboard rendering, and validation; the agent supplies bounded semantic scoring for new or materially changed descriptions.

## Paths

- Script: `scripts/job_market_tracker.py`
- Private dashboard root: `/home/howis/Documents/online-personal/Personal/Career/Job Market`
- Credentials: `/home/howis/.config/job-market-tracker/credentials.json`
- Raw-description cache: `/home/howis/.cache/job-market-tracker`
- Scoring contract: `references/scoring-contract.md`
- Credential setup: `references/setup.md`

Do not put credentials or raw job descriptions in the Obsidian vault. Do not publish the `Personal/` tree.

## Daily scan workflow

The batch limit protects one model call; it is never a per-run throughput limit. A successful daily run must leave every collected job in a terminal `scored` state and `pending_count` must be zero before rendering or alerts.

1. Inspect durable workflow state:

   ```bash
   python scripts/job_market_tracker.py run-status
   ```

   - `complete` or `not-started`: start a fresh collection.
   - `failed`: run `resume-run`, then drain and finalize that workflow without collecting over it.
   - `scoring` or `ready-to-finalize`: resume that workflow without collecting over it.
   - After recovering an earlier workflow, start and complete a fresh collection in the same invocation only when its `collected_at` date predates today in local time. A same-day recovery is already the current scan.

2. Start collection when the workflow rules above require it:

   ```bash
   python scripts/job_market_tracker.py collect
   ```

   Collection starts a durable scoring workflow and returns its `workflow_run_id`. It does not render the dashboard.

3. Request one batch of at most 30 pending records:

   ```bash
   python scripts/job_market_tracker.py pending --limit 30 --output /home/howis/.cache/job-market-tracker/pending.json
   ```

4. If `jobs` is non-empty, read `references/scoring-contract.md` and score every supplied record, including obvious exclusions. Write `/home/howis/.cache/job-market-tracker/scores.json` with the `write_file` tool as an object containing the exact pending payload `run_id` and a `scores` array. Cron runs cannot approve shell heredocs, `python -c`, or `execute_code`; do not use those mechanisms. Do not invent missing evidence; record it under `uncertainties`.

5. Apply the batch:

   ```bash
   python scripts/job_market_tracker.py apply-scores --file /home/howis/.cache/job-market-tracker/scores.json
   ```

6. Repeat steps 3–5 until `pending` returns an empty `jobs` array and `pending_count` is zero. Do not stop merely because one batch completed.

7. Finalize, then validate:

   ```bash
   python scripts/job_market_tracker.py finalize-run
   python scripts/job_market_tracker.py validate
   ```

   `finalize-run` is the only normal path that renders the dashboard. It refuses to run while any job is pending.

8. Inspect alert candidates only after successful finalization:

   ```bash
   python scripts/job_market_tracker.py alerts --output /home/howis/.cache/job-market-tracker/alerts.json
   ```

9. If there are no alert candidates and no alert-worthy source/validation failure, return exactly `[SILENT]`.

10. Otherwise, send a compact report containing role, company, location/work pattern, priority/score, one fit reason, one gap or uncertainty, and the official listing link. Then mark only the roles included in the report:

   ```bash
   python scripts/job_market_tracker.py mark-alerted JOB_ID [JOB_ID ...]
   ```

Alert a role again only when its description materially changes and its priority increases. Missing credentials are setup blockers shown on the dashboard, not daily failures. Alert on invalid credentials, all enabled sources failing, validation failure, or one enabled source failing on two consecutive runs.

If any collection, scoring, application, finalization, or validation step fails, run `fail-run --error "bounded non-secret summary"` when a workflow exists, report the run as incomplete, and stop. The next invocation must use `resume-run`; completed batches are durable and must not be rescored. Never report a partial workflow as a successful daily scan.

## Review operations

Set a user-controlled review state without changing automated evidence:

```bash
python scripts/job_market_tracker.py set-status JOB_ID shortlisted --rating 4 --note "Strong sensor/time-series fit"
```

Allowed states are `unseen`, `reviewed`, `shortlisted`, `applied`, and `dismissed`. A manual priority override is optional:

```bash
python scripts/job_market_tracker.py set-status JOB_ID reviewed --priority-override B
```

After every 25 user ratings, report the observed score/rating bands from the dashboard. Never adjust weights or thresholds automatically.

## Safety boundaries

- Use only configured official APIs and public ATS job-board endpoints.
- Never scrape or automate LinkedIn.
- Never auto-apply, fill an application, or contact a person.
- Keep salary unknown neutral; never infer a number.
- Preserve user states, notes, ratings, and priority overrides across refreshes.
- Do not delete stale or closed roles. Use `purge-source SOURCE` only for source-license removal.
- Prefer ATS records over Reed and Adzuna during exact duplicate merges while retaining every source reference.

## Maintenance

Run the fixture suite after changing the collector:

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

Run the skill validator after changing skill metadata:

```bash
python /home/howis/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```
