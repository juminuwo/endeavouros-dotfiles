from __future__ import annotations

import hashlib
import importlib.util
import json
import multiprocessing
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "config/bin/dotfiles-autoupdate"


def load_module():
    loader = SourceFileLoader("dotfiles_autoupdate", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test User"], check=True)
    (path / "config").mkdir(parents=True)
    (path / "config/codex-config.toml").write_text('model = "gpt-5"\n')
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "initial"], check=True)


def commit_all(path: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", message], check=True)


def test_load_link_entries_handles_scalar_and_mapping_values(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "install.conf.yaml").write_text(
        """
- defaults:
    link:
      relink: true
      create: true
- link:
    ~/.zshrc: config/zshrc
    ~/git/CLAUDE.md:
      path: config/AGENTS.md
      relink: true
- shell:
  - [true, noop]
""".lstrip()
    )

    links = mod.load_link_entries(repo)

    assert links == {
        "~/.zshrc": "config/zshrc",
        "~/git/CLAUDE.md": "config/AGENTS.md",
    }


def test_scan_units_reports_hash_based_drift(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    repo_unit_dir = repo / "config/host/systemd/user"
    live_user_dir = tmp_path / "home/.config/systemd/user"
    repo_unit_dir.mkdir(parents=True)
    live_user_dir.mkdir(parents=True)
    repo_unit = repo_unit_dir / "example.service"
    live_unit = live_user_dir / "example.service"
    repo_unit.write_text("[Unit]\nDescription=repo\n")
    live_unit.write_text("[Unit]\nDescription=live\n")

    drift = mod.scan_units(repo, tmp_path / "home", tmp_path / "system")

    assert drift == [
        {
            "scope": "user",
            "name": "example.service",
            "repo_path": "config/host/systemd/user/example.service",
            "live_path": str(live_unit),
            "status": "drift",
            "repo_sha256": hashlib.sha256(repo_unit.read_bytes()).hexdigest(),
            "live_sha256": hashlib.sha256(live_unit.read_bytes()).hexdigest(),
        }
    ]


def test_compare_packages_marks_drift_report_only(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    (repo / "config/host").mkdir(parents=True)
    (repo / "config/packages-repo.txt").write_text("git\nmissing-native\n")
    (repo / "config/packages-aur.txt").write_text("yay-only\n")
    (repo / "config/host/packages-host-repo.txt").write_text("intel-ucode\n")

    result = mod.compare_packages(
        repo,
        native_explicit={"git", "intel-ucode", "extra-native"},
        foreign_explicit={"yay-only", "extra-aur"},
        native_installed={"git", "intel-ucode", "missing-native", "extra-native"},
        foreign_installed={"yay-only", "extra-aur"},
    )

    assert result["report_only"] is True
    assert result["extra_native"] == ["extra-native"]
    assert result["extra_foreign"] == ["extra-aur"]
    assert result["missing_native"] == []
    assert result["missing_foreign"] == []


def test_compare_packages_missing_uses_installed_not_explicit(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    (repo / "config/host").mkdir(parents=True)
    (repo / "config/packages-repo.txt").write_text("installed-dependency\nactually-missing\n")
    (repo / "config/packages-aur.txt").write_text("installed-foreign-dependency\nmissing-foreign\n")
    (repo / "config/host/packages-host-repo.txt").write_text("")

    result = mod.compare_packages(
        repo,
        native_explicit=set(),
        foreign_explicit=set(),
        native_installed={"installed-dependency"},
        foreign_installed={"installed-foreign-dependency"},
    )

    assert result["missing_native"] == ["actually-missing"]
    assert result["missing_foreign"] == ["missing-foreign"]


def test_compare_packages_ignores_extra_native_baseline(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    (repo / "config/host").mkdir(parents=True)
    (repo / "config/packages-repo.txt").write_text("git\n")
    (repo / "config/packages-aur.txt").write_text("")
    (repo / "config/host/packages-host-repo.txt").write_text("")
    (repo / "config/host/packages-extra-native-baseline.txt").write_text("base\n# comments are ignored\nlinux\n")

    result = mod.compare_packages(
        repo,
        native_explicit={"git", "base", "linux", "unexpected"},
        foreign_explicit=set(),
        native_installed={"git", "base", "linux", "unexpected"},
        foreign_installed=set(),
    )

    assert result["extra_native"] == ["unexpected"]
    assert result["ignored_extra_native"] == ["base", "linux"]


def test_scan_creates_request_for_package_only_drift(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "config/host").mkdir(exist_ok=True)
    (repo / "config/packages-repo.txt").write_text("git\n")
    (repo / "config/packages-aur.txt").write_text("")
    (repo / "config/host/packages-host-repo.txt").write_text("")
    commit_all(repo, "package manifests")

    scan = mod.build_scan(
        repo=repo,
        home=tmp_path / "home",
        system_dir=tmp_path / "system",
        native_explicit={"git", "extra-native"},
        native_installed={"git", "extra-native"},
        foreign_explicit={"extra-aur"},
        foreign_installed={"extra-aur"},
    )
    message = mod.format_discord_message(scan)

    assert scan["git_status"] == []
    assert scan["actionable"] is True
    assert scan["actions"] == [
        {
            "type": "append_package_manifest",
            "manifest": "config/packages-repo.txt",
            "packages": ["extra-native"],
            "source": "extra_native",
        },
        {
            "type": "append_package_manifest",
            "manifest": "config/packages-aur.txt",
            "packages": ["extra-aur"],
            "source": "extra_foreign",
        },
    ]
    assert message.startswith("The dotfiles repo is behind this machine.")
    assert "- Native packages to record: extra-native" in message
    assert "- AUR packages to record: extra-aur (review PKGBUILDs before approving)" in message
    assert "Approve updating the repo and pushing to `main`?" in message
    assert "Reply `approve dotfiles`." in message



def test_missing_package_drift_notifies_without_manifest_action(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "config/host").mkdir(exist_ok=True)
    (repo / "config/packages-repo.txt").write_text("missing-native\n")
    (repo / "config/packages-aur.txt").write_text("missing-aur\n")
    (repo / "config/host/packages-host-repo.txt").write_text("")
    commit_all(repo, "package manifests")

    scan = mod.build_scan(
        repo=repo,
        home=tmp_path / "home",
        system_dir=tmp_path / "system",
        native_explicit=set(),
        native_installed=set(),
        foreign_explicit=set(),
        foreign_installed=set(),
    )

    assert scan["actionable"] is True
    assert scan["actions"] == []
    assert scan["package_drift"]["missing_native"] == ["missing-native"]
    assert scan["package_drift"]["missing_foreign"] == ["missing-aur"]
    message = mod.format_discord_message(scan)
    assert message.startswith("This machine and the dotfiles repo differ.")
    assert "- repo native packages not installed: missing-native" in message
    assert "- repo AUR packages not installed: missing-aur" in message
    assert "No automatic repo update is available." in message
    assert "approve dotfiles" not in message


def test_append_packages_to_manifest_appends_sorted_missing_only(tmp_path):
    mod = load_module()
    manifest = tmp_path / "packages.txt"
    manifest.write_text("# Packages\nbeta\n")

    changed = mod.append_packages_to_manifest(manifest, ["delta", "alpha", "beta", "alpha"])

    assert changed is True
    assert manifest.read_text() == "# Packages\nbeta\nalpha\ndelta\n"
    assert mod.append_packages_to_manifest(manifest, ["alpha", "delta"]) is False
    assert manifest.read_text() == "# Packages\nbeta\nalpha\ndelta\n"


def test_apply_request_package_actions_dry_run_reports_manifest_paths(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "config/packages-repo.txt").write_text("git\n")
    (repo / "config/packages-aur.txt").write_text("")
    commit_all(repo, "package manifests")
    request = {
        "id": "20260101T000000Z-deadbeef",
        "repo": str(repo),
        "head": mod.current_head(repo),
        "branch": mod.current_branch(repo),
        "remote": mod.remote_url(repo),
        "git_status": [],
        "repo_state_sha256": mod.repo_state_sha256(repo, []),
        "package_drift": {
            "state_sha256": mod.package_state_sha256(
                {"git", "new-native"},
                {"new-aur"},
                {"git", "new-native"},
                {"new-aur"},
            ),
        },
        "actions": [
            {
                "type": "append_package_manifest",
                "manifest": "config/packages-repo.txt",
                "packages": ["new-native"],
                "source": "extra_native",
            },
            {
                "type": "append_package_manifest",
                "manifest": "config/packages-aur.txt",
                "packages": ["new-aur"],
                "source": "extra_foreign",
                "security_review_required": True,
            },
        ],
    }

    result = mod.apply_request(
        request,
        repo=repo,
        dry_run=True,
        package_state_override=request["package_drift"]["state_sha256"],
    )

    assert result["ok"] is True
    assert result["paths"] == ["config/packages-aur.txt", "config/packages-repo.txt"]
    assert (repo / "config/packages-repo.txt").read_text() == "git\n"
    assert (repo / "config/packages-aur.txt").read_text() == ""


def test_scan_creates_discord_message_for_codex_config_and_report_only_packages(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "config/packages-repo.txt").write_text("git\n")
    (repo / "config/packages-aur.txt").write_text("")
    (repo / "config/host").mkdir(exist_ok=True)
    (repo / "config/host/packages-host-repo.txt").write_text("")
    commit_all(repo, "package manifests")
    (repo / "config/codex-config.toml").write_text('model = "gpt-5.5"\n')

    scan = mod.build_scan(
        repo=repo,
        home=tmp_path / "home",
        system_dir=tmp_path / "system",
        native_explicit={"git", "extra-native"},
        native_installed={"git", "extra-native"},
        foreign_explicit=set(),
        foreign_installed=set(),
    )
    message = mod.format_discord_message(scan)

    assert scan["actionable"] is True
    assert "- Changed repo files:" in message
    assert "  - ` M` config/codex-config.toml" in message
    assert "- Native packages to record: extra-native" in message
    assert "Reply `approve dotfiles`." in message

    details = mod.format_snapshot_details(scan)
    assert "M config/codex-config.toml" in details
    assert "installed native packages missing from repo manifests: 1" in details
    assert "extra-native" in details


def test_discord_message_lists_every_changed_repo_file_without_truncation():
    mod = load_module()
    status = [
        " M README.md",
        "?? config/new-file.toml",
        "R  config/old-name -> config/new-name",
    ] + [f" M config/generated-{index:02d}.toml" for index in range(13)]
    scan = {
        "id": "20260101T000000Z-deadbeef",
        "git_status": status,
        "unit_drift": [],
        "link_issues": [],
        "package_drift": {
            "extra_native": [],
            "extra_foreign": [],
            "missing_native": [],
            "missing_foreign": [],
        },
        "actions": [{"type": "commit_repo_changes", "status": status}],
    }

    message = mod.format_discord_message(scan)

    assert "- Changed repo files:" in message
    assert "  - ` M` README.md" in message
    assert "  - `??` config/new-file.toml" in message
    assert "  - `R ` config/old-name -> config/new-name" in message
    assert "  - ` M` config/generated-12.toml" in message
    assert "Changed repo files: 16" not in message
    assert "… more" not in message
    assert "Ignore this message to do nothing." in message
    assert "The next scan replaces this snapshot; there is no approval queue." in message


def test_scan_identifies_machine_state_files_as_silent_only_repo_status():
    mod = load_module()

    silent_scan = {
        "unit_drift": [],
        "link_issues": [],
        "package_drift": {
            "extra_native": [],
            "extra_foreign": [],
            "missing_native": [],
            "missing_foreign": [],
        },
    }

    for status in (
        [" M config/fcitx5/profile"],
        [" M config/codex-config.toml"],
        [" M config/fcitx5/profile", " M config/codex-config.toml"],
    ):
        assert mod.scan_is_silent_only_repo_status({**silent_scan, "git_status": status}) is True

    assert mod.scan_is_silent_only_repo_status({
        **silent_scan,
        "git_status": [" M config/fcitx5/profile"],
        "package_drift": {
            "extra_native": ["new-package"],
            "extra_foreign": [],
            "missing_native": [],
            "missing_foreign": [],
        },
    }) is False


def test_command_scan_does_not_save_or_notify_for_machine_state_only(tmp_path, monkeypatch, capsys):
    mod = load_module()
    scan = {
        "actionable": True,
        "git_status": [" M config/fcitx5/profile", " M config/codex-config.toml"],
        "unit_drift": [],
        "link_issues": [],
        "package_drift": {
            "extra_native": [],
            "extra_foreign": [],
            "missing_native": [],
            "missing_foreign": [],
        },
    }
    monkeypatch.setattr(mod, "build_scan", lambda **kwargs: scan)

    def fail_save_pending(*args, **kwargs):
        raise AssertionError("silent-only scan should not create a pending snapshot")

    monkeypatch.setattr(mod, "save_pending", fail_save_pending)
    args = SimpleNamespace(repo="repo", home="home", system_dir="system", state_dir=str(tmp_path / "state"))

    assert mod.command_scan(args) == 0
    assert capsys.readouterr().out == ""


def test_apply_request_refuses_head_mismatch(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    init_repo(repo)
    request = {
        "id": "20260101T000000Z-deadbeef",
        "repo": str(repo),
        "branch": mod.current_branch(repo),
        "head": "not-the-current-head",
        "actions": [],
    }

    result = mod.apply_request(request, repo=repo, dry_run=True)

    assert result["ok"] is False
    assert "HEAD changed" in result["error"]


def test_find_discord_approval_accepts_approval_for_current_snapshot(tmp_path):
    mod = load_module()
    state_dir = tmp_path / "state"
    request = {
        "id": "20260101T000000Z-deadbeef",
        "created_at": "2026-01-01T00:00:00+00:00",
        "actions": [{"type": "commit_repo_changes"}],
    }
    mod.save_pending(request, state_dir)
    log = tmp_path / "gateway.log"
    log.write_text(
        "2026-01-01 00:05:00,000 INFO gateway.run: inbound message: "
        "platform=discord user=isitokaymimi chat=1506284995818553374 "
        "msg='approve dotfiles' reply_to_id=None reply_to_text=''\n"
    )

    approval = mod.find_discord_approval(state_dir=state_dir, log_path=log)

    assert approval == {
        "request_id": "20260101T000000Z-deadbeef",
        "mode": "current-snapshot",
        "message": "approve dotfiles",
    }


def test_find_discord_approval_ignores_unscoped_approval(tmp_path):
    mod = load_module()
    state_dir = tmp_path / "state"
    request = {
        "id": "20260101T000000Z-deadbeef",
        "created_at": "2026-01-01T00:00:00+00:00",
        "actions": [{"type": "commit_repo_changes"}],
    }
    mod.save_pending(request, state_dir)
    log = tmp_path / "gateway.log"
    log.write_text(
        "2026-01-01 00:05:00,000 INFO gateway.run: inbound message: "
        "platform=discord user=isitokaymimi chat=1506284995818553374 "
        "msg='Approved' reply_to_id=None reply_to_text=''\n"
    )

    assert mod.find_discord_approval(state_dir=state_dir, log_path=log) is None


def test_find_discord_approval_requires_exact_message_and_configured_chat(tmp_path):
    mod = load_module()
    state_dir = tmp_path / "state"
    request = {
        "id": "20260101T000000Z-deadbeef",
        "created_at": "2026-01-01T00:00:00+00:00",
        "actions": [{"type": "commit_repo_changes"}],
    }
    mod.save_pending(request, state_dir)
    log = tmp_path / "gateway.log"

    for index, (chat, message) in enumerate([
        ("1506284995818553374", "Approve Dotfiles"),
        ("1506284995818553374", "approve    dotfiles"),
        ("1506284995818553374", " approve dotfiles "),
        ("OTHER", "approve dotfiles"),
    ], start=1):
        log.write_text(
            f"2026-01-01 00:05:0{index},000 INFO gateway.run: inbound message: "
            f"platform=discord user=isitokaymimi chat={chat} "
            f"msg={message!r} reply_to_id=None reply_to_text=''\n"
        )
        assert mod.find_discord_approval(state_dir=state_dir, log_path=log) is None


def test_find_discord_approval_ignores_messages_before_current_snapshot(tmp_path):
    mod = load_module()
    state_dir = tmp_path / "state"
    request = {
        "id": "20260101T000000Z-deadbeef",
        "created_at": "2026-01-01T00:10:00+00:00",
        "actions": [{"type": "commit_repo_changes"}],
    }
    mod.save_pending(request, state_dir)
    log = tmp_path / "gateway.log"
    log.write_text(
        "2026-01-01 00:05:00,000 INFO gateway.run: inbound message: "
        "platform=discord user=isitokaymimi chat=1506284995818553374 "
        "msg='approve dotfiles' reply_to_id=None reply_to_text=''\n"
    )

    assert mod.find_discord_approval(state_dir=state_dir, log_path=log) is None


def test_find_discord_approval_preserves_millisecond_ordering(tmp_path):
    mod = load_module()
    state_dir = tmp_path / "state"
    request = {
        "id": "20260101T000000Z-deadbeef",
        "created_at": "2026-01-01T00:00:00.500000+00:00",
        "actions": [{"type": "commit_repo_changes"}],
    }
    mod.save_pending(request, state_dir)
    log = tmp_path / "gateway.log"
    log.write_text(
        "2026-01-01 00:00:00,600 INFO gateway.run: inbound message: "
        "platform=discord user=isitokaymimi chat=1506284995818553374 "
        "msg='approve dotfiles' reply_to_id=None reply_to_text=''\n"
    )

    assert mod.find_discord_approval(state_dir=state_dir, log_path=log) is not None

    request["created_at"] = "2026-01-01T00:00:00.700000+00:00"
    mod.save_pending(request, state_dir)
    assert mod.find_discord_approval(state_dir=state_dir, log_path=log) is None


def test_find_discord_approval_ignores_notify_only_snapshot(tmp_path):
    mod = load_module()
    state_dir = tmp_path / "state"
    request = {
        "id": "20260101T000000Z-deadbeef",
        "created_at": "2026-01-01T00:00:00+00:00",
        "actions": [],
    }
    mod.save_pending(request, state_dir)
    log = tmp_path / "gateway.log"
    log.write_text(
        "2026-01-01 00:05:00,000 INFO gateway.run: inbound message: "
        "platform=discord user=isitokaymimi chat=1506284995818553374 "
        "msg='approve dotfiles' reply_to_id=None reply_to_text=''\n"
    )

    assert mod.find_discord_approval(state_dir=state_dir, log_path=log) is None
    assert mod.load_pending(state_dir) == request


def test_save_pending_replaces_the_previous_snapshot(tmp_path):
    mod = load_module()
    state_dir = tmp_path / "state"

    mod.save_pending({"id": "first"}, state_dir)
    mod.save_pending({"id": "second"}, state_dir)

    assert mod.load_pending(state_dir) == {"id": "second"}
    assert list(state_dir.glob("*.json")) == [state_dir / "pending.json"]


def test_package_only_scan_refuses_unapproved_repo_change(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "config/host").mkdir(exist_ok=True)
    (repo / "config/packages-repo.txt").write_text("git\n")
    (repo / "config/packages-aur.txt").write_text("")
    (repo / "config/host/packages-host-repo.txt").write_text("")
    commit_all(repo, "package manifests")
    scan = mod.build_scan(
        repo=repo,
        home=tmp_path / "home",
        system_dir=tmp_path / "system",
        native_explicit={"git", "extra-native"},
        native_installed={"git", "extra-native"},
        foreign_explicit=set(),
        foreign_installed=set(),
    )

    (repo / "unapproved.txt").write_text("not in the snapshot\n")
    result = mod.apply_request(scan, repo=repo, dry_run=True)

    assert result["ok"] is False
    assert "Repo status changed" in result["error"]


def test_unit_only_scan_refuses_unapproved_repo_change(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    init_repo(repo)
    repo_unit_dir = repo / "config/host/systemd/user"
    live_unit_dir = tmp_path / "home/.config/systemd/user"
    repo_unit_dir.mkdir(parents=True)
    live_unit_dir.mkdir(parents=True)
    (repo_unit_dir / "example.service").write_text("[Unit]\nDescription=repo\n")
    commit_all(repo, "systemd unit")
    (live_unit_dir / "example.service").write_text("[Unit]\nDescription=live\n")
    scan = mod.build_scan(
        repo=repo,
        home=tmp_path / "home",
        system_dir=tmp_path / "system",
        native_explicit=set(),
        native_installed=set(),
        foreign_explicit=set(),
        foreign_installed=set(),
    )

    (repo / "unapproved.txt").write_text("not in the snapshot\n")
    result = mod.apply_request(scan, repo=repo, dry_run=True)

    assert result["ok"] is False
    assert "Repo status changed" in result["error"]


def test_apply_refuses_changed_contents_with_same_git_status(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    init_repo(repo)
    config = repo / "config/codex-config.toml"
    config.write_text('model = "gpt-5.5"\n')
    scan = mod.build_scan(
        repo=repo,
        home=tmp_path / "home",
        system_dir=tmp_path / "system",
        native_explicit=set(),
        native_installed=set(),
        foreign_explicit=set(),
        foreign_installed=set(),
    )

    config.write_text('model = "gpt-5.6"\n')
    assert mod.git_status_lines(repo) == scan["git_status"]
    result = mod.apply_request(scan, repo=repo, dry_run=True)

    assert result["ok"] is False
    assert "Repo contents changed" in result["error"]


def test_apply_refuses_changed_installed_package_state(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "config/host").mkdir(exist_ok=True)
    (repo / "config/packages-repo.txt").write_text("git\n")
    (repo / "config/packages-aur.txt").write_text("")
    (repo / "config/host/packages-host-repo.txt").write_text("")
    commit_all(repo, "package manifests")
    scan = mod.build_scan(
        repo=repo,
        home=tmp_path / "home",
        system_dir=tmp_path / "system",
        native_explicit={"git", "extra-native"},
        native_installed={"git", "extra-native"},
        foreign_explicit=set(),
        foreign_installed=set(),
    )
    changed_state = mod.package_state_sha256(
        {"git"},
        {"extra-native"},
        {"git", "extra-native"},
        {"extra-native"},
    )

    result = mod.apply_request(
        scan,
        repo=repo,
        dry_run=True,
        package_state_override=changed_state,
    )

    assert result["ok"] is False
    assert "Installed package state changed" in result["error"]


def test_apply_refuses_changed_origin(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    first_remote = tmp_path / "first.git"
    second_remote = tmp_path / "second.git"
    init_repo(repo)
    subprocess.run(["git", "init", "-q", "--bare", str(first_remote)], check=True)
    subprocess.run(["git", "init", "-q", "--bare", str(second_remote)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(first_remote)], check=True)
    config = repo / "config/codex-config.toml"
    config.write_text('model = "gpt-5.5"\n')
    scan = mod.build_scan(
        repo=repo,
        home=tmp_path / "home",
        system_dir=tmp_path / "system",
        native_explicit=set(),
        native_installed=set(),
        foreign_explicit=set(),
        foreign_installed=set(),
    )

    subprocess.run(
        ["git", "-C", str(repo), "remote", "set-url", "origin", str(second_remote)],
        check=True,
    )
    result = mod.apply_request(scan, repo=repo, dry_run=True)

    assert result["ok"] is False
    assert "Git origin changed" in result["error"]


def test_apply_refuses_snapshot_branch_mismatch_at_same_head(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    init_repo(repo)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "feature"], check=True)
    (repo / "config/codex-config.toml").write_text('model = "gpt-5.5"\n')
    scan = mod.build_scan(
        repo=repo,
        home=tmp_path / "home",
        system_dir=tmp_path / "system",
        native_explicit=set(),
        native_installed=set(),
        foreign_explicit=set(),
        foreign_installed=set(),
    )
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], check=True)
    assert mod.current_head(repo) == scan["head"]

    result = mod.apply_request(scan, repo=repo, dry_run=True)

    assert result["ok"] is False
    assert "Branch changed" in result["error"]


def test_apply_refuses_changed_or_disappeared_live_unit(tmp_path):
    mod = load_module()
    for case, expected in [
        ("changed", "Live unit changed"),
        ("disappeared", "Live unit disappeared"),
    ]:
        base = tmp_path / case
        repo = base / "repo"
        home = base / "home"
        init_repo(repo)
        repo_unit_dir = repo / "config/host/systemd/user"
        live_unit_dir = home / ".config/systemd/user"
        repo_unit_dir.mkdir(parents=True)
        live_unit_dir.mkdir(parents=True)
        repo_unit = repo_unit_dir / "example.service"
        live_unit = live_unit_dir / "example.service"
        repo_unit.write_text("[Unit]\nDescription=repo\n")
        commit_all(repo, "systemd unit")
        live_unit.write_text("[Unit]\nDescription=live at scan\n")
        scan = mod.build_scan(
            repo=repo,
            home=home,
            system_dir=base / "system",
            native_explicit=set(),
            native_installed=set(),
            foreign_explicit=set(),
            foreign_installed=set(),
        )
        if case == "changed":
            live_unit.write_text("[Unit]\nDescription=changed after scan\n")
        else:
            live_unit.unlink()

        result = mod.apply_request(scan, repo=repo, dry_run=True)

        assert result["ok"] is False
        assert expected in result["error"]


def test_notify_only_link_and_missing_unit_do_not_request_approval(tmp_path, monkeypatch, capsys):
    mod = load_module()
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "install.conf.yaml").write_text("- link:\n    ~/.zshrc: config/zshrc\n")
    (repo / "config/zshrc").write_text("# zsh\n")
    unit_dir = repo / "config/host/systemd/user"
    unit_dir.mkdir(parents=True)
    (unit_dir / "example.service").write_text("[Unit]\nDescription=example\n")
    commit_all(repo, "tracked host state")
    monkeypatch.setattr(mod, "compare_packages", lambda repo, **kwargs: {
        "report_only": True,
        "extra_native": [],
        "extra_foreign": [],
        "missing_native": [],
        "missing_foreign": [],
        "ignored_extra_native": [],
    })
    args = SimpleNamespace(
        repo=str(repo),
        home=str(tmp_path / "home"),
        system_dir=str(tmp_path / "system"),
        state_dir=str(tmp_path / "state"),
    )

    assert mod.command_scan(args) == 0
    message = capsys.readouterr().out

    assert message.startswith("This machine and the dotfiles repo differ.")
    assert "No automatic repo update is available." in message
    assert "approve dotfiles" not in message
    assert mod.load_pending(tmp_path / "state")["actions"] == []


def test_command_approvals_refuses_replaced_snapshot(tmp_path, monkeypatch, capsys):
    mod = load_module()
    state_dir = tmp_path / "state"
    request_a = {"id": "snapshot-a"}
    request_b = {"id": "snapshot-b"}
    mod.save_pending(request_a, state_dir)

    def replace_during_approval(**kwargs):
        mod.save_pending(request_b, state_dir)
        return {"request_id": "snapshot-a", "mode": "current-snapshot", "message": "approve dotfiles"}

    monkeypatch.setattr(mod, "find_discord_approval", replace_during_approval)
    monkeypatch.setattr(
        mod,
        "apply_request",
        lambda request: (_ for _ in ()).throw(AssertionError("replacement snapshot must not apply")),
    )
    args = SimpleNamespace(state_dir=str(state_dir), log_path=str(tmp_path / "gateway.log"))

    assert mod.command_approvals(args) == 0
    assert "pending snapshot changed" in capsys.readouterr().out
    assert mod.load_pending(state_dir) == request_b


def test_apply_request_commits_pushes_and_leaves_repo_clean(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    remote = tmp_path / "origin.git"
    init_repo(repo)
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(repo), "push", "-q", "-u", "origin", "main"], check=True)
    config = repo / "config/codex-config.toml"
    config.write_text('model = "gpt-5.5"\n')
    scan = mod.build_scan(
        repo=repo,
        home=tmp_path / "home",
        system_dir=tmp_path / "system",
        native_explicit=set(),
        native_installed=set(),
        foreign_explicit=set(),
        foreign_installed=set(),
    )

    result = mod.apply_request(scan, repo=repo)

    assert result["ok"] is True
    local_head = mod.current_head(repo)
    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "main"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    assert local_head == remote_head
    assert mod.git_status_lines(repo) == []


def test_approval_monitor_applies_once_and_repeat_is_noop(tmp_path, capsys):
    mod = load_module()
    repo = tmp_path / "repo"
    remote = tmp_path / "origin.git"
    state_dir = tmp_path / "state"
    init_repo(repo)
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(repo), "push", "-q", "-u", "origin", "main"], check=True)
    (repo / "config/codex-config.toml").write_text('model = "gpt-5.5"\n')
    scan = mod.build_scan(
        repo=repo,
        home=tmp_path / "home",
        system_dir=tmp_path / "system",
        native_explicit=set(),
        native_installed=set(),
        foreign_explicit=set(),
        foreign_installed=set(),
    )
    mod.save_pending(scan, state_dir)
    log = tmp_path / "gateway.log"
    log.write_text(
        "2099-01-01 00:05:00,000 INFO gateway.run: inbound message: "
        "platform=discord user=isitokaymimi chat=1506284995818553374 "
        "msg='approve dotfiles' reply_to_id=None reply_to_text=''\n"
    )
    args = SimpleNamespace(state_dir=str(state_dir), log_path=str(log))

    assert mod.command_approvals(args) == 0
    first_output = capsys.readouterr().out
    assert "Dotfiles approval applied and pushed." in first_output
    assert not mod.pending_path(state_dir).exists()
    first_head = mod.current_head(repo)

    assert mod.command_approvals(args) == 0
    assert capsys.readouterr().out == ""
    assert mod.current_head(repo) == first_head


def test_failed_push_preserves_commit_and_retries_without_second_commit(tmp_path, capsys):
    mod = load_module()
    repo = tmp_path / "repo"
    remote = tmp_path / "origin.git"
    state_dir = tmp_path / "state"
    init_repo(repo)
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(repo), "push", "-q", "-u", "origin", "main"], check=True)
    initial_remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "main"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    rejecting_hook = remote / "hooks/pre-receive"
    rejecting_hook.write_text("#!/bin/sh\nexit 1\n")
    rejecting_hook.chmod(0o755)
    (repo / "config/codex-config.toml").write_text('model = "gpt-5.5"\n')
    scan = mod.build_scan(
        repo=repo,
        home=tmp_path / "home",
        system_dir=tmp_path / "system",
        native_explicit=set(),
        native_installed=set(),
        foreign_explicit=set(),
        foreign_installed=set(),
    )
    mod.save_pending(scan, state_dir)
    log = tmp_path / "gateway.log"
    log.write_text(
        "2099-01-01 00:05:00,000 INFO gateway.run: inbound message: "
        "platform=discord user=isitokaymimi chat=1506284995818553374 "
        "msg='approve dotfiles' reply_to_id=None reply_to_text=''\n"
    )
    approval_args = SimpleNamespace(state_dir=str(state_dir), log_path=str(log))

    assert mod.command_approvals(approval_args) == 0
    assert "git push origin main failed" in capsys.readouterr().out
    pending = mod.load_pending(state_dir)
    local_commit = mod.current_head(repo)
    assert pending["push_pending_commit"] == local_commit
    assert mod.git_status_lines(repo) == []
    assert local_commit != initial_remote_head

    scan_args = SimpleNamespace(
        repo=str(repo),
        home=str(tmp_path / "home"),
        system_dir=str(tmp_path / "system"),
        state_dir=str(state_dir),
    )
    assert mod.command_scan(scan_args) == 0
    assert capsys.readouterr().out == ""
    assert mod.load_pending(state_dir)["push_pending_commit"] == local_commit

    unexpected = repo / "unexpected.txt"
    unexpected.write_text("appeared during push recovery\n")
    assert mod.command_approvals(approval_args) == 0
    assert "Repo changed while a push retry was pending" in capsys.readouterr().out
    assert mod.load_pending(state_dir)["push_pending_commit"] == local_commit
    unexpected.unlink()

    rejecting_hook.unlink()
    assert mod.command_approvals(approval_args) == 0
    assert "Dotfiles approval applied and pushed." in capsys.readouterr().out
    assert not mod.pending_path(state_dir).exists()
    assert mod.current_head(repo) == local_commit
    commit_count = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", "main"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    assert commit_count == "2"
    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "main"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    assert remote_head == local_commit


def test_state_lock_serializes_processes(tmp_path):
    mod = load_module()
    state_dir = tmp_path / "state"
    context = multiprocessing.get_context("fork")
    started = context.Event()
    acquired = context.Event()

    def contend_for_lock():
        started.set()
        with mod.state_lock(state_dir):
            acquired.set()

    with mod.state_lock(state_dir):
        process = context.Process(target=contend_for_lock)
        process.start()
        assert started.wait(2)
        assert not acquired.wait(0.2)

    assert acquired.wait(2)
    process.join(2)
    assert process.exitcode == 0
