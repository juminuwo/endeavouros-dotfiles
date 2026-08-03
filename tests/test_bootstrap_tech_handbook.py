from __future__ import annotations

import os
import subprocess
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "bin"
    / "bootstrap-tech-handbook"
)
EXPECTED_ORIGIN = "https://github.com/Imoto-Labs/tech-handbook.git"


def write_fake_installer(path: Path) -> None:
    installer = path / "install"
    installer.write_text(
        """#!/bin/sh
set -eu
if [ -n "${FAKE_INSTALL_MARKER:-}" ]; then
  : > "$FAKE_INSTALL_MARKER"
fi
"""
    )
    installer.chmod(0o755)


def init_checkout(path: Path, origin: str = EXPECTED_ORIGIN) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", origin],
        check=True,
    )
    write_fake_installer(path)
    subprocess.run(["git", "-C", str(path), "add", "install"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "Initial handbook",
        ],
        check=True,
    )


def make_fake_gh(path: Path) -> Path:
    path.mkdir(parents=True)
    gh = path / "gh"
    gh.write_text(
        """#!/bin/sh
set -eu
if [ "${1:-}" = auth ] && [ "${2:-}" = status ]; then
  exit "${FAKE_GH_AUTH_STATUS:-0}"
fi
if [ "${1:-}" = repo ] && [ "${2:-}" = clone ]; then
  git init -q "$4"
  git -C "$4" remote add origin https://github.com/Imoto-Labs/tech-handbook.git
  printf '#!/bin/sh\nset -eu\n: > "$FAKE_INSTALL_MARKER"\n' > "$4/install"
  chmod +x "$4/install"
  git -C "$4" add install
  git -C "$4" -c user.name='Test User' -c user.email=test@example.com \
    commit -qm 'Initial handbook'
  exit 0
fi
if [ "${1:-}" = api ]; then
  if [ "${FAKE_GH_API_STATUS:-0}" -ne 0 ]; then
    exit "$FAKE_GH_API_STATUS"
  fi
  if [ -n "${FAKE_REMOTE_HEAD:-}" ]; then
    printf '%s\n' "$FAKE_REMOTE_HEAD"
  else
    git -C "$TECH_HANDBOOK_DIR" rev-parse HEAD
  fi
  exit 0
fi
exit 64
"""
    )
    gh.chmod(0o755)
    return path


def run_bootstrap(
    tmp_path: Path,
    *,
    auth_status: int = 0,
    api_status: int = 0,
    remote_head: str | None = None,
    legacy_target: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    destination = tmp_path / "git" / "tech-handbook"
    legacy_link = tmp_path / "git" / "docs"
    old_docs = legacy_target or tmp_path / "dotfiles" / "config" / "agent-docs"
    fake_bin = make_fake_gh(tmp_path / "bin")

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path),
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "TECH_HANDBOOK_DIR": str(destination),
            "LEGACY_DOCS_LINK": str(legacy_link),
            "DOTFILES_AGENT_DOCS_DIR": str(old_docs),
            "FAKE_GH_AUTH_STATUS": str(auth_status),
            "FAKE_GH_API_STATUS": str(api_status),
            "FAKE_REMOTE_HEAD": remote_head or "",
            "FAKE_INSTALL_MARKER": str(tmp_path / "install-ran"),
        }
    )
    result = subprocess.run(
        [str(SCRIPT)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, destination, legacy_link


def test_clones_missing_checkout_and_removes_owned_legacy_link(tmp_path: Path) -> None:
    old_docs = tmp_path / "dotfiles" / "config" / "agent-docs"
    old_docs.mkdir(parents=True)
    legacy_link = tmp_path / "git" / "docs"
    legacy_link.parent.mkdir(parents=True)
    legacy_link.symlink_to(old_docs)

    result, destination, returned_link = run_bootstrap(
        tmp_path,
        legacy_target=old_docs,
    )

    assert result.returncode == 0, result.stderr
    assert destination.is_dir()
    assert (
        subprocess.check_output(
            ["git", "-C", str(destination), "remote", "get-url", "origin"],
            text=True,
        ).strip()
        == EXPECTED_ORIGIN
    )
    assert returned_link == legacy_link
    assert not legacy_link.exists()
    assert not legacy_link.is_symlink()
    assert (tmp_path / "install-ran").is_file()


def test_existing_checkout_is_not_pulled_and_unrelated_link_is_preserved(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "git" / "tech-handbook"
    init_checkout(destination)
    unrelated = tmp_path / "other-docs"
    unrelated.mkdir()
    legacy_link = tmp_path / "git" / "docs"
    legacy_link.symlink_to(unrelated)

    result, _, _ = run_bootstrap(tmp_path)

    assert result.returncode == 0, result.stderr
    assert legacy_link.is_symlink()
    assert legacy_link.resolve() == unrelated


def test_warns_when_existing_checkout_is_behind_remote(tmp_path: Path) -> None:
    destination = tmp_path / "git" / "tech-handbook"
    init_checkout(destination)
    local_head = subprocess.check_output(
        ["git", "-C", str(destination), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    subprocess.run(
        [
            "git",
            "-C",
            str(destination),
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--allow-empty",
            "-qm",
            "Remote handbook update",
        ],
        check=True,
    )
    remote_head = subprocess.check_output(
        ["git", "-C", str(destination), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    subprocess.run(
        ["git", "-C", str(destination), "reset", "--hard", local_head],
        check=True,
        capture_output=True,
    )

    result, _, _ = run_bootstrap(tmp_path, remote_head=remote_head)

    assert result.returncode == 0, result.stderr
    assert "is missing 1 commit(s) from the remote default branch" in result.stderr
    assert "install will use the local checkout" in result.stderr
    assert (
        subprocess.check_output(
            ["git", "-C", str(destination), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        == local_head
    )
    assert (tmp_path / "install-ran").is_file()


def test_warns_and_continues_when_remote_check_fails(tmp_path: Path) -> None:
    destination = tmp_path / "git" / "tech-handbook"
    init_checkout(destination)

    result, _, _ = run_bootstrap(tmp_path, api_status=1)

    assert result.returncode == 0, result.stderr
    assert "could not check whether" in result.stderr
    assert (tmp_path / "install-ran").is_file()


def test_rejects_occupied_non_repository_path(tmp_path: Path) -> None:
    destination = tmp_path / "git" / "tech-handbook"
    destination.mkdir(parents=True)

    result, _, _ = run_bootstrap(tmp_path)

    assert result.returncode != 0
    assert "is not a Git checkout" in result.stderr


def test_rejects_checkout_with_wrong_origin(tmp_path: Path) -> None:
    destination = tmp_path / "git" / "tech-handbook"
    init_checkout(destination, "https://github.com/example/unrelated.git")

    result, _, _ = run_bootstrap(tmp_path)

    assert result.returncode != 0
    assert "expected GitHub repository Imoto-Labs/tech-handbook" in result.stderr


def test_requires_authenticated_github_cli_for_clone(tmp_path: Path) -> None:
    result, destination, _ = run_bootstrap(tmp_path, auth_status=1)

    assert result.returncode != 0
    assert "gh auth login" in result.stderr
    assert not destination.exists()


def test_rejects_checkout_without_handbook_installer(tmp_path: Path) -> None:
    destination = tmp_path / "git" / "tech-handbook"
    init_checkout(destination)
    (destination / "install").unlink()

    result, _, _ = run_bootstrap(tmp_path)

    assert result.returncode != 0
    assert "install is missing or not executable" in result.stderr
