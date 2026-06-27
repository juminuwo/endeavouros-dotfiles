from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path


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
    subprocess.run(["git", "init", "-q", str(path)], check=True)
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
            "security_review_required": True,
        },
    ]
    assert "Package drift is report-only" in message
    assert "AUR/foreign package drift is security-sensitive" in message
    assert "Bare Approved will be ignored" in message
    assert "Approved  # also works" not in message


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

    result = mod.apply_request(request, repo=repo, dry_run=True)

    assert result["ok"] is True
    assert result["paths"] == ["config/packages-aur.txt", "config/packages-repo.txt"]
    assert (repo / "config/packages-repo.txt").read_text() == "git\n"
    assert (repo / "config/packages-aur.txt").read_text() == ""


def test_scan_creates_discord_message_for_codex_config_and_report_only_packages(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    init_repo(repo)
    (repo / "config/codex-config.toml").write_text('model = "gpt-5.5"\n')
    (repo / "config/packages-repo.txt").write_text("git\n")
    (repo / "config/packages-aur.txt").write_text("")
    (repo / "config/host").mkdir(exist_ok=True)
    (repo / "config/host/packages-host-repo.txt").write_text("")

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
    assert "M config/codex-config.toml" in message
    assert "approve dotfiles " in message
    assert "Package drift is report-only" in message
    assert "extra-native" in message


def test_apply_request_refuses_head_mismatch(tmp_path):
    mod = load_module()
    repo = tmp_path / "repo"
    init_repo(repo)
    request = {
        "id": "20260101T000000Z-deadbeef",
        "repo": str(repo),
        "head": "not-the-current-head",
        "actions": [],
    }

    result = mod.apply_request(request, repo=repo, dry_run=True)

    assert result["ok"] is False
    assert "HEAD changed" in result["error"]


def test_find_discord_approval_accepts_exact_request_id(tmp_path):
    mod = load_module()
    state_dir = tmp_path / "state"
    pending = state_dir / "pending"
    pending.mkdir(parents=True)
    request = {"id": "20260101T000000Z-deadbeef", "created_at": "2026-01-01T00:00:00+00:00"}
    (pending / "20260101T000000Z-deadbeef.json").write_text(json.dumps(request))
    log = tmp_path / "gateway.log"
    log.write_text(
        "2026-01-01 00:05:00,000 INFO gateway.run: inbound message: "
        "platform=discord user=isitokaymimi chat=1506284995818553374 "
        "msg='approve dotfiles 20260101T000000Z-deadbeef' reply_to_id=None reply_to_text=''\n"
    )

    approval = mod.find_discord_approval(state_dir=state_dir, log_path=log)

    assert approval == {
        "request_id": "20260101T000000Z-deadbeef",
        "mode": "explicit",
        "message": "approve dotfiles 20260101T000000Z-deadbeef",
    }


def test_find_discord_approval_accepts_exact_request_id_for_aur_package_actions(tmp_path):
    mod = load_module()
    state_dir = tmp_path / "state"
    pending = state_dir / "pending"
    pending.mkdir(parents=True)
    request = {
        "id": "20260101T000000Z-deadbeef",
        "created_at": "2026-01-01T00:00:00+00:00",
        "actions": [
            {
                "type": "append_package_manifest",
                "manifest": "config/packages-aur.txt",
                "packages": ["new-aur"],
                "source": "extra_foreign",
                "security_review_required": True,
            }
        ],
    }
    (pending / "20260101T000000Z-deadbeef.json").write_text(json.dumps(request))
    log = tmp_path / "gateway.log"
    log.write_text(
        "2026-01-01 00:05:00,000 INFO gateway.run: inbound message: "
        "platform=discord user=isitokaymimi chat=1506284995818553374 "
        "msg='approve dotfiles 20260101T000000Z-deadbeef' reply_to_id=None reply_to_text=''\n"
    )

    approval = mod.find_discord_approval(state_dir=state_dir, log_path=log)

    assert approval == {
        "request_id": "20260101T000000Z-deadbeef",
        "mode": "explicit",
        "message": "approve dotfiles 20260101T000000Z-deadbeef",
    }


def test_find_discord_approval_accepts_bare_approved_for_single_pending_request(tmp_path):
    mod = load_module()
    state_dir = tmp_path / "state"
    pending = state_dir / "pending"
    pending.mkdir(parents=True)
    request = {"id": "20260101T000000Z-deadbeef", "created_at": "2026-01-01T00:00:00+00:00"}
    (pending / "20260101T000000Z-deadbeef.json").write_text(json.dumps(request))
    log = tmp_path / "gateway.log"
    log.write_text(
        "2026-01-01 00:05:00,000 INFO gateway.run: inbound message: "
        "platform=discord user=isitokaymimi chat=1506284995818553374 "
        "msg='Approved' reply_to_id=None reply_to_text=''\n"
    )

    approval = mod.find_discord_approval(state_dir=state_dir, log_path=log)

    assert approval == {
        "request_id": "20260101T000000Z-deadbeef",
        "mode": "single-pending-bare-approved",
        "message": "Approved",
    }


def test_find_discord_approval_ignores_bare_approved_for_aur_package_actions(tmp_path):
    mod = load_module()
    state_dir = tmp_path / "state"
    pending = state_dir / "pending"
    pending.mkdir(parents=True)
    request = {
        "id": "20260101T000000Z-deadbeef",
        "created_at": "2026-01-01T00:00:00+00:00",
        "actions": [
            {
                "type": "append_package_manifest",
                "manifest": "config/packages-aur.txt",
                "packages": ["new-aur"],
                "source": "extra_foreign",
                "security_review_required": True,
            }
        ],
    }
    (pending / "20260101T000000Z-deadbeef.json").write_text(json.dumps(request))
    log = tmp_path / "gateway.log"
    log.write_text(
        "2026-01-01 00:05:00,000 INFO gateway.run: inbound message: "
        "platform=discord user=isitokaymimi chat=1506284995818553374 "
        "msg='Approved' reply_to_id=None reply_to_text=''\n"
    )

    assert mod.find_discord_approval(state_dir=state_dir, log_path=log) is None


def test_find_discord_approval_ignores_bare_approved_when_multiple_requests_pending(tmp_path):
    mod = load_module()
    state_dir = tmp_path / "state"
    pending = state_dir / "pending"
    pending.mkdir(parents=True)
    for request_id in ("20260101T000000Z-deadbeef", "20260101T000100Z-feedface"):
        (pending / f"{request_id}.json").write_text(
            json.dumps({"id": request_id, "created_at": "2026-01-01T00:00:00+00:00"})
        )
    log = tmp_path / "gateway.log"
    log.write_text(
        "2026-01-01 00:05:00,000 INFO gateway.run: inbound message: "
        "platform=discord user=isitokaymimi chat=1506284995818553374 "
        "msg='Approved' reply_to_id=None reply_to_text=''\n"
    )

    assert mod.find_discord_approval(state_dir=state_dir, log_path=log) is None
