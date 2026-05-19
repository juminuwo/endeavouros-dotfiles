from __future__ import annotations

import importlib.util
import sqlite3
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path


def load_dashboard_module():
    script = Path(__file__).resolve().parents[1] / "config/bin/agents-dashboard"
    loader = SourceFileLoader("agents_dashboard", str(script))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def create_hermes_state_db(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                user_id TEXT,
                model TEXT,
                model_config TEXT,
                system_prompt TEXT,
                parent_session_id TEXT,
                started_at REAL NOT NULL,
                ended_at REAL,
                end_reason TEXT,
                message_count INTEGER DEFAULT 0,
                tool_call_count INTEGER DEFAULT 0,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0,
                cache_write_tokens INTEGER DEFAULT 0,
                reasoning_tokens INTEGER DEFAULT 0,
                billing_provider TEXT,
                billing_base_url TEXT,
                billing_mode TEXT,
                estimated_cost_usd REAL,
                actual_cost_usd REAL,
                cost_status TEXT,
                cost_source TEXT,
                pricing_version TEXT,
                title TEXT,
                api_call_count INTEGER DEFAULT 0,
                handoff_state TEXT,
                handoff_platform TEXT,
                handoff_error TEXT
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                role TEXT NOT NULL,
                content TEXT,
                tool_call_id TEXT,
                tool_calls TEXT,
                tool_name TEXT,
                timestamp REAL NOT NULL,
                token_count INTEGER,
                finish_reason TEXT,
                reasoning TEXT,
                reasoning_content TEXT,
                reasoning_details TEXT,
                codex_reasoning_items TEXT,
                codex_message_items TEXT
            );
            """
        )
        con.execute(
            """
            INSERT INTO sessions
                (id, source, model, started_at, ended_at, message_count, tool_call_count, title)
            VALUES
                ('20260520_003054_8114b7', 'cli', 'gpt-5.5', 1779233851.0, NULL, 3, 1, 'Live Hermes')
            """
        )
        con.execute(
            """
            INSERT INTO messages (session_id, role, content, timestamp)
            VALUES ('20260520_003054_8114b7', 'user', 'fix the dashboard', 1779233860.0)
            """
        )
        con.execute(
            """
            INSERT INTO messages (session_id, role, content, timestamp)
            VALUES ('20260520_003054_8114b7', 'assistant', 'reading the Hermes state', 1779233865.0)
            """
        )
        con.execute(
            """
            INSERT INTO messages (session_id, role, tool_name, timestamp)
            VALUES ('20260520_003054_8114b7', 'tool', 'terminal', 1779233866.0)
            """
        )
        con.commit()
    finally:
        con.close()


def test_gather_sessions_maps_live_hermes_tab_to_state_db(monkeypatch, tmp_path):
    dashboard = load_dashboard_module()
    hermes_home = tmp_path / "hermes"
    log_dir = hermes_home / "logs"
    log_dir.mkdir(parents=True)
    db = hermes_home / "state.db"
    create_hermes_state_db(db)
    (log_dir / "agent.log").write_text(
        "2026-05-20 00:37:32,000 INFO [20260520_003054_8114b7] "
        "agent.conversation_loop: conversation turn: session=20260520_003054_8114b7\n"
    )

    monkeypatch.setattr(dashboard, "HERMES_HOME", hermes_home)
    monkeypatch.setattr(dashboard, "HERMES_STATE_DB", db)
    monkeypatch.setattr(dashboard, "HERMES_LOG_PATH", log_dir / "agent.log")
    monkeypatch.setattr(dashboard, "proc_cwd", lambda pid: "/work/project")
    monkeypatch.setattr(dashboard, "proc_start_time", lambda pid: 1779233851.0)
    monkeypatch.setattr(
        dashboard,
        "kitty_ls",
        lambda: [
            {
                "tabs": [
                    {
                        "id": 42,
                        "windows": [
                            {
                                "cwd": "/work/project",
                                "foreground_processes": [
                                    {"pid": 12345, "cmdline": ["hermes"]}
                                ],
                            }
                        ],
                    }
                ]
            }
        ],
    )

    sessions = dashboard.gather_sessions()

    assert len(sessions) == 1
    session = sessions[0]
    assert session["harness"] == "hermes"
    assert session["tab_id"] == 42
    assert session["session_id"] == "20260520_003054_8114b7"
    assert session["fresh"] is False
    assert session["summary"]["last_user"] == "fix the dashboard"
    assert session["summary"]["last_assistant"] == "reading the Hermes state"
    assert session["summary"]["last_tool"] == "terminal"
