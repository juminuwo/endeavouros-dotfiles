# Credit Claim

Daily oneshot for claiming account credits through a private API endpoint.

The repo contains only the generic service wiring and script. Runtime details stay outside the repo in `~/.config/credit-claim/`:

- `token`: bearer token used as `Authorization: Bearer ...`
- `api_url`: target claim endpoint
- `claim.log`: local run log

## Refreshing The Token

The token is copied from the browser session for the target site.

1. Log in to the site in Chrome.
2. Open the subscription/account page so the browser refreshes localStorage.
3. Extract the newest JWT from the site's localStorage `TOKEN` value.
4. Write it to `~/.config/credit-claim/token`.
5. Keep the file private:

```sh
chmod 600 ~/.config/credit-claim/token
```

Do not commit the target domain, endpoint, token, account details, or browser profile data to this repo. Keep those in `~/.config/credit-claim/` or other private notes.

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

Rejected-token results include `401`, `403`, or the script's "Token may be expired" warning.

## Timer

The timer is installed by `host-install` as a user unit. After a successful claim, `claim.sh` writes a drop-in at:

```text
~/.config/systemd/user/credit-claim.timer.d/schedule.conf
```

Inspect the next run:

```sh
systemctl --user list-timers --all --no-pager | rg 'credit-claim|NEXT|UNIT'
```
