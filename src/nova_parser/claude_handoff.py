"""Claude Code の Superpowers 実行結果を Codex 向け handoff に変換する。"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SessionCandidate:
    """Claude Code session JSONL の候補。"""

    path: Path
    timestamp: str


@dataclass(frozen=True)
class HandoffResult:
    """生成された handoff artifact。"""

    markdown_path: Path
    json_path: Path


_SECRET_RE = re.compile(r"(?i)\b([A-Z0-9_]*(?:SECRET|TOKEN|CREDENTIAL|PASSWORD|API_KEY)[A-Z0-9_]*\s*=\s*)([^\s`\"']+)")
_MAX_REPORT_CHARS = 12000


def project_log_dir_name(project_dir: Path) -> str:
    """Claude Code が `~/.claude/projects` で使う project dir 名へ変換する。"""
    path = project_dir.expanduser()
    try:
        path = path.resolve()
    except OSError:
        path = path.absolute()
    return str(path).replace("/", "-")


def discover_project_sessions(project_dir: Path, claude_home: Path | None = None) -> list[SessionCandidate]:
    """project に対応する Claude Code session JSONL を新しい順で返す。"""
    home = claude_home or Path.home() / ".claude"
    log_dir = home / "projects" / project_log_dir_name(project_dir)
    if not log_dir.exists():
        return []

    candidates = [
        SessionCandidate(path=path, timestamp=_session_timestamp(path))
        for path in log_dir.glob("*.jsonl")
        if path.is_file()
    ]
    return sorted(candidates, key=lambda candidate: candidate.timestamp, reverse=True)


def generate_handoff(session_path: Path, project_dir: Path, out_dir: Path) -> HandoffResult:
    """Claude Code session JSONL から Codex 用 handoff Markdown/JSON を生成する。"""
    records = _read_jsonl(session_path)
    generated_at = _now_utc()
    summary = _build_summary(records, session_path=session_path, project_dir=project_dir, generated_at=generated_at)
    out_dir.mkdir(parents=True, exist_ok=True)
    session_name = summary["session"]["agent_name"] or summary["session"]["id"]
    stem = f"{_timestamp_for_filename(generated_at)}-{_slug(session_name)}"
    markdown_path = out_dir / f"{stem}.handoff.md"
    json_path = out_dir / f"{stem}.handoff.json"

    markdown_path.write_text(_render_markdown(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return HandoffResult(markdown_path=markdown_path, json_path=json_path)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint。"""
    parser = argparse.ArgumentParser(description="Claude Code Superpowers の結果を Codex handoff に変換する")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--latest", action="store_true", help="現在 project の最新 Claude session を handoff 化する")
    group.add_argument("--session-id", help="指定 session id / JSONL stem を handoff 化する")
    group.add_argument("--list", action="store_true", help="候補 session を新しい順に表示する")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd(), help="Claude project として扱うディレクトリ")
    parser.add_argument("--claude-home", type=Path, default=None, help="Claude home。既定は ~/.claude")
    parser.add_argument("--out-dir", type=Path, default=Path("docs_draft/claude_handoffs"))
    parser.add_argument("--stdout", action="store_true", help="生成した Markdown を標準出力する")
    args = parser.parse_args(argv)

    project_dir = args.project_dir.resolve()
    sessions = discover_project_sessions(project_dir=project_dir, claude_home=args.claude_home)
    if args.list:
        for candidate in sessions:
            print(f"{candidate.timestamp}\t{candidate.path.stem}\t{candidate.path}")
        return 0

    session_path = _select_session(sessions, session_id=args.session_id)
    if session_path is None:
        parser.error("Claude session JSONL が見つかりません。--session-id または --latest を確認してください。")

    out_dir = args.out_dir if args.out_dir.is_absolute() else project_dir / args.out_dir
    result = generate_handoff(session_path=session_path, project_dir=project_dir, out_dir=out_dir)
    if args.stdout:
        print(result.markdown_path.read_text(encoding="utf-8"), end="")
    else:
        print(result.markdown_path)
        print(result.json_path)
    return 0


def _select_session(candidates: list[SessionCandidate], session_id: str | None) -> Path | None:
    if not candidates:
        return None
    if session_id is None:
        return candidates[0].path
    for candidate in candidates:
        if candidate.path.stem == session_id:
            return candidate.path
        records = _read_jsonl(candidate.path)
        if any(record.get("sessionId") == session_id for record in records):
            return candidate.path
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _session_timestamp(path: Path) -> str:
    timestamp = ""
    for record in _read_jsonl(path):
        if isinstance(record.get("timestamp"), str):
            timestamp = record["timestamp"]
    if timestamp:
        return timestamp
    mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=datetime.UTC)
    return mtime.isoformat().replace("+00:00", "Z")


def _now_utc() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _build_summary(
    records: list[dict[str, Any]], *, session_path: Path, project_dir: Path, generated_at: str
) -> dict[str, Any]:
    session_id = session_path.stem
    ai_title = ""
    agent_name = ""
    permission_mode = ""
    last_prompt = ""
    skills: list[str] = []
    reports: list[dict[str, str]] = []
    latest_tasks: list[dict[str, str]] = []
    plan_files: list[str] = []

    for record in records:
        raw_session_id = record.get("sessionId")
        if isinstance(raw_session_id, str) and raw_session_id:
            session_id = raw_session_id
        if record.get("type") == "ai-title" and isinstance(record.get("aiTitle"), str):
            ai_title = record["aiTitle"]
        if record.get("type") == "agent-name" and isinstance(record.get("agentName"), str):
            agent_name = record["agentName"]
        if record.get("type") == "permission-mode" and isinstance(record.get("permissionMode"), str):
            permission_mode = record["permissionMode"]
        if record.get("type") == "last-prompt" and isinstance(record.get("lastPrompt"), str):
            last_prompt = record["lastPrompt"]

        skill = record.get("attributionSkill")
        if isinstance(skill, str) and skill and skill not in skills:
            skills.append(skill)

        task_content = record.get("attachment", {}).get("content")
        if record.get("attachment", {}).get("type") == "task_reminder" and isinstance(task_content, list):
            latest_tasks = [_normalize_task(item) for item in task_content if isinstance(item, dict)]
        for update in _task_updates(record):
            _apply_task_update(latest_tasks, update)

        if record.get("type") == "file-history-snapshot":
            tracked = record.get("snapshot", {}).get("trackedFileBackups", {})
            if isinstance(tracked, dict):
                for path in tracked:
                    if "/.claude/plans/" in path and path.endswith(".md") and path not in plan_files:
                        plan_files.append(path)

        text = _assistant_text(record)
        if text and _looks_like_report(text):
            reports.append(
                {
                    "timestamp": str(record.get("timestamp", "")),
                    "skill": str(record.get("attributionSkill", "")),
                    "text": _redact(_truncate(text)),
                }
            )

    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "project_dir": str(project_dir),
        "session": {
            "id": session_id,
            "path": str(session_path),
            "ai_title": ai_title,
            "agent_name": agent_name,
            "permission_mode": permission_mode,
            "last_prompt": last_prompt,
        },
        "skills": skills,
        "tasks": latest_tasks,
        "reports": reports[-5:],
        "next_work": _next_work(latest_tasks, reports),
        "sources": {
            "session_jsonl": str(session_path),
            "plan_files": plan_files,
        },
        "git": _git_state(project_dir),
    }


def _normalize_task(item: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(item.get("id", "")),
        "subject": str(item.get("subject", "")),
        "description": str(item.get("description", "")),
        "status": str(item.get("status", "")),
    }


def _task_updates(record: dict[str, Any]) -> list[dict[str, str]]:
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    updates: list[dict[str, str]] = []
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "tool_use" or item.get("name") != "TaskUpdate":
            continue
        tool_input = item.get("input")
        if not isinstance(tool_input, dict):
            continue
        task_id = tool_input.get("taskId")
        status = tool_input.get("status")
        if isinstance(task_id, str) and isinstance(status, str):
            updates.append({"id": task_id, "status": status})
    return updates


def _apply_task_update(tasks: list[dict[str, str]], update: dict[str, str]) -> None:
    for task in tasks:
        if task.get("id") == update["id"]:
            task["status"] = update["status"]
            return


def _assistant_text(record: dict[str, Any]) -> str:
    message = record.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    parts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
    return "\n".join(part for part in parts if isinstance(part, str))


def _looks_like_report(text: str) -> bool:
    markers = ("Gate", "Phase", "フェイズ", "完了報告", "検証結果", "次は", "approved")
    return any(marker in text for marker in markers)


def _next_work(tasks: list[dict[str, str]], reports: list[dict[str, str]]) -> list[str]:
    pending = [
        task["subject"] for task in tasks if task.get("status") not in {"completed", "done"} and task["subject"]
    ]
    if pending:
        return pending
    for report in reversed(reports):
        for line in report["text"].splitlines():
            if "次は" in line:
                return [line.strip()]
    return []


def _git_state(project_dir: Path) -> dict[str, str]:
    return {
        "branch": _run_git(project_dir, "rev-parse", "--abbrev-ref", "HEAD"),
        "head": _run_git(project_dir, "rev-parse", "--short", "HEAD"),
        "status": _run_git(project_dir, "status", "--short"),
    }


def _run_git(project_dir: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_dir,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _render_markdown(summary: dict[str, Any]) -> str:
    session = summary["session"]
    lines = [
        "# Claude Superpowers Handoff",
        "",
        "## Session",
        "",
        f"- Session ID: `{session['id']}`",
        f"- Agent: `{session['agent_name'] or session['ai_title'] or 'unknown'}`",
        f"- Last prompt: `{_redact(session['last_prompt'])}`",
        f"- Permission mode: `{session['permission_mode'] or 'unknown'}`",
        f"- Source JSONL: `{summary['sources']['session_jsonl']}`",
        "",
        "## Detected Skills",
        "",
        _bullet_list(summary["skills"]) or "- None detected",
        "",
        "## Task State",
        "",
        _task_table(summary["tasks"]),
        "",
        "## Completion Report",
        "",
    ]
    if summary["reports"]:
        for report in summary["reports"]:
            label = report["timestamp"] or "unknown time"
            skill = f" / {report['skill']}" if report["skill"] else ""
            lines.extend([f"### {label}{skill}", "", report["text"], ""])
    else:
        lines.extend(["No completion report-like assistant messages were detected.", ""])

    lines.extend(
        [
            "## Next Recommended Work",
            "",
            _bullet_list(summary["next_work"]) or "- No pending task detected",
            "",
            "## Source Files",
            "",
            _bullet_list(summary["sources"]["plan_files"]) or "- No Claude plan files detected",
            "",
            "## Git",
            "",
            f"- Branch: `{summary['git']['branch']}`",
            f"- HEAD: `{summary['git']['head']}`",
            "- Status:",
            "```text",
            summary["git"]["status"] or "(clean or unavailable)",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _task_table(tasks: list[dict[str, str]]) -> str:
    if not tasks:
        return "No task reminder was detected."
    lines = ["| ID | Status | Subject |", "|---|---|---|"]
    for task in tasks:
        lines.append(f"| {task['id']} | {task['status']} | {_escape_table(task['subject'])} |")
    return "\n".join(lines)


def _bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items if item)


def _escape_table(text: str) -> str:
    return text.replace("|", "\\|")


def _redact(text: str) -> str:
    return _SECRET_RE.sub(r"\1[REDACTED]", text)


def _truncate(text: str) -> str:
    if len(text) <= _MAX_REPORT_CHARS:
        return text
    return f"... (truncated to last {_MAX_REPORT_CHARS} chars)\n{text[-_MAX_REPORT_CHARS:]}"


def _timestamp_for_filename(timestamp: str) -> str:
    return re.sub(r"[^0-9]", "", timestamp)[:14] or "unknown-time"


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "claude-session"
