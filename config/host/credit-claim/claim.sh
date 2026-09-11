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
OUTCOMES_DIR="$CONFIG_DIR/outcomes"
REFRESH_SCRIPT=${CREDIT_CLAIM_REFRESH_SCRIPT:-"$SCRIPT_DIR/refresh-token.mjs"}
TIMER_NAME="credit-claim.timer"
TIMER_DROPIN_DIR="$HOME/.config/systemd/user/$TIMER_NAME.d"
TIMER_OVERRIDE="$TIMER_DROPIN_DIR/schedule.conf"
DEFAULT_TIMER_TIME="10:10:00"
SUCCESS_DELAY_SECONDS=30
TEMP_FILES=()
RETRY_DELAYS=(300 900 1800)
RETRY_COUNT=0
ATTEMPTS=0
CURL_STATUS=0
HTTP_STATUS=000
RUN_ID=${INVOCATION_ID:-}
if [[ ! "$RUN_ID" =~ ^[A-Fa-f0-9]{32}$ ]]; then
    RUN_ID=$(tr -d '-' < /proc/sys/kernel/random/uuid)
fi

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

# One durable terminal record per invocation; intermediate errors never notify.
record_outcome() {
    local category=$1 timestamp tmp_file status
    case "$category" in
        success|not-in-time|retries-exhausted|configuration-failed|claim-request-failed|login-required|refreshed-token-rejected|schedule-failed|unexpected-api-response) ;;
        *) category=generic-failure ;;
    esac
    timestamp=$(date -Iseconds)
    status=$HTTP_STATUS
    [[ "$status" =~ ^[0-9]{3}$ ]] || status=000
    flock 8
    if ! mkdir -p -m 700 "$OUTCOMES_DIR"; then
        flock -u 8
        return 1
    fi
    tmp_file=$(mktemp "$CONFIG_DIR/.outcome.XXXXXX") || { flock -u 8; return 1; }
    if ! printf '{"version":2,"invocation_id":"%s","category":"%s","timestamp":"%s","retry_count":%d,"attempts":%d,"http_status":"%s","curl_status":%d}\n' \
        "$RUN_ID" "$category" "$timestamp" "$RETRY_COUNT" "$ATTEMPTS" "$status" "$CURL_STATUS" > "$tmp_file" \
        || ! mv "$tmp_file" "$OUTCOMES_DIR/$RUN_ID.json"; then
        rm -f "$tmp_file"
        flock -u 8
        return 1
    fi
    # Compatibility snapshot; queued outcomes survive subsequent runs.
    tmp_file=$(mktemp "$CONFIG_DIR/.outcome.XXXXXX") || { flock -u 8; return 1; }
    if ! cp "$OUTCOMES_DIR/$RUN_ID.json" "$tmp_file" || ! mv "$tmp_file" "$FAILURE_FILE"; then
        rm -f "$tmp_file"
        flock -u 8
        return 1
    fi
    flock -u 8
}

if ! exec 9>"$LOCK_FILE"; then
    echo "$(date -Iseconds) ERROR: Could not open claim lock." >> "$LOG_FILE"
    record_outcome configuration-failed || true
    exit 1
fi
if ! chmod 600 "$LOCK_FILE"; then
    echo "$(date -Iseconds) ERROR: Could not secure claim lock." >> "$LOG_FILE"
    record_outcome configuration-failed || true
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
    record_outcome configuration-failed || true
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
    record_outcome configuration-failed || true
    exit 1
fi

if [ ! -f "$URL_FILE" ] || [ ! -r "$URL_FILE" ] || [ ! -s "$URL_FILE" ]; then
    echo "$(date -Iseconds) ERROR: URL file is missing, unreadable, or empty at $URL_FILE" >> "$LOG_FILE"
    record_outcome configuration-failed || true
    exit 1
fi

if ! URL=$(cat "$URL_FILE") || [ -z "$URL" ]; then
    echo "$(date -Iseconds) ERROR: Could not read a non-empty API URL." >> "$LOG_FILE"
    record_outcome configuration-failed || true
    exit 1
fi

perform_claim() {
    local token curl_err response_file
    HTTP_STATUS=000
    CURL_STATUS=0
    RESPONSE=
    CODE=
    MSG=

    if ! token=$(cat "$TOKEN_FILE") || [ -z "$token" ]; then
        echo "$(date -Iseconds) ERROR: Could not read a non-empty token." >> "$LOG_FILE"
        return 2
    fi
    curl_err=$(mktemp) || return 2
    response_file=$(mktemp) || { rm -f "$curl_err"; return 2; }
    TEMP_FILES=("$curl_err" "$response_file")
    HTTP_STATUS=$(printf 'header = "Authorization: Bearer %s"\n' "$token" \
        | curl --connect-timeout 20 --max-time 100 --config - -sS -o "$response_file" -w "%{http_code}" -X POST "$URL" \
            -H "Content-Type: application/json" 2>"$curl_err")
    CURL_STATUS=$?
    RESPONSE=$(cat "$response_file")

    if [ "$CURL_STATUS" -ne 0 ]; then
        echo "$(date -Iseconds) ERROR: curl failed: $(cat "$curl_err")" >> "$LOG_FILE"
        rm -f "$curl_err" "$response_file"
        TEMP_FILES=()
        return 1
    fi
    rm -f "$curl_err" "$response_file"
    TEMP_FILES=()

    # Parse the envelope, including whitespace, without trusting an arbitrary
    # nested code or a success-looking body on a failed HTTP response.
    local fields
    fields=$(printf '%s' "$RESPONSE" | python3 -c '
import json, sys
try:
    value = json.load(sys.stdin)
    if not isinstance(value, dict): raise ValueError()
    code = value.get("code")
    msg = value.get("msg", value.get("Error", ""))
    print(code if type(code) is int else "")
    print(msg.replace("\n", " ").replace("\r", " ") if isinstance(msg, str) else "")
except (ValueError, TypeError):
    print("")
')
    CODE=${fields%%$'\n'*}
    if [[ "$fields" == *$'\n'* ]]; then MSG=${fields#*$'\n'}; fi

}

is_auth_rejection() {
    [ "$HTTP_STATUS" = "401" ] || [ "$HTTP_STATUS" = "403" ] \
        || [ "$CODE" = "401" ] || [ "$CODE" = "403" ]
}

log_result() {
    local attempt=$1
    echo "$(date -Iseconds) attempt=$attempt http=$HTTP_STATUS code=$CODE msg=$MSG" >> "$LOG_FILE"
}

# Approved 2026-09-11: bounded 522 retries accept the uncertain POST outcome,
# relying on the observed server cooldown. Other ambiguous failures stay daily.
refresh_used=0
while true; do
    ATTEMPTS=$((ATTEMPTS + 1))
    perform_claim
    claim_status=$?
    log_result "$ATTEMPTS"
    if [ "$claim_status" -eq 2 ]; then
        record_outcome configuration-failed
        exit 1
    fi

    if { [ "$claim_status" -eq 1 ] && [[ "$CURL_STATUS" =~ ^(5|6|7)$ ]]; } \
        || { [ "$claim_status" -eq 0 ] && [ "$HTTP_STATUS" = 522 ]; }; then
        if [ "$RETRY_COUNT" -ge "${#RETRY_DELAYS[@]}" ]; then
            record_outcome retries-exhausted
            exit 1
        fi
        delay=${RETRY_DELAYS[$RETRY_COUNT]}
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo "$(date -Iseconds) INFO: transient failure; retry=$RETRY_COUNT wait_seconds=$delay" >> "$LOG_FILE"
        sleep "$delay" || { record_outcome generic-failure; exit 1; }
        continue
    fi
    if [ "$claim_status" -ne 0 ]; then
        record_outcome claim-request-failed
        exit 1
    fi

    if is_auth_rejection; then
        if [ "$refresh_used" -eq 1 ]; then
            record_outcome refreshed-token-rejected
            exit 1
        fi
        refresh_used=1
        echo "$(date -Iseconds) INFO: Token rejected; attempting one headless refresh." >> "$LOG_FILE"
        refresh_output=$(node "$REFRESH_SCRIPT" 2>&1)
        refresh_status=$?
        if [ -n "$refresh_output" ]; then
            while IFS= read -r line; do
                echo "$(date -Iseconds) refresh: $line" >> "$LOG_FILE"
            done <<< "$refresh_output"
        fi
        if [ "$refresh_status" -ne 0 ]; then
            record_outcome login-required
            exit 1
        fi
        continue
    fi

    if [[ "$HTTP_STATUS" =~ ^2[0-9]{2}$ ]]; then
        if [ "$CODE" = 400 ] && [ "$MSG" = 'not in time' ]; then
            record_outcome not-in-time
            exit $?
        fi
        if [ "$CODE" = 200 ]; then
            if delay_timer_after_success "$RESPONSE"; then
                record_outcome success
                exit $?
            fi
            record_outcome schedule-failed
            exit 1
        fi
    fi
    record_outcome unexpected-api-response
    exit 1
done
