#!/bin/bash
set -euo pipefail

CONFIG_DIR=${CREDIT_CLAIM_CONFIG_DIR:-"$HOME/.config/credit-claim"}
PAGE_URL_FILE="$CONFIG_DIR/page_url"
PROFILE_DIR="$CONFIG_DIR/chrome-profile"
CHROME=${CREDIT_CLAIM_CHROME:-/usr/bin/google-chrome-stable}

if [ ! -x "$CHROME" ]; then
    echo "Chrome executable not found at $CHROME" >&2
    exit 1
fi
if [ ! -s "$PAGE_URL_FILE" ]; then
    echo "Credit-claim page_url is missing; bootstrap the profile first." >&2
    exit 1
fi

mkdir -p -m 700 "$PROFILE_DIR"
chmod 700 "$PROFILE_DIR"
exec "$CHROME" \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    "$(<"$PAGE_URL_FILE")"
