#!/bin/bash
# Daily API credit claim.
# Reads bearer token from $TOKEN_FILE and target URL from $URL_FILE.
# When the token expires (~monthly), refresh it from browser localStorage
# and overwrite $TOKEN_FILE.

CONFIG_DIR="$HOME/.config/credit-claim"
TOKEN_FILE="$CONFIG_DIR/token"
URL_FILE="$CONFIG_DIR/api_url"
LOG_FILE="$CONFIG_DIR/claim.log"
TIMER_NAME="credit-claim.timer"
TIMER_DROPIN_DIR="$HOME/.config/systemd/user/$TIMER_NAME.d"
TIMER_OVERRIDE="$TIMER_DROPIN_DIR/schedule.conf"
DEFAULT_TIMER_TIME="10:10:00"
SUCCESS_DELAY_SECONDS=30

configured_timer_time() {
    local time

    if [ -f "$TIMER_OVERRIDE" ]; then
        time=$(awk -F' ' '/^OnCalendar=\*-\*-\* / { value=$2 } END { print value }' "$TIMER_OVERRIDE")
    fi

    if [ -z "$time" ]; then
        time=$(systemctl --user cat "$TIMER_NAME" 2>/dev/null \
            | awk -F' ' '/^OnCalendar=\*-\*-\* / { value=$2 } END { print value }')
    fi

    if [[ ! "$time" =~ ^[0-9]{2}:[0-9]{2}(:[0-9]{2})?$ ]]; then
        time="$DEFAULT_TIMER_TIME"
    fi

    echo "$time"
}

add_seconds_to_time() {
    local time=$1
    local seconds_to_add=$2
    local hour minute second total

    IFS=: read -r hour minute second <<< "$time"
    second=${second:-0}

    total=$((10#$hour * 3600 + 10#$minute * 60 + 10#$second + seconds_to_add))
    total=$((total % 86400))

    printf "%02d:%02d:%02d\n" $((total / 3600)) $(((total % 3600) / 60)) $((total % 60))
}

timer_time_from_response() {
    local response=$1
    local next_claim_time parsed_time

    next_claim_time=$(echo "$response" | grep -o '"next_claim_time":"[^"]*"' | head -1 | cut -d'"' -f4)
    if [ -n "$next_claim_time" ]; then
        parsed_time=$(date -d "$next_claim_time + $SUCCESS_DELAY_SECONDS seconds" +%H:%M:%S 2>/dev/null || true)
    fi

    if [[ "$parsed_time" =~ ^[0-9]{2}:[0-9]{2}:[0-9]{2}$ ]]; then
        echo "$parsed_time"
        return
    fi

    add_seconds_to_time "$(configured_timer_time)" "$SUCCESS_DELAY_SECONDS"
}

delay_timer_after_success() {
    local response=$1
    local current_time next_time tmp_file

    current_time=$(configured_timer_time)
    next_time=$(timer_time_from_response "$response")

    mkdir -p "$TIMER_DROPIN_DIR"
    tmp_file=$(mktemp "$TIMER_DROPIN_DIR/.schedule.XXXXXX")
    {
        echo "[Timer]"
        echo "OnCalendar="
        echo "OnCalendar=*-*-* $next_time"
    } > "$tmp_file"
    mv "$tmp_file" "$TIMER_OVERRIDE"

    systemctl --user daemon-reload
    systemctl --user restart "$TIMER_NAME"

    echo "$(date -Iseconds) timer moved from $current_time to $next_time" >> "$LOG_FILE"
}

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

CURL_ERR=$(mktemp)
RESPONSE_FILE=$(mktemp)
HTTP_STATUS=$(curl -sS -o "$RESPONSE_FILE" -w "%{http_code}" -X POST "$URL" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" 2>"$CURL_ERR")
CURL_STATUS=$?
RESPONSE=$(cat "$RESPONSE_FILE")

CODE=$(echo "$RESPONSE" | grep -o '"code":[0-9]*' | head -1 | cut -d: -f2)
MSG=$(echo "$RESPONSE" | grep -o '"msg":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ -z "$MSG" ]; then
    MSG=$(echo "$RESPONSE" | grep -o '"Error":"[^"]*"' | head -1 | cut -d'"' -f4)
fi

if [ "$CURL_STATUS" -ne 0 ]; then
    echo "$(date -Iseconds) ERROR: curl failed: $(cat "$CURL_ERR")" >> "$LOG_FILE"
    rm -f "$CURL_ERR" "$RESPONSE_FILE"
    exit 1
fi
rm -f "$CURL_ERR" "$RESPONSE_FILE"

echo "$(date -Iseconds) http=$HTTP_STATUS code=$CODE msg=$MSG" >> "$LOG_FILE"

if [ "$HTTP_STATUS" = "401" ] || [ "$HTTP_STATUS" = "403" ] || [ "$CODE" = "401" ] || [ "$CODE" = "403" ]; then
    echo "$(date -Iseconds) WARNING: Token may be expired. Please refresh." >> "$LOG_FILE"
    exit 1
fi

if [ "$CODE" = "200" ]; then
    delay_timer_after_success "$RESPONSE"
    exit 0
fi

exit 1
