#!/usr/bin/env python3
"""Deliver terminal credit-claim outcomes through Hermes Discord."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


DEFAULT_CONFIG_DIR = Path.home() / ".config/credit-claim"
DEFAULT_HERMES = "/home/howis/.local/bin/hermes"
DEFAULT_SYSTEMCTL = "/usr/bin/systemctl"
DEFAULT_TARGET = "discord:isitokaymimi"

MESSAGES = {
    "success": "Credits claimed successfully.",
    "not-in-time": "Account is not eligible to claim yet. The next scheduled run will try again.",
    "retries-exhausted": "Credit claim failed after all scheduled retries. The next daily run will try again.",
    "configuration-failed": (
        "Credit claim configuration is missing or unreadable.\n\n"
        "Check the private files under `~/.config/credit-claim/`, then run "
        "`systemctl --user start credit-claim.service`."
    ),
    "claim-request-failed": (
        "Credit claim could not reach or complete the API request. This may be a network or upstream-service failure.\n\n"
        "The next scheduled run will try again."
    ),
    "login-required": (
        "Credit claim could not refresh its monthly token. The dedicated Chrome session likely needs your login.\n\n"
        "Run `~/git/endeavouros-dotfiles/config/host/credit-claim/open-profile.sh`, "
        "sign in, close that Chrome window, then run "
        "`systemctl --user start credit-claim.service`."
    ),
    "refreshed-token-rejected": (
        "Credit claim refreshed its token, but the API rejected the replacement.\n\n"
        "Run `~/git/endeavouros-dotfiles/config/host/credit-claim/open-profile.sh`, "
        "sign in again, close that Chrome window, then retry the service."
    ),
    "schedule-failed": (
        "The credit was claimed, but the next timer schedule could not be installed or restarted.\n\n"
        "Check `credit-claim.timer` before the next day."
    ),
    "unexpected-api-response": (
        "Credit claim received an unexpected API result and stopped.\n\n"
        "Inspect the local service status and claim log."
    ),
    "generic-failure": (
        "Credit claim failed or timed out before it could record a specific cause.\n\n"
        "Inspect the local service status and claim log."
    ),
}

CHECKS = (
    "\n\nUseful checks:\n"
    "`systemctl --user status credit-claim.service --no-pager`\n"
    "`tail -n 20 ~/.config/credit-claim/claim.log`"
)


def read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def atomic_write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def systemd_property(systemctl: str, property_name: str) -> str | None:
    try:
        result = subprocess.run(
            [
                systemctl,
                "--user",
                "show",
                "credit-claim.service",
                f"--property={property_name}",
                "--value",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def current_failure(
    failure_path: Path, systemctl: str
) -> tuple[str, dict[str, object]] | None:
    """Recover legacy outcomes and abnormal exits; queued outcomes are authoritative."""
    invocation_id = systemd_property(systemctl, "InvocationID")
    active_state = systemd_property(systemctl, "ActiveState")
    if active_state in {"active", "activating", "deactivating", "reloading"}:
        return None
    stored = read_json(failure_path)
    if active_state == "failed":
        if stored and stored.get("category") in MESSAGES and invocation_id and stored.get("invocation_id") == invocation_id:
            return str(stored["category"]), stored
        # A pending record can survive a crash before failure.json is replaced.
        for path in (failure_path.parent / "outcomes").glob("*.json"):
            queued = read_json(path)
            if queued and invocation_id and queued.get("invocation_id") == invocation_id and queued.get("category") in MESSAGES:
                return str(queued["category"]), queued
        generic = {
            "version": 2,
            "invocation_id": invocation_id or "unknown",
            "category": "generic-failure",
        }
        atomic_write_json(failure_path, generic)
        return "generic-failure", generic
    if stored and stored.get("category") in MESSAGES:
        if stored.get("version") == 2 or stored.get("invocation_id") == "manual" or not invocation_id or stored.get("invocation_id") == invocation_id:
            return str(stored["category"]), stored
    return None


def outcome_key(state: dict[str, object]) -> str:
    invocation = state.get("invocation_id", "unknown")
    # Old manual runs shared an ID. Include their timestamp when available.
    identity = [invocation]
    if invocation in {"manual", "unknown"}:
        identity += [state.get("timestamp"), state.get("category")]
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def terminal_message(category: str, state: dict[str, object]) -> str:
    conditions = {
        "success": "success",
        "not-in-time": "not in time",
        "retries-exhausted": "retries exhausted",
        "configuration-failed": "configuration failure",
        "claim-request-failed": "permanent request failure",
        "login-required": "authentication failure",
        "refreshed-token-rejected": "authentication failure",
        "schedule-failed": "schedule failure after successful claim",
        "unexpected-api-response": "unexpected API response",
        "generic-failure": "service failure or timeout",
    }
    message = MESSAGES[category] + "\n\nStop condition: " + conditions[category] + "."
    retries, attempts = state.get("retry_count"), state.get("attempts")
    if type(retries) is int and 0 <= retries <= 3:
        message += f"\nClaim retries: {retries}."
    if type(attempts) is int and 0 <= attempts <= 5:
        message += f" Total claim attempts: {attempts}."
    status = state.get("http_status")
    if isinstance(status, str) and len(status) == 3 and status.isascii() and status.isdigit() and status != "000":
        message += f"\nLast HTTP status: {status}."
    curl_status = state.get("curl_status")
    if type(curl_status) is int and 0 < curl_status <= 99:
        message += f"\nLast curl exit status: {curl_status}."
    if category not in {"success", "not-in-time"}:
        message += CHECKS
    return message


def send_message(hermes: str, target: str, subject: str, message: str) -> int:
    try:
        result = subprocess.run(
            [
                hermes,
                "send",
                "--to",
                target,
                "--subject",
                subject,
                "--quiet",
                "--file",
                "-",
            ],
            input=message,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1
    return 0 if result.returncode == 0 else 1


def notify(config_dir: Path, hermes: str, systemctl: str, target: str) -> int:
    config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(config_dir, 0o700)
    lock_path = config_dir / "notification.lock"
    failure_path = config_dir / "failure.json"
    notified_path = config_dir / "notified.json"

    with lock_path.open("a", encoding="utf-8") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        outcomes_dir = config_dir / "outcomes"
        delivered_dir = config_dir / "delivered"
        queued_keys = {
            outcome_key(state)
            for path in outcomes_dir.glob("*.json")
            if (state := read_json(path)) and state.get("category") in MESSAGES
        }
        # Import a legacy outcome or abnormal termination into the durable queue.
        failure = current_failure(failure_path, systemctl)
        if failure:
            category, state = failure
            key = outcome_key(state)
            notified = read_json(notified_path)
            legacy_delivered = (
                state.get("version") == 1 and notified
                and notified.get("category") == category
                and notified.get("invocation_id") == state.get("invocation_id")
            )
            if legacy_delivered:
                atomic_write_json(delivered_dir / f"{key}.json", state)
            elif key not in queued_keys and not (delivered_dir / f"{key}.json").exists():
                atomic_write_json(outcomes_dir / f"{key}.json", state)

        failed = False
        seen = set()
        for path in sorted(outcomes_dir.glob("*.json")):
            state = read_json(path)
            if not state or state.get("category") not in MESSAGES:
                # Never send arbitrary data from corrupted or unknown records.
                continue
            category = str(state["category"])
            key = outcome_key(state)
            marker = delivered_dir / f"{key}.json"
            if marker.exists():
                path.unlink(missing_ok=True)
                continue
            if key in seen:
                continue
            seen.add(key)
            subject = "[MAIN] Credit claim " + ("succeeded" if category == "success" else "stopped")
            if send_message(hermes, target, subject, terminal_message(category, state)) != 0:
                print("Credit-claim Discord notification delivery failed.", file=sys.stderr)
                failed = True
                break
            # Retain small per-invocation receipts so failure.json or delayed
            # duplicate queue writes cannot cause another notification.
            receipt = {"version": 2, "category": category, "invocation_id": state.get("invocation_id", "unknown")}
            atomic_write_json(marker, receipt)
            atomic_write_json(notified_path, receipt)
            path.unlink(missing_ok=True)
        return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--test",
        action="store_true",
        help="send a test message without changing notification state",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_dir = Path(
        os.environ.get("CREDIT_CLAIM_CONFIG_DIR", str(DEFAULT_CONFIG_DIR))
    ).expanduser()
    hermes = os.environ.get("CREDIT_CLAIM_HERMES_BIN", DEFAULT_HERMES)
    systemctl = os.environ.get("CREDIT_CLAIM_SYSTEMCTL_BIN", DEFAULT_SYSTEMCTL)
    target = os.environ.get("CREDIT_CLAIM_DISCORD_TARGET", DEFAULT_TARGET)

    if args.test:
        return send_message(
            hermes,
            target,
            "[MAIN] Credit claim notifications enabled",
            "Test successful. Terminal credit-claim outcomes will be delivered here through Hermes. No action is required.",
        )
    return notify(config_dir, hermes, systemctl, target)


if __name__ == "__main__":
    raise SystemExit(main())
