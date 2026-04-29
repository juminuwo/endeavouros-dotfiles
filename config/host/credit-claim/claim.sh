#!/bin/bash
# Daily API credit claim.
# Reads bearer token from $TOKEN_FILE and target URL from $URL_FILE.
# When the token expires (~monthly), refresh it from browser localStorage
# and overwrite $TOKEN_FILE.

CONFIG_DIR="$HOME/.config/credit-claim"
TOKEN_FILE="$CONFIG_DIR/token"
URL_FILE="$CONFIG_DIR/api_url"
LOG_FILE="$CONFIG_DIR/claim.log"

if [ ! -f "$TOKEN_FILE" ]; then
    echo "$(date -Iseconds) ERROR: Token file not found at $TOKEN_FILE" >> "$LOG_FILE"
    exit 1
fi

if [ ! -f "$URL_FILE" ]; then
    echo "$(date -Iseconds) ERROR: URL file not found at $URL_FILE" >> "$LOG_FILE"
    exit 1
fi

TOKEN=$(cat "$TOKEN_FILE")
URL=$(cat "$URL_FILE")

RESPONSE=$(curl -s -X POST "$URL" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json")

CODE=$(echo "$RESPONSE" | grep -o '"code":[0-9]*' | head -1 | cut -d: -f2)
MSG=$(echo "$RESPONSE" | grep -o '"msg":"[^"]*"' | head -1 | cut -d'"' -f4)

echo "$(date -Iseconds) code=$CODE msg=$MSG" >> "$LOG_FILE"

if [ "$CODE" = "401" ] || [ "$CODE" = "403" ]; then
    echo "$(date -Iseconds) WARNING: Token may be expired. Please refresh." >> "$LOG_FILE"
fi
