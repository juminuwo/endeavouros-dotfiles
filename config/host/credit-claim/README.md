# Credit Claim

Daily oneshot for claiming account credits through a private API endpoint.

The repo contains only the generic service wiring and script. Runtime details stay outside the repo in `~/.config/credit-claim/`:

- `token`: bearer token used as `Authorization: Bearer ...`
- `api_url`: target claim endpoint
- `page_url`: authenticated subscription/account page used for headless refresh
- `chrome-profile/`: dedicated browser session for this site only
- `claim.log`: local run log
- `failure.json`: current sanitized failure category and service invocation
- `notified.json`: last failure category confirmed delivered to Discord

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

## Discord Failure Notifications

`credit-claim.service` starts `credit-claim-notify.service` through systemd
`OnFailure`. The notifier sends a sanitized message to the existing Hermes
Discord DM with:

```sh
/home/howis/.local/bin/hermes send --to discord:isitokaymimi
```

No LLM, new webhook, or new bot credential is involved. Notification failures
do not alter the original claim result. `credit-claim-notify.timer` retries a
pending delivery every 15 minutes. Hermes exit code `0` is required before the
failure category is marked delivered.

The same unresolved category is sent once. A changed category sends a new
message, and the next successful claim clears both failure and delivery state.
The message never includes the bearer token, target domain or URLs, cookies,
local storage, or raw API responses.

Send a labeled delivery test without changing deduplication state:

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
