# Source setup

The Greenhouse, Lever and Ashby sources use public job-board endpoints and need no credentials.

Create `/home/howis/.config/job-market-tracker/credentials.json` with mode `0600` to enable Adzuna and Reed:

```json
{
  "adzuna": {
    "app_id": "replace-me",
    "app_key": "replace-me"
  },
  "reed": {
    "api_key": "replace-me"
  }
}
```

- Adzuna developer registration: https://developer.adzuna.com/
- Reed API registration: https://www.reed.co.uk/developers

The collector treats absent keys as a setup blocker and continues with ATS sources. It never writes secrets to scan history, listing state, the dashboard, logs, or alert output.

## Public ATS configuration

Configure employer boards under `ats` in the private `job-market-config.json`:

```json
{"ashby": [{"company": "Wayve", "board": "wayve"}]}
```

Enable `sources.ashby.enabled` and remove Wayve from `ats.greenhouse`.
Wayve's official careers page now links to `https://jobs.ashbyhq.com/wayve`.
Ashby's [public posting API](https://developers.ashbyhq.com/docs/public-job-posting-api)
requires no account or credentials. Only listed postings enter the tracker.

Each company board is collected independently. A source can be `partial`: healthy
boards still contribute listings, while the error names each failed company.
Repeated partial failures alert using the existing consecutive-failure threshold.
Only a successfully fetched board supplies evidence of missing jobs. Legacy refs
are attributed only to a unique configured company board; removed or ambiguous
refs remain preserved and can become stale under the existing age policy.
