# Credit Claim

Daily oneshot for claiming account credits through a private API endpoint.

The repo contains only the generic service wiring and script. Runtime details stay outside the repo in `~/.config/credit-claim/`:

- `token`: bearer token used as `Authorization: Bearer ...`
- `api_url`: target claim endpoint
- `page_url`: authenticated subscription/account page used for headless refresh
- `chrome-profile/`: dedicated browser session for this site only
- `claim.log`: local run log
- `failure.json`: latest sanitized terminal outcome and service invocation
- `outcomes/`: pending terminal notifications
- `delivered/`: notification delivery markers
- `notified.json`: latest delivery compatibility snapshot

## Headless Token Refresh

An authentication rejection triggers one headless Chrome refresh and one claim
retry. Accepted claims and `not in time` responses never launch Chrome. The
workflow lock prevents timer and manual runs from making duplicate requests.

Bootstrap the dedicated profile once from an already logged-in Chrome session:

```sh
node ~/git/endeavouros-dotfiles/config/host/credit-claim/refresh-token.mjs \
  --bootstrap-from-active-chrome
```

Before bootstrapping, open the site's subscription/account page in Chrome and
enable remote debugging at `chrome://inspect/#remote-debugging`. The bootstrap
copies only cookies and local storage for the configured API origin, writes the
selected page to the private `page_url` file, and does not replace `token`.

If the dedicated browser session later expires, open it visibly and log in
again:

```sh
google-chrome-stable \
  --user-data-dir="$HOME/.config/credit-claim/chrome-profile" \
  "$(<"$HOME/.config/credit-claim/page_url")"
```

Close that dedicated Chrome window before retrying the service. The refresher
validates a different, unexpired JWT and atomically replaces `token` at mode
`0600`; it never logs the credential. It does not make a third claim attempt if
the refreshed token is rejected.

Do not commit the target domain, endpoint, token, account details, or browser profile data to this repo. Keep those in `~/.config/credit-claim/` or other private notes.

## Claim retries and stop notifications

Approved on 2026-09-11: retry HTTP 522 and curl DNS/proxy-resolution/connection
failures (exit codes 5, 6, 7) up to three times, waiting **5, 15, then 30 minutes**
between attempts. The lock stays held throughout. A single token refresh is
allowed across the whole run; it does not reset the transient retry budget.
Other HTTP errors, read timeouts, configuration failures and unexpected API
results stop immediately. Success and `not in time` also stop immediately.
A timer-update failure after a successful credit grant never resends the claim.

HTTP 522 can leave the POST outcome uncertain. The owner accepted bounded
retries based on the observed server cooldown rejecting repeat claims; server
atomicity/idempotency has not been verified. Broader timeout/5xx retries remain
excluded. Each request has a 20-second connection timeout and a 100-second
overall timeout. The service allows 65 minutes for 50 minutes of retry waits,
at most five requests and one bounded browser refresh. Interrupted retry waits
are not persisted; the daily timer remains recovery after a restart/reboot.

Every completed invocation queues one Discord message with an explicit
**Stop condition**, including success, not in time, retries exhausted, or the
specific permanent failure. Intermediate failures and concurrent lock skips do
not create messages. Messages contain sanitized attempt/retry counts and status
codes, never tokens, URLs, cookies or raw API responses.

`credit-claim.service` triggers `credit-claim-notify.service` on both success and
failure. Terminal outcomes are written to private `outcomes/<invocation>.json`
files before replacing the compatibility `failure.json` snapshot (which now
includes successful outcomes). The notifier tracks delivery per invocation so
the same condition on a later day still gets its own message. Pending outcomes
survive subsequent claims. Abnormal service failures get a fallback stop message.

`credit-claim-notify.timer` retries failed delivery every 15 minutes. No LLM,
new webhook or bot credential is involved. Delivery requires Hermes exit code 0.
A crash after Discord accepts a message but before delivery is recorded can
still cause a duplicate; Hermes does not provide an idempotency key here.

Install just the affected units:

```sh
./host-install --user-unit credit-claim.service credit-claim-notify.service credit-claim-notify.timer
```

Send a labeled delivery test without changing outcome state:

```sh
config/host/credit-claim/notify-failure.py --test
```

## Verify

Run the service manually:

```sh
systemctl --user start credit-claim.service
systemctl --user status credit-claim.service --no-pager
tail -n 20 ~/.config/credit-claim/claim.log
```

Expected accepted-token results:

- `http=200 code=200 msg=success`: claim worked, and the timer is moved to the next claim time plus the configured delay.
- `http=200 code=400 msg=not in time`: token is accepted, but the account is not eligible to claim yet.

Rejected-token results include `401`, `403`, or a headless-refresh warning.

## Tests

```sh
bash config/host/credit-claim/tests/claim.test.sh
node --test config/host/credit-claim/tests/refresh-token.test.mjs
python3 config/host/credit-claim/tests/notify_failure.test.py
```

## Timer

The timer is installed by `host-install` as a user unit. After a successful claim, `claim.sh` writes a drop-in at:

```text
~/.config/systemd/user/credit-claim.timer.d/schedule.conf
```

Inspect the next run:

```sh
systemctl --user list-timers --all --no-pager | rg 'credit-claim|NEXT|UNIT'
```
