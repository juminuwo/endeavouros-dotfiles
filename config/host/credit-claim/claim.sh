#!/bin/bash
# Daily API credit claim.
# Reads bearer token from $TOKEN_FILE and target URL from $URL_FILE.
# On an authentication rejection, refreshes once through a dedicated headless
# Chrome profile and retries the claim once.

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CONFIG_DIR=${CREDIT_CLAIM_CONFIG_DIR:-"$HOME/.config/credit-claim"}
TOKEN_FILE="$CONFIG_DIR/token"
URL_FILE="$CONFIG_DIR/api_url"
LOG_FILE="$CONFIG_DIR/claim.log"
LOCK_FILE="$CONFIG_DIR/claim.lock"
NOTIFY_LOCK_FILE="$CONFIG_DIR/notification.lock"
FAILURE_FILE="$CONFIG_DIR/failure.json"
NOTIFIED_FILE="$CONFIG_DIR/notified.json"
REFRESH_SCRIPT=${CREDIT_CLAIM_REFRESH_SCRIPT:-"$SCRIPT_DIR/refresh-token.mjs"}
TIMER_NAME="credit-claim.timer"
TIMER_DROPIN_DIR="$HOME/.config/systemd/user/$TIMER_NAME.d"
TIMER_OVERRIDE="$TIMER_DROPIN_DIR/schedule.conf"
DEFAULT_TIMER_TIME="10:10:00"
SUCCESS_DELAY_SECONDS=30
TEMP_FILES=()

cleanup() {
    if [ "${#TEMP_FILES[@]}" -gt 0 ]; then
        rm -f "${TEMP_FILES[@]}"
    fi
}
trap cleanup EXIT

if ! mkdir -p -m 700 "$CONFIG_DIR" || ! chmod 700 "$CONFIG_DIR"; then
    echo "$(date -Iseconds) ERROR: Could not prepare credit-claim configuration directory." >&2
    exit 1
fi
if ! exec 8>"$NOTIFY_LOCK_FILE" || ! chmod 600 "$NOTIFY_LOCK_FILE"; then
    echo "$(date -Iseconds) ERROR: Could not prepare notification state lock." >> "$LOG_FILE"
    exit 1
fi

record_failure() {
    local category=$1 invocation_id timestamp tmp_file

    case "$category" in
        configuration-failed|claim-request-failed|login-required|refreshed-token-rejected|schedule-failed|unexpected-api-response)
            ;;
        *)
            category=generic-failure
            ;;
    esac
    invocation_id=${INVOCATION_ID:-manual}
    if [[ ! "$invocation_id" =~ ^[A-Fa-f0-9]{32}$ ]]; then
        invocation_id=manual
    fi
    timestamp=$(date -Iseconds)

    flock 8
    if ! tmp_file=$(mktemp "$CONFIG_DIR/.failure.XXXXXX"); then
        flock -u 8
        echo "$timestamp ERROR: Could not create failure notification state." >> "$LOG_FILE"
        return 1
    fi
    chmod 600 "$tmp_file"
    if ! printf '{"version":1,"invocation_id":"%s","category":"%s","timestamp":"%s"}\n' \
        "$invocation_id" "$category" "$timestamp" > "$tmp_file" \
        || ! mv "$tmp_file" "$FAILURE_FILE"; then
        rm -f "$tmp_file"
        flock -u 8
        echo "$timestamp ERROR: Could not install failure notification state." >> "$LOG_FILE"
        return 1
    fi
    flock -u 8
}

clear_failure_state() {
    flock 8
    if ! rm -f "$FAILURE_FILE" "$NOTIFIED_FILE"; then
        echo "$(date -Iseconds) WARNING: Could not clear failure notification state." >> "$LOG_FILE"
    fi
    flock -u 8
}

if ! exec 9>"$LOCK_FILE"; then
    echo "$(date -Iseconds) ERROR: Could not open claim lock." >> "$LOG_FILE"
    record_failure configuration-failed || true
    exit 1
fi
if ! chmod 600 "$LOCK_FILE"; then
    echo "$(date -Iseconds) ERROR: Could not secure claim lock." >> "$LOG_FILE"
    record_failure configuration-failed || true
    exit 1
fi
flock -n -E 75 9
lock_status=$?
if [ "$lock_status" -eq 75 ]; then
    echo "$(date -Iseconds) INFO: Another credit claim is already running; skipping." >> "$LOG_FILE"
    exit 0
fi
if [ "$lock_status" -ne 0 ]; then
    echo "$(date -Iseconds) ERROR: Could not acquire claim lock." >> "$LOG_FILE"
    record_failure configuration-failed || true
    exit 1
fi

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

    if ! mkdir -p "$TIMER_DROPIN_DIR"; then
        echo "$(date -Iseconds) ERROR: Could not create timer drop-in directory." >> "$LOG_FILE"
        return 1
    fi
    if ! tmp_file=$(mktemp "$TIMER_DROPIN_DIR/.schedule.XXXXXX"); then
        echo "$(date -Iseconds) ERROR: Could not create temporary timer schedule." >> "$LOG_FILE"
        return 1
    fi
    TEMP_FILES=("$tmp_file")
    if ! {
        echo "[Timer]"
        echo "OnCalendar="
        echo "OnCalendar=*-*-* $next_time"
    } > "$tmp_file"; then
        echo "$(date -Iseconds) ERROR: Could not write temporary timer schedule." >> "$LOG_FILE"
        rm -f "$tmp_file"
        TEMP_FILES=()
        return 1
    fi
    if ! mv "$tmp_file" "$TIMER_OVERRIDE"; then
        echo "$(date -Iseconds) ERROR: Could not install timer schedule." >> "$LOG_FILE"
        rm -f "$tmp_file"
        TEMP_FILES=()
        return 1
    fi
    TEMP_FILES=()

    if ! systemctl --user daemon-reload; then
        echo "$(date -Iseconds) ERROR: Could not reload systemd after timer update." >> "$LOG_FILE"
        return 1
    fi
    if ! systemctl --user restart "$TIMER_NAME"; then
        echo "$(date -Iseconds) ERROR: Could not restart $TIMER_NAME after timer update." >> "$LOG_FILE"
        return 1
    fi

    echo "$(date -Iseconds) timer moved from $current_time to $next_time" >> "$LOG_FILE"
}

if [ ! -f "$TOKEN_FILE" ] || [ ! -r "$TOKEN_FILE" ] || [ ! -s "$TOKEN_FILE" ]; then
    echo "$(date -Iseconds) ERROR: Token file is missing, unreadable, or empty at $TOKEN_FILE" >> "$LOG_FILE"
    record_failure configuration-failed || true
    exit 1
fi

if [ ! -f "$URL_FILE" ] || [ ! -r "$URL_FILE" ] || [ ! -s "$URL_FILE" ]; then
    echo "$(date -Iseconds) ERROR: URL file is missing, unreadable, or empty at $URL_FILE" >> "$LOG_FILE"
    record_failure configuration-failed || true
    exit 1
fi

if ! URL=$(cat "$URL_FILE") || [ -z "$URL" ]; then
    echo "$(date -Iseconds) ERROR: Could not read a non-empty API URL." >> "$LOG_FILE"
    record_failure configuration-failed || true
    exit 1
fi

perform_claim() {
    local token curl_err response_file curl_status

    if ! token=$(cat "$TOKEN_FILE") || [ -z "$token" ]; then
        echo "$(date -Iseconds) ERROR: Could not read a non-empty token." >> "$LOG_FILE"
        return 2
    fi
    curl_err=$(mktemp)
    response_file=$(mktemp)
    TEMP_FILES=("$curl_err" "$response_file")
    HTTP_STATUS=$(printf 'header = "Authorization: Bearer %s"\n' "$token" \
        | curl --config - -sS -o "$response_file" -w "%{http_code}" -X POST "$URL" \
            -H "Content-Type: application/json" 2>"$curl_err")
    curl_status=$?
    RESPONSE=$(cat "$response_file")

    if [ "$curl_status" -ne 0 ]; then
        echo "$(date -Iseconds) ERROR: curl failed: $(cat "$curl_err")" >> "$LOG_FILE"
        rm -f "$curl_err" "$response_file"
        TEMP_FILES=()
        return 1
    fi
    rm -f "$curl_err" "$response_file"
    TEMP_FILES=()

    CODE=$(echo "$RESPONSE" | grep -o '"code":[0-9]*' | head -1 | cut -d: -f2)
    MSG=$(echo "$RESPONSE" | grep -o '"msg":"[^"]*"' | head -1 | cut -d'"' -f4)
    if [ -z "$MSG" ]; then
        MSG=$(echo "$RESPONSE" | grep -o '"Error":"[^"]*"' | head -1 | cut -d'"' -f4)
    fi
}

is_auth_rejection() {
    [ "$HTTP_STATUS" = "401" ] || [ "$HTTP_STATUS" = "403" ] \
        || [ "$CODE" = "401" ] || [ "$CODE" = "403" ]
}

log_result() {
    local attempt=$1
    echo "$(date -Iseconds) attempt=$attempt http=$HTTP_STATUS code=$CODE msg=$MSG" >> "$LOG_FILE"
}

perform_claim
claim_status=$?
if [ "$claim_status" -ne 0 ]; then
    if [ "$claim_status" -eq 2 ]; then
        record_failure configuration-failed || true
    else
        record_failure claim-request-failed || true
    fi
    exit 1
fi
log_result initial

if is_auth_rejection; then
    echo "$(date -Iseconds) INFO: Token rejected; attempting one headless refresh." >> "$LOG_FILE"
    refresh_output=$(node "$REFRESH_SCRIPT" 2>&1)
    refresh_status=$?
    if [ -n "$refresh_output" ]; then
        while IFS= read -r line; do
            echo "$(date -Iseconds) refresh: $line" >> "$LOG_FILE"
        done <<< "$refresh_output"
    fi
    if [ "$refresh_status" -ne 0 ]; then
        echo "$(date -Iseconds) WARNING: Headless refresh failed; visible Chrome login may be required." >> "$LOG_FILE"
        record_failure login-required || true
        exit 1
    fi

    perform_claim
    claim_status=$?
    if [ "$claim_status" -ne 0 ]; then
        if [ "$claim_status" -eq 2 ]; then
            record_failure configuration-failed || true
        else
            record_failure claim-request-failed || true
        fi
        exit 1
    fi
    log_result retry
    if is_auth_rejection; then
        echo "$(date -Iseconds) WARNING: Refreshed token was rejected; not retrying again." >> "$LOG_FILE"
        record_failure refreshed-token-rejected || true
        exit 1
    fi
fi

if [ "$CODE" = "400" ] && [ "$MSG" = "not in time" ]; then
    clear_failure_state
    exit 0
fi

if [ "$CODE" = "200" ]; then
    if delay_timer_after_success "$RESPONSE"; then
        clear_failure_state
        exit 0
    fi
    record_failure schedule-failed || true
    exit 1
fi

record_failure unexpected-api-response || true
exit 1
