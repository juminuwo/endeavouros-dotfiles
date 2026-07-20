from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
CUTOVER = REPO_ROOT / "config/host/systemd/hermes-driver-shield-cutover.sh"
OLD_UNIT = "hermes-gateway-driver-shield-slack.service"
NEW_UNIT = "hermes-gateway-driver-shield.service"


@pytest.fixture
def cutover_env(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    bin_dir = tmp_path / "bin"
    state_dir = tmp_path / "state"
    unit_dir = tmp_path / "systemd/user"
    profile_dir = tmp_path / "profile"
    backup_dir = tmp_path / "backup"
    for directory in (bin_dir, state_dir, unit_dir, profile_dir):
        directory.mkdir(parents=True)

    for relative in (
        "config.yaml",
        ".env",
        "auth.json",
        "plugins/driver-shield/plugin.yaml",
    ):
        path = profile_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test\n")

    (unit_dir / OLD_UNIT).write_text("old unit\n")
    (unit_dir / NEW_UNIT).write_text("new unit\n")
    (state_dir / OLD_UNIT).write_text("active\n")

    systemctl = bin_dir / "systemctl"
    systemctl.write_text(
        """#!/usr/bin/env bash
set -u
state_dir="$MOCK_SYSTEMCTL_STATE"
unit_dir="$MOCK_SYSTEMCTL_UNITS"
printf '%s\\n' "$*" >> "$MOCK_SYSTEMCTL_LOG"
[[ "${1:-}" == --user ]] && shift
command="${1:-}"
shift || true
case "$command" in
  cat)
    [[ -f "$unit_dir/${1:-}" ]]
    ;;
  daemon-reload)
    exit 0
    ;;
  is-active)
    unit="${1:-}"
    value=inactive
    [[ -f "$state_dir/$unit" ]] && value="$(tr -d '\\n' < "$state_dir/$unit")"
    printf '%s\\n' "$value"
    [[ "$value" == active ]]
    ;;
  disable)
    [[ "${1:-}" == --now ]] && shift
    unit="${1:-}"
    if [[ -f "$state_dir/stop-fail-$unit" ]]; then
      exit 1
    fi
    printf 'inactive\\n' > "$state_dir/$unit"
    ;;
  enable)
    [[ "${1:-}" == --now ]] && shift
    unit="${1:-}"
    if [[ -f "$state_dir/start-fail-$unit" ]]; then
      printf 'failed\\n' > "$state_dir/$unit"
      exit 1
    fi
    printf 'active\\n' > "$state_dir/$unit"
    ;;
  *)
    printf 'unexpected systemctl command: %s\\n' "$command" >&2
    exit 2
    ;;
esac
"""
    )
    systemctl.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "MOCK_SYSTEMCTL_STATE": str(state_dir),
            "MOCK_SYSTEMCTL_UNITS": str(unit_dir),
            "MOCK_SYSTEMCTL_LOG": str(tmp_path / "systemctl.log"),
            "HERMES_DRIVER_SHIELD_PROFILE_DIR": str(profile_dir),
            "HERMES_DRIVER_SHIELD_CUTOVER_BACKUP_DIR": str(backup_dir),
        }
    )
    return env, state_dir, unit_dir


def _run(env: dict[str, str], unit_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; hermes_driver_shield_cutover "$2"',
            "cutover-test",
            str(CUTOVER),
            str(unit_dir),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_aborts_if_old_gateway_does_not_stop(cutover_env):
    env, state_dir, unit_dir = cutover_env
    (state_dir / f"stop-fail-{OLD_UNIT}").touch()

    result = _run(env, unit_dir)

    assert result.returncode != 0
    assert (state_dir / OLD_UNIT).read_text().strip() == "active"
    assert not (state_dir / NEW_UNIT).exists()
    assert (unit_dir / OLD_UNIT).exists()


def test_profile_preflight_failure_leaves_old_gateway_running(cutover_env):
    env, state_dir, unit_dir = cutover_env
    (Path(env["HERMES_DRIVER_SHIELD_PROFILE_DIR"]) / "auth.json").unlink()

    result = _run(env, unit_dir)

    assert result.returncode != 0
    assert (state_dir / OLD_UNIT).read_text().strip() == "active"
    assert not (state_dir / NEW_UNIT).exists()
    assert (unit_dir / OLD_UNIT).exists()


def test_failed_replacement_start_restores_old_gateway(cutover_env):
    env, state_dir, unit_dir = cutover_env
    (state_dir / f"start-fail-{NEW_UNIT}").touch()

    result = _run(env, unit_dir)

    assert result.returncode != 0
    assert (state_dir / NEW_UNIT).read_text().strip() == "inactive"
    assert (state_dir / OLD_UNIT).read_text().strip() == "active"
    assert (unit_dir / OLD_UNIT).exists()


def test_successful_cutover_is_repeatable(cutover_env):
    env, state_dir, unit_dir = cutover_env

    first = _run(env, unit_dir)
    second = _run(env, unit_dir)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert (state_dir / NEW_UNIT).read_text().strip() == "active"
    assert (state_dir / OLD_UNIT).read_text().strip() == "inactive"
    assert not (unit_dir / OLD_UNIT).exists()
