#!/bin/bash
set -euo pipefail

TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CLAIM_SCRIPT=$(cd -- "$TEST_DIR/.." && pwd)/claim.sh
TEST_ROOT=$(mktemp -d)
FAKE_BIN="$TEST_ROOT/bin"
mkdir -p "$FAKE_BIN"
trap 'rm -rf -- "$TEST_ROOT"' EXIT

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

assert_equal() {
    local expected=$1 actual=$2 label=$3
    [ "$expected" = "$actual" ] || fail "$label: expected '$expected', got '$actual'"
}

line_count() {
    local path=$1
    if [ -f "$path" ]; then
        wc -l < "$path" | tr -d ' '
    else
        echo 0
    fi
}

cat > "$FAKE_BIN/curl" <<'SH'
#!/bin/bash
set -euo pipefail
for arg in "$@"; do
    case "$arg" in
        *sentinel-secret-token*|*refreshed-test-token*)
            echo 'credential appeared in curl process arguments' >&2
            exit 98
            ;;
    esac
done
[[ " $* " == *" --connect-timeout 20 "* ]] || exit 98
[[ " $* " == *" --max-time 100 "* ]] || exit 98
output=
while [ "$#" -gt 0 ]; do
    case "$1" in
        -o)
            output=$2
            shift 2
            ;;
        -w|-X|-H|--connect-timeout|--max-time)
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done
count_file="$CREDIT_CLAIM_TEST_STATE/curl-count"
count=$(($(wc -l < "$count_file" 2>/dev/null || echo 0) + 1))
echo "$count" >> "$count_file"

case "$CREDIT_CLAIM_TEST_SCENARIO:$count" in
    success:*|timer-update-fails:*)
        status=200
        response='{"code":200,"msg":"success","next_claim_time":"2030-01-01T10:10:00Z"}'
        ;;
    not-in-time:*)
        status=200
        response='{"code":400,"msg":"not in time"}'
        ;;
    auth-then-success:1|auth-then-claim-success:1|refresh-fails:1|retry-auth:1)
        status=401
        response='{"Error":"authentication rejected"}'
        ;;
    body-auth-then-success:1)
        status=200
        response='{"code":403,"msg":"authentication rejected"}'
        ;;
    auth-then-success:2|body-auth-then-success:2)
        status=200
        response='{"code":400,"msg":"not in time"}'
        ;;
    auth-then-claim-success:2)
        status=200
        response='{"code":200,"msg":"success","next_claim_time":"2030-01-01T10:10:00Z"}'
        ;;
    retry-auth:2)
        status=403
        response='{"Error":"authentication rejected again"}'
        ;;
    transient-success:1|transient-cooldown:1|exhausted:*|mixed:1|mixed:3|mixed-auth-fails:1|mixed-auth-fails:3)
        status=522
        response=''
        ;;
    transient-success:2|mixed:4|dns-success:2|connect-success:2|proxy-success:2)
        status=200
        response='{"code": 200, "msg": "success"}'
        ;;
    transient-cooldown:2)
        status=200
        response='{"code": 400, "msg": "not in time"}'
        ;;
    mixed:2|mixed-auth-fails:2|mixed-auth-fails:4)
        status=401
        response=''
        ;;
    dns-success:1) exit 6 ;;
    connect-success:1) exit 7 ;;
    proxy-success:1) exit 5 ;;
    excluded-timeout:*) exit 28 ;;
    misleading-success:*)
        status=500
        response='{"code":200,"msg":"success"}'
        ;;
    curl-fails:*)
        echo 'simulated network failure' >&2
        exit 7
        ;;
    *)
        status=500
        response='{"code":500,"msg":"unexpected test scenario"}'
        ;;
esac

printf '%s' "$response" > "$output"
printf '%s' "$status"
SH

cat > "$FAKE_BIN/node" <<'SH'
#!/bin/bash
set -euo pipefail
echo refresh >> "$CREDIT_CLAIM_TEST_STATE/refresh-count"
if [ "$CREDIT_CLAIM_TEST_SCENARIO" = refresh-fails ]; then
    echo 'ERROR: simulated refresh failure' >&2
    exit 1
fi
printf '%s\n' 'refreshed-test-token' > "$CREDIT_CLAIM_CONFIG_DIR/token"
chmod 600 "$CREDIT_CLAIM_CONFIG_DIR/token"
echo 'Headless token refresh succeeded; expires 2030-01-01T00:00:00.000Z'
SH

cat > "$FAKE_BIN/systemctl" <<'SH'
#!/bin/bash
set -euo pipefail
if [ "${1:-}" = --user ] && [ "${2:-}" = cat ]; then
    printf '%s\n' '[Timer]' 'OnCalendar=*-*-* 10:10:00'
    exit 0
fi
if [ "$CREDIT_CLAIM_TEST_SCENARIO" = timer-update-fails ] \
    && [ "${1:-}" = --user ] && [ "${2:-}" = daemon-reload ]; then
    exit 1
fi
echo "$*" >> "$CREDIT_CLAIM_TEST_STATE/systemctl-calls"
SH
cat > "$FAKE_BIN/sleep" <<'SH'
#!/bin/bash
set -euo pipefail
echo "$1" >> "$CREDIT_CLAIM_TEST_STATE/sleeps"
# No terminal state may be created while retrying.
[ ! -e "$CREDIT_CLAIM_CONFIG_DIR/failure.json" ]
if [ "${CREDIT_CLAIM_TEST_SCENARIO}" = transient-success ]; then
    # A simultaneous invocation must skip without another request or outcome.
    "$CREDIT_CLAIM_TEST_SCRIPT"
fi
SH
chmod +x "$FAKE_BIN/sleep"
chmod +x "$FAKE_BIN/curl" "$FAKE_BIN/node" "$FAKE_BIN/systemctl"

prepare_case() {
    local name=$1
    CASE_ROOT="$TEST_ROOT/$name"
    CASE_HOME="$CASE_ROOT/home"
    CASE_CONFIG="$CASE_HOME/.config/credit-claim"
    CASE_STATE="$CASE_ROOT/state"
    mkdir -p "$CASE_CONFIG" "$CASE_STATE"
    chmod 700 "$CASE_CONFIG"
    printf '%s\n' 'sentinel-secret-token' > "$CASE_CONFIG/token"
    printf '%s\n' 'https://example.invalid/api/claim' > "$CASE_CONFIG/api_url"
    chmod 600 "$CASE_CONFIG/token" "$CASE_CONFIG/api_url"
}

run_claim() {
    local scenario=$1
    env \
        HOME="$CASE_HOME" \
        PATH="$FAKE_BIN:/usr/bin" \
        CREDIT_CLAIM_CONFIG_DIR="$CASE_CONFIG" \
        CREDIT_CLAIM_REFRESH_SCRIPT="$CASE_ROOT/fake-refresh.mjs" \
        CREDIT_CLAIM_TEST_SCENARIO="$scenario" \
        CREDIT_CLAIM_TEST_STATE="$CASE_STATE" \
        CREDIT_CLAIM_TEST_SCRIPT="$CLAIM_SCRIPT" \
        "$CLAIM_SCRIPT"
}

prepare_case success
printf '%s\n' '{"category":"claim-request-failed"}' > "$CASE_CONFIG/failure.json"
printf '%s\n' '{"category":"claim-request-failed"}' > "$CASE_CONFIG/notified.json"
run_claim success
assert_equal 1 "$(line_count "$CASE_STATE/curl-count")" 'accepted claim request count'
assert_equal 0 "$(line_count "$CASE_STATE/refresh-count")" 'accepted claim refresh count'
assert_equal 2 "$(line_count "$CASE_STATE/systemctl-calls")" 'accepted claim timer mutation count'
! rg -q 'sentinel-secret-token' "$CASE_CONFIG/claim.log" || fail 'accepted claim leaked token'
rg -q '"category":"success"' "$CASE_CONFIG/failure.json" || fail 'success outcome missing'
[ -e "$CASE_CONFIG/notified.json" ] || fail 'old notification state unexpectedly deleted'

prepare_case not-in-time
run_claim not-in-time
assert_equal 1 "$(line_count "$CASE_STATE/curl-count")" 'not-in-time request count'
assert_equal 0 "$(line_count "$CASE_STATE/refresh-count")" 'not-in-time refresh count'
assert_equal 0 "$(line_count "$CASE_STATE/systemctl-calls")" 'not-in-time timer mutation count'

for scenario in auth-then-success body-auth-then-success; do
    prepare_case "$scenario"
    run_claim "$scenario"
    assert_equal 2 "$(line_count "$CASE_STATE/curl-count")" "$scenario request count"
    assert_equal 1 "$(line_count "$CASE_STATE/refresh-count")" "$scenario refresh count"
    ! rg -q 'sentinel-secret-token|refreshed-test-token' "$CASE_CONFIG/claim.log" || fail "$scenario leaked token"
done

prepare_case auth-then-claim-success
run_claim auth-then-claim-success
assert_equal 2 "$(line_count "$CASE_STATE/curl-count")" 'refresh then claim-success request count'
assert_equal 1 "$(line_count "$CASE_STATE/refresh-count")" 'refresh then claim-success refresh count'
assert_equal 2 "$(line_count "$CASE_STATE/systemctl-calls")" 'refresh then claim-success timer mutation count'
[ -f "$CASE_HOME/.config/systemd/user/credit-claim.timer.d/schedule.conf" ] \
    || fail 'refresh then claim-success schedule override missing'

prepare_case refresh-fails
if run_claim refresh-fails; then
    fail 'refresh failure unexpectedly succeeded'
fi
assert_equal 1 "$(line_count "$CASE_STATE/curl-count")" 'refresh failure request count'
assert_equal 1 "$(line_count "$CASE_STATE/refresh-count")" 'refresh failure refresh count'
assert_equal 'sentinel-secret-token' "$(<"$CASE_CONFIG/token")" 'refresh failure preserved token'
rg -q '"category":"login-required"' "$CASE_CONFIG/failure.json" \
    || fail 'refresh failure category missing'
assert_equal 600 "$(stat -c '%a' "$CASE_CONFIG/failure.json")" 'failure state mode'

prepare_case retry-auth
if run_claim retry-auth; then
    fail 'second auth rejection unexpectedly succeeded'
fi
assert_equal 2 "$(line_count "$CASE_STATE/curl-count")" 'second auth rejection request count'
assert_equal 1 "$(line_count "$CASE_STATE/refresh-count")" 'second auth rejection refresh count'
rg -q '"category":"refreshed-token-rejected"' "$CASE_CONFIG/failure.json" \
    || fail 'refreshed-token rejection category missing'

prepare_case curl-fails
if run_claim curl-fails; then
    fail 'curl failure unexpectedly succeeded'
fi
assert_equal 4 "$(line_count "$CASE_STATE/curl-count")" 'curl failure request count'
assert_equal 0 "$(line_count "$CASE_STATE/refresh-count")" 'curl failure refresh count'
rg -q '"category":"retries-exhausted"' "$CASE_CONFIG/failure.json" \
    || fail 'curl failure category missing'

prepare_case timer-update-fails
if run_claim timer-update-fails; then
    fail 'timer reload failure unexpectedly succeeded'
fi
! rg -q 'timer moved from' "$CASE_CONFIG/claim.log" || fail 'timer reload failure logged false success'
rg -q 'Could not reload systemd after timer update' "$CASE_CONFIG/claim.log" \
    || fail 'timer reload failure feedback missing'
rg -q '"category":"schedule-failed"' "$CASE_CONFIG/failure.json" \
    || fail 'timer reload failure category missing'

prepare_case unexpected-api
if run_claim unexpected-api; then
    fail 'unexpected API response unexpectedly succeeded'
fi
rg -q '"category":"unexpected-api-response"' "$CASE_CONFIG/failure.json" \
    || fail 'unexpected API failure category missing'

for config_case in missing-token empty-token unreadable-token missing-url empty-url unreadable-url; do
    prepare_case "$config_case"
    case "$config_case" in
        missing-token) rm "$CASE_CONFIG/token" ;;
        empty-token) : > "$CASE_CONFIG/token" ;;
        unreadable-token) chmod 000 "$CASE_CONFIG/token" ;;
        missing-url) rm "$CASE_CONFIG/api_url" ;;
        empty-url) : > "$CASE_CONFIG/api_url" ;;
        unreadable-url) chmod 000 "$CASE_CONFIG/api_url" ;;
    esac
    if run_claim success; then
        fail "$config_case unexpectedly succeeded"
    fi
    rg -q '"category":"configuration-failed"' "$CASE_CONFIG/failure.json" \
        || fail "$config_case configuration failure category missing"
    assert_equal 0 "$(line_count "$CASE_STATE/curl-count")" "$config_case request count"
done

prepare_case unusable-config
if env \
    HOME="$CASE_HOME" \
    PATH="$FAKE_BIN:/usr/bin" \
    CREDIT_CLAIM_CONFIG_DIR="/proc/credit-claim-review" \
    CREDIT_CLAIM_REFRESH_SCRIPT="$CASE_ROOT/fake-refresh.mjs" \
    CREDIT_CLAIM_TEST_SCENARIO=success \
    CREDIT_CLAIM_TEST_STATE="$CASE_STATE" \
    "$CLAIM_SCRIPT" >/dev/null 2>&1; then
    fail 'unusable config path unexpectedly succeeded'
fi
assert_equal 0 "$(line_count "$CASE_STATE/curl-count")" 'unusable config request count'

prepare_case locked
exec 8>"$CASE_CONFIG/claim.lock"
flock 8
run_claim success
flock -u 8
assert_equal 0 "$(line_count "$CASE_STATE/curl-count")" 'lock contention request count'
rg -q 'already running; skipping' "$CASE_CONFIG/claim.log" || fail 'lock contention feedback missing'

for scenario in transient-success dns-success connect-success proxy-success transient-cooldown mixed; do
    prepare_case "$scenario"
    run_claim "$scenario"
    expected=2
    [ "$scenario" != mixed ] || expected=4
    assert_equal "$expected" "$(line_count "$CASE_STATE/curl-count")" "$scenario request count"
    assert_equal 1 "$(find "$CASE_CONFIG/outcomes" -name '*.json' | wc -l | tr -d ' ')" "$scenario terminal outcome count"
    if [ "$scenario" = mixed ]; then
        assert_equal 1 "$(line_count "$CASE_STATE/refresh-count")" 'mixed refresh limit'
        assert_equal $'300\n900' "$(cat "$CASE_STATE/sleeps")" 'mixed delays'
    else
        assert_equal 300 "$(cat "$CASE_STATE/sleeps")" "$scenario delay"
    fi
    category=success
    [ "$scenario" != transient-cooldown ] || category=not-in-time
    rg -q "\"category\":\"$category\"" "$CASE_CONFIG/failure.json" || fail "$scenario terminal condition"
done

for scenario in exhausted mixed-auth-fails excluded-timeout misleading-success; do
    prepare_case "$scenario"
    if run_claim "$scenario"; then fail "$scenario unexpectedly succeeded"; fi
    case "$scenario" in
        exhausted) count=4; category=retries-exhausted
            assert_equal $'300\n900\n1800' "$(cat "$CASE_STATE/sleeps")" 'exhaustion delays' ;;
        mixed-auth-fails) count=4; category=refreshed-token-rejected ;;
        excluded-timeout) count=1; category=claim-request-failed ;;
        misleading-success) count=1; category=unexpected-api-response ;;
    esac
    assert_equal "$count" "$(line_count "$CASE_STATE/curl-count")" "$scenario count"
    assert_equal 0 "$(line_count "$CASE_STATE/systemctl-calls")" "$scenario schedule unchanged"
    rg -q "\"category\":\"$category\"" "$CASE_CONFIG/failure.json" || fail "$scenario category"
done

prepare_case repeated-manual
run_claim not-in-time
run_claim not-in-time
assert_equal 2 "$(find "$CASE_CONFIG/outcomes" -name '*.json' | wc -l | tr -d ' ')" 'manual invocation identities'

# Exercise focused installation with fake systemctl and an isolated destination.
prepare_case install-units
env XDG_CONFIG_HOME="$CASE_CONFIG" PATH="$FAKE_BIN:/usr/bin" \
    CREDIT_CLAIM_TEST_SCENARIO=install CREDIT_CLAIM_TEST_STATE="$CASE_STATE" \
    "$TEST_DIR/../../../../host-install" --user-unit credit-claim.service credit-claim-notify.service
cmp "$TEST_DIR/../../systemd/user/credit-claim.service" "$CASE_CONFIG/systemd/user/credit-claim.service"
assert_equal 1 "$(line_count "$CASE_STATE/systemctl-calls")" 'focused install reload'

echo 'claim workflow tests passed'
