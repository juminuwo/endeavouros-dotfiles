#!/usr/bin/env python3

import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


TEST_DIR = Path(__file__).resolve().parent
NOTIFIER = TEST_DIR.parent / "notify-failure.py"
REPO_ROOT = TEST_DIR.parents[3]


class NotifyFailureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="credit-claim-notify-test.")
        self.root = Path(self.temporary.name)
        self.config = self.root / "config"
        self.config.mkdir(mode=0o700)
        self.capture = self.root / "messages.jsonl"
        self.hermes = self.root / "hermes"
        self.systemctl = self.root / "systemctl"
        self.hermes.write_text(
            """#!/usr/bin/env python3
import json, os, sys
with open(os.environ['TEST_CAPTURE'], 'a', encoding='utf-8') as handle:
    handle.write(json.dumps({'args': sys.argv[1:], 'body': sys.stdin.read()}) + '\\n')
raise SystemExit(int(os.environ.get('TEST_HERMES_EXIT', '0')))
""",
            encoding="utf-8",
        )
        self.systemctl.write_text(
            """#!/bin/bash
case "$*" in
    *InvocationID*) printf '%s\\n' "${TEST_INVOCATION_ID:-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}" ;;
    *ActiveState*) printf '%s\\n' "${TEST_ACTIVE_STATE:-failed}" ;;
    *) exit 1 ;;
esac
""",
            encoding="utf-8",
        )
        self.hermes.chmod(0o755)
        self.systemctl.chmod(0o755)
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "CREDIT_CLAIM_CONFIG_DIR": str(self.config),
                "CREDIT_CLAIM_HERMES_BIN": str(self.hermes),
                "CREDIT_CLAIM_SYSTEMCTL_BIN": str(self.systemctl),
                "CREDIT_CLAIM_DISCORD_TARGET": "discord:isitokaymimi",
                "TEST_CAPTURE": str(self.capture),
                "TEST_INVOCATION_ID": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "TEST_ACTIVE_STATE": "failed",
            }
        )
        (self.config / "token").write_text("sentinel-secret-token\n", encoding="utf-8")
        (self.config / "api_url").write_text(
            "https://private.example.invalid/api/claim\n", encoding="utf-8"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def write_failure(self, category, invocation_id=None):
        value = {
            "version": 1,
            "category": category,
            "invocation_id": invocation_id or self.environment["TEST_INVOCATION_ID"],
        }
        (self.config / "failure.json").write_text(
            json.dumps(value), encoding="utf-8"
        )

    def run_notifier(self, *arguments, check=False):
        return subprocess.run(
            [str(NOTIFIER), *arguments],
            env=self.environment,
            check=check,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def messages(self):
        if not self.capture.exists():
            return []
        return [json.loads(line) for line in self.capture.read_text().splitlines()]

    def test_no_failure_and_inactive_service_stays_silent(self):
        self.environment["TEST_ACTIVE_STATE"] = "inactive"
        result = self.run_notifier()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.messages(), [])

    def test_login_failure_sends_once_and_records_delivery(self):
        self.write_failure("login-required")
        self.assertEqual(self.run_notifier().returncode, 0)
        self.assertEqual(self.run_notifier().returncode, 0)

        messages = self.messages()
        self.assertEqual(len(messages), 1)
        self.assertIn("discord:isitokaymimi", messages[0]["args"])
        self.assertIn("open-profile.sh", messages[0]["body"])
        self.assertNotIn("sentinel-secret-token", messages[0]["body"])
        self.assertNotIn("private.example.invalid", messages[0]["body"])
        notified = self.config / "notified.json"
        self.assertEqual(json.loads(notified.read_text())["category"], "login-required")
        self.assertEqual(stat.S_IMODE(notified.stat().st_mode), 0o600)

    def test_changed_failure_category_sends_again(self):
        self.write_failure("login-required")
        self.assertEqual(self.run_notifier().returncode, 0)
        self.write_failure("schedule-failed")
        self.assertEqual(self.run_notifier().returncode, 0)
        self.assertEqual(len(self.messages()), 2)
        self.assertIn("timer schedule", self.messages()[1]["body"])

    def test_failed_delivery_remains_pending_until_success(self):
        self.write_failure("claim-request-failed")
        self.environment["TEST_HERMES_EXIT"] = "1"
        self.assertEqual(self.run_notifier().returncode, 1)
        self.assertFalse((self.config / "notified.json").exists())

        self.environment["TEST_HERMES_EXIT"] = "0"
        self.assertEqual(self.run_notifier().returncode, 0)
        self.assertEqual(len(self.messages()), 2)
        self.assertEqual(
            json.loads((self.config / "notified.json").read_text())["category"],
            "claim-request-failed",
        )

    def test_stale_failure_record_becomes_generic_for_current_failed_invocation(self):
        self.write_failure("login-required", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        self.assertEqual(self.run_notifier().returncode, 0)
        self.assertIn("failed or timed out", self.messages()[0]["body"])
        self.assertEqual(
            json.loads((self.config / "failure.json").read_text())["category"],
            "generic-failure",
        )

    def test_stale_delivered_manual_failure_cannot_mask_current_systemd_failure(self):
        self.write_failure("login-required", "manual")
        (self.config / "notified.json").write_text(
            json.dumps({"version": 1, "category": "login-required"}),
            encoding="utf-8",
        )

        self.assertEqual(self.run_notifier().returncode, 0)
        self.assertEqual(len(self.messages()), 1)
        self.assertIn("failed or timed out", self.messages()[0]["body"])
        self.assertEqual(
            json.loads((self.config / "failure.json").read_text())["category"],
            "generic-failure",
        )

    def test_test_message_does_not_create_delivery_state(self):
        self.environment["TEST_ACTIVE_STATE"] = "inactive"
        self.assertEqual(self.run_notifier("--test").returncode, 0)
        self.assertIn("No action is required", self.messages()[0]["body"])
        self.assertFalse((self.config / "notified.json").exists())

    def test_repo_units_wire_failure_and_retry_timer(self):
        service = (
            REPO_ROOT / "config/host/systemd/user/credit-claim.service"
        ).read_text()
        retry_timer = (
            REPO_ROOT / "config/host/systemd/user/credit-claim-notify.timer"
        ).read_text()
        host_install = (REPO_ROOT / "host-install").read_text()
        self.assertIn("OnFailure=credit-claim-notify.service", service)
        self.assertIn("OnUnitActiveSec=15min", retry_timer)
        self.assertIn("credit-claim-notify.timer", host_install)


if __name__ == "__main__":
    unittest.main()
