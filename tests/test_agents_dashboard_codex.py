import subprocess
from types import SimpleNamespace

from test_agents_dashboard_hermes import load_dashboard_module


def test_latest_wrapped_recap_excludes_prompt_and_activity():
    dashboard = load_dashboard_module()
    text = (
        "─ Conversation recap ─────\n\n  Old recap.\n\n"
        "› Continue\n\n• Working\n\n"
        "─ Conversation recap ─────\n\n"
        "  Changes are complete;\n  verification passed.\n\n"
        "› Ask Codex to do anything\n"
    )
    assert dashboard.codex_recap_from_text(text) == (
        "Changes are complete; verification passed."
    )


def test_raw_recap_and_missing_or_incomplete_recap():
    dashboard = load_dashboard_module()
    assert dashboard.codex_recap_from_text(
        "Conversation recap\nAll done.\n\n› Next task\n"
    ) == "All done."
    for text in (
        "• Generating conversation recap…\n",
        "› Explain Conversation recap\n",
        "─ Conversation recap ───\n\n› Ask Codex to do anything\n",
    ):
        assert dashboard.codex_recap_from_text(text) == ""


def test_window_lookup_targets_exact_window_and_handles_failure(monkeypatch):
    dashboard = load_dashboard_module()
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="Conversation recap\nDone.\n")

    monkeypatch.setattr(dashboard.subprocess, "run", run)
    assert dashboard.codex_window_recap(42) == "Done."
    assert calls[0][-5:] == ["get-text", "--match", "id:42", "--extent", "all"]

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("kitty", 2)

    monkeypatch.setattr(dashboard.subprocess, "run", timeout)
    assert dashboard.codex_window_recap(42) == ""


def test_idle_codex_card_uses_its_window_recap(monkeypatch, tmp_path):
    dashboard = load_dashboard_module()
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text("")
    monkeypatch.setattr(dashboard, "find_agent_tabs", lambda: iter([{
        "harness": "codex", "tab_id": 7, "window_id": 42,
        "cwd": str(tmp_path), "jsonl": rollout, "session_id": "thread",
    }]))
    monkeypatch.setattr(dashboard, "status_for", lambda _: ("idle", "○", "dim"))
    windows = []

    def recap(window_id):
        windows.append(window_id)
        return "Verification passed."

    monkeypatch.setattr(dashboard, "codex_window_recap", recap)
    session, = dashboard.gather_sessions()
    assert windows == [42]
    assert session["summary"]["last_recap"] == "Verification passed."
    assert dashboard.render_card(session).renderables[2].plain == "recap: Verification passed."
    monkeypatch.setattr(dashboard, "status_for", lambda _: ("active", "●", "dim"))
    dashboard.gather_sessions()
    assert windows == [42]
