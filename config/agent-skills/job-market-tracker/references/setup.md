# Source setup

The Greenhouse and Lever sources use public job-board endpoints and need no credentials.

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
