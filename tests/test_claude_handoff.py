from __future__ import annotations

import json
import tomllib
from pathlib import Path

from nova_parser.claude_handoff import (
    discover_project_sessions,
    generate_handoff,
    main,
    project_log_dir_name,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")


def _sample_records() -> list[dict]:
    return [
        {
            "type": "ai-title",
            "aiTitle": "add-regional-ocr-web-tool",
            "sessionId": "session-1",
        },
        {
            "type": "agent-name",
            "agentName": "add-regional-ocr-web-tool",
            "sessionId": "session-1",
        },
        {
            "type": "permission-mode",
            "permissionMode": "bypassPermissions",
            "sessionId": "session-1",
        },
        {
            "type": "last-prompt",
            "lastPrompt": "/python-tdd-team ワークフローを続行し、次のフェイズを開始して",
            "sessionId": "session-1",
        },
        {
            "timestamp": "2026-05-11T06:59:41.438Z",
            "attachment": {
                "type": "task_reminder",
                "content": [
                    {
                        "id": "35",
                        "subject": "Phase C / reviewer: コードレビュー",
                        "description": "python-reviewer エージェントで Phase C 変更を read-only レビュー。",
                        "status": "completed",
                    },
                    {
                        "id": "36",
                        "subject": "Phase C / Gate 3 完了報告",
                        "description": "受入条件対応表 + git status をユーザに提示。",
                        "status": "completed",
                    },
                    {
                        "id": "37",
                        "subject": "Phase D / frontend 実装",
                        "description": "HTML/JS と README を追加する。",
                        "status": "pending",
                    },
                ],
            },
        },
        {
            "timestamp": "2026-05-11T07:00:20.861Z",
            "attributionSkill": "python-tdd-team",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "## Gate 3: Phase C 完了報告\n\n"
                            "### 検証結果\n"
                            "- `uv run pytest -q`: **192/192 passed**\n"
                            "- `uv run task ruff`: **All checks passed**\n\n"
                            "SECRET_TOKEN=should-not-leak\n"
                            "次は frontend HTML/JS + README + ローカル E2E の Phase D です。"
                        ),
                    }
                ],
            },
        },
        {
            "timestamp": "2026-05-11T07:20:58.431Z",
            "type": "file-history-snapshot",
            "snapshot": {
                "trackedFileBackups": {
                    "/home/vscode/.claude/plans/misty-sniffing-pinwheel.md": {
                        "backupFileName": "abc@v4",
                    }
                }
            },
        },
    ]


def test_project_log_dir_name_matches_claude_code_project_encoding() -> None:
    assert project_log_dir_name(Path("/workspaces/nova-parser")) == "-workspaces-nova-parser"


def test_generate_handoff_extracts_superpowers_state_and_redacts_secrets(tmp_path: Path) -> None:
    project = tmp_path / "nova-parser"
    project.mkdir()
    session = tmp_path / "session.jsonl"
    _write_jsonl(session, _sample_records())

    handoff = generate_handoff(
        session_path=session,
        project_dir=project,
        out_dir=project / "docs_draft" / "claude_handoffs",
    )

    assert handoff.markdown_path.exists()
    assert handoff.json_path.exists()

    data = json.loads(handoff.json_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["session"]["id"] == "session-1"
    assert data["session"]["agent_name"] == "add-regional-ocr-web-tool"
    assert data["session"]["last_prompt"].startswith("/python-tdd-team")
    assert data["skills"] == ["python-tdd-team"]
    assert data["tasks"][-1]["subject"] == "Phase D / frontend 実装"
    assert data["tasks"][-1]["status"] == "pending"
    assert data["next_work"] == ["Phase D / frontend 実装"]
    assert data["sources"]["plan_files"] == ["/home/vscode/.claude/plans/misty-sniffing-pinwheel.md"]

    markdown = handoff.markdown_path.read_text(encoding="utf-8")
    assert "# Claude Superpowers Handoff" in markdown
    assert "Phase C / Gate 3 完了報告" in markdown
    assert "Phase D / frontend 実装" in markdown
    assert "192/192 passed" in markdown
    assert "SECRET_TOKEN=should-not-leak" not in markdown
    assert "[REDACTED]" in markdown


def test_discover_project_sessions_lists_latest_first(tmp_path: Path) -> None:
    claude_home = tmp_path / ".claude"
    project_dir = Path("/workspaces/nova-parser")
    log_dir = claude_home / "projects" / project_log_dir_name(project_dir)
    first = log_dir / "first.jsonl"
    second = log_dir / "second.jsonl"
    _write_jsonl(first, [{"timestamp": "2026-01-01T00:00:00Z", "sessionId": "first"}])
    _write_jsonl(second, [{"timestamp": "2026-01-02T00:00:00Z", "sessionId": "second"}])

    sessions = discover_project_sessions(project_dir=project_dir, claude_home=claude_home)

    assert [session.path.name for session in sessions] == ["second.jsonl", "first.jsonl"]


def test_generate_handoff_applies_task_update_events_after_task_reminder(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    session = tmp_path / "task-update.jsonl"
    records = [
        {
            "type": "agent-name",
            "agentName": "handoff-agent",
            "sessionId": "session-task-update",
        },
        {
            "timestamp": "2026-05-11T06:59:41.438Z",
            "attachment": {
                "type": "task_reminder",
                "content": [
                    {"id": "35", "subject": "Phase C / reviewer", "description": "", "status": "in_progress"},
                    {"id": "36", "subject": "Phase C / Gate 3", "description": "", "status": "pending"},
                    {"id": "37", "subject": "Phase D / frontend 実装", "description": "", "status": "pending"},
                ],
            },
        },
        {
            "timestamp": "2026-05-11T07:00:21.195Z",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "TaskUpdate",
                        "input": {"taskId": "35", "status": "completed"},
                    }
                ],
            },
        },
        {
            "timestamp": "2026-05-11T07:00:21.240Z",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "TaskUpdate",
                        "input": {"taskId": "36", "status": "completed"},
                    }
                ],
            },
        },
    ]
    _write_jsonl(session, records)

    handoff = generate_handoff(session_path=session, project_dir=project, out_dir=project / "handoffs")

    data = json.loads(handoff.json_path.read_text(encoding="utf-8"))
    status_by_id = {task["id"]: task["status"] for task in data["tasks"]}
    assert status_by_id["35"] == "completed"
    assert status_by_id["36"] == "completed"
    assert data["next_work"] == ["Phase D / frontend 実装"]


def test_cli_writes_latest_handoff_to_default_repo_docs_dir(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    claude_home = tmp_path / ".claude"
    log_dir = claude_home / "projects" / project_log_dir_name(project)
    _write_jsonl(log_dir / "sample.jsonl", _sample_records())

    monkeypatch.chdir(project)
    exit_code = main(["--latest", "--claude-home", str(claude_home)])

    assert exit_code == 0
    handoffs = sorted((project / "docs_draft" / "claude_handoffs").glob("*.handoff.md"))
    assert len(handoffs) == 1
    assert "Phase C 完了報告" in handoffs[0].read_text(encoding="utf-8")


def test_pyproject_exposes_claude_handoff_script() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["nova-parser-claude-handoff"] == "nova_parser.claude_handoff:main"


def test_redact_handles_unquoted_double_quoted_and_single_quoted_assignments(tmp_path: Path) -> None:
    """unquoted / double-quoted / single-quoted / 値内空白 の secret がすべて redaction される。"""
    project = tmp_path / "repo"
    project.mkdir()
    session = tmp_path / "session.jsonl"
    text = (
        "## Gate 完了\n\n"
        "結果:\n"
        "API_KEY=raw-unquoted\n"
        'API_KEY="raw-double-quoted"\n'
        "TOKEN='raw-single-quoted'\n"
        'MY_SECRET="with space value"\n'
    )
    records = [
        {"type": "agent-name", "agentName": "redact-test", "sessionId": "s1"},
        {
            "timestamp": "2026-05-15T00:00:00Z",
            "attributionSkill": "secret-tester",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
            },
        },
    ]
    _write_jsonl(session, records)

    handoff = generate_handoff(session_path=session, project_dir=project, out_dir=project / "out")

    markdown = handoff.markdown_path.read_text(encoding="utf-8")
    payload = handoff.json_path.read_text(encoding="utf-8")

    for leak in ("raw-unquoted", "raw-double-quoted", "raw-single-quoted", "with space value"):
        assert leak not in markdown, f"Markdown に raw secret 残存: {leak}"
        assert leak not in payload, f"JSON に raw secret 残存: {leak}"

    assert "[REDACTED]" in markdown
    assert "[REDACTED]" in payload


def test_last_prompt_in_json_is_redacted(tmp_path: Path) -> None:
    """lastPrompt に含まれる secret が .handoff.json でも redaction されること。"""
    project = tmp_path / "repo"
    project.mkdir()
    session = tmp_path / "session.jsonl"
    records = [
        {"type": "agent-name", "agentName": "lp-redact", "sessionId": "s2"},
        {
            "type": "last-prompt",
            "lastPrompt": 'デバッグ中 API_KEY="should-not-leak-in-json" 確認',
            "sessionId": "s2",
        },
    ]
    _write_jsonl(session, records)

    handoff = generate_handoff(session_path=session, project_dir=project, out_dir=project / "out")

    data = json.loads(handoff.json_path.read_text(encoding="utf-8"))
    last_prompt = data["session"]["last_prompt"]

    assert "should-not-leak-in-json" not in last_prompt
    assert "[REDACTED]" in last_prompt

    markdown = handoff.markdown_path.read_text(encoding="utf-8")
    assert "should-not-leak-in-json" not in markdown
