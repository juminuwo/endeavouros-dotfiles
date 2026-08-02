#!/usr/bin/env python3
"""Deliver deduplicated credit-claim failures through Hermes Discord."""

from __future__ import annotations

import argparse
import fcntl
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
        "Credit claim received an unexpected API result and stopped without retrying.\n\n"
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
    stored = read_json(failure_path)
    invocation_id = systemd_property(systemctl, "InvocationID")
    active_state = systemd_property(systemctl, "ActiveState")

    if active_state == "failed":
        if stored:
            category = stored.get("category")
            stored_invocation = stored.get("invocation_id")
            if (
                category in MESSAGES
                and invocation_id
                and stored_invocation == invocation_id
            ):
                return str(category), stored

        generic = {
            "version": 1,
            "invocation_id": invocation_id or "unknown",
            "category": "generic-failure",
        }
        atomic_write_json(failure_path, generic)
        return "generic-failure", generic

    if stored:
        category = stored.get("category")
        stored_invocation = stored.get("invocation_id")
        if category in MESSAGES and (
            stored_invocation == "manual"
            or not invocation_id
            or stored_invocation == invocation_id
        ):
            return str(category), stored

    return None


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
        failure = current_failure(failure_path, systemctl)
        if not failure:
            return 0
        category, state = failure

        notified = read_json(notified_path)
        if notified and notified.get("category") == category:
            return 0

        message = MESSAGES[category] + CHECKS
        if send_message(
            hermes, target, "[MAIN] Credit claim failed", message
        ) != 0:
            print("Credit-claim Discord notification delivery failed.", file=sys.stderr)
            return 1

        atomic_write_json(
            notified_path,
            {
                "version": 1,
                "category": category,
                "invocation_id": state.get("invocation_id", "unknown"),
            },
        )
        return 0


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
            "Test successful. Credit-claim failures will be delivered here through Hermes. No action is required.",
        )
    return notify(config_dir, hermes, systemctl, target)


if __name__ == "__main__":
    raise SystemExit(main())
