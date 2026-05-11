import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".claude" / "scripts" / "exit-plan-codex-review.sh"


requires_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is required for fake Codex companion")


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    return project


def make_fake_home(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    companion = (
        home / ".claude" / "plugins" / "cache" / "openai-codex" / "codex" / "1.0.0" / "scripts" / "codex-companion.mjs"
    )
    companion.parent.mkdir(parents=True)
    companion.write_text(
        """
import fs from "node:fs";

if (process.env.FAKE_CODEX_LOG) {
  fs.appendFileSync(process.env.FAKE_CODEX_LOG, "call\\n");
}

const mode = process.env.FAKE_CODEX_MODE || "approve";

if (mode === "approve") {
  console.log(JSON.stringify({ result: { verdict: "approve", summary: "ok", findings: [], next_steps: [] } }));
} else if (mode === "needs-attention") {
  console.log(JSON.stringify({
    result: {
      verdict: "needs-attention",
      summary: "plan needs work",
      findings: [
        { severity: "medium", title: "Missing fallback", file: "PLAN", line_start: 1, body: "fallback is absent" }
      ],
      next_steps: ["add fallback"]
    }
  }));
} else if (mode === "invalid") {
  console.log("not json");
} else if (mode === "fail") {
  console.error("boom");
  process.exit(42);
} else {
  console.error(`unknown mode: ${mode}`);
  process.exit(2);
}
""",
        encoding="utf-8",
    )
    return home, tmp_path / "codex.log"


def run_hook(
    tmp_path: Path,
    *,
    plan: str,
    home: Path | None = None,
    project: Path | None = None,
    mode: str = "approve",
    session_id: str = "session-1",
    log_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    project = project or make_project(tmp_path)
    home = home or (tmp_path / "empty-home")
    tmpdir = tmp_path / "tmp"
    home.mkdir(parents=True, exist_ok=True)
    tmpdir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "TMPDIR": str(tmpdir),
            "CLAUDE_PROJECT_DIR": str(project),
            "FAKE_CODEX_MODE": mode,
        }
    )
    if log_path is not None:
        env["FAKE_CODEX_LOG"] = str(log_path)

    payload = {
        "tool_input": {"plan": plan},
        "session_id": session_id,
        "cwd": str(project),
    }
    return subprocess.run(
        ["bash", str(SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=project,
        env=env,
        check=False,
    )


def parse_hook_output(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), result.stderr
    return json.loads(result.stdout)


def decision(output: dict) -> str:
    return output["hookSpecificOutput"]["permissionDecision"]


def marker_files(tmp_path: Path) -> list[Path]:
    marker_dir = tmp_path / "tmp" / "claude-codex-adv-review"
    return sorted(marker_dir.glob("*")) if marker_dir.exists() else []


def test_empty_plan_exits_without_hook_output(tmp_path: Path) -> None:
    result = run_hook(tmp_path, plan="")

    assert result.returncode == 0
    assert result.stdout == ""
    assert marker_files(tmp_path) == []


def test_missing_companion_asks_for_confirmation(tmp_path: Path) -> None:
    result = run_hook(tmp_path, plan="implement the change")
    output = parse_hook_output(result)

    assert decision(output) == "ask"
    assert "codex-companion.mjs" in output["systemMessage"]
    assert marker_files(tmp_path) == []


@requires_node
def test_approve_allows_and_reuses_marker(tmp_path: Path) -> None:
    home, log_path = make_fake_home(tmp_path)
    project = make_project(tmp_path)

    first = parse_hook_output(run_hook(tmp_path, plan="ship it", home=home, project=project, log_path=log_path))
    second = parse_hook_output(run_hook(tmp_path, plan="ship it", home=home, project=project, log_path=log_path))

    assert decision(first) == "allow"
    assert decision(second) == "allow"
    assert log_path.read_text(encoding="utf-8").splitlines() == ["call"]
    assert len(marker_files(tmp_path)) == 1


@requires_node
def test_needs_attention_asks_and_does_not_write_marker(tmp_path: Path) -> None:
    home, log_path = make_fake_home(tmp_path)
    project = make_project(tmp_path)

    first = parse_hook_output(
        run_hook(tmp_path, plan="risky plan", home=home, project=project, mode="needs-attention", log_path=log_path)
    )
    second = parse_hook_output(
        run_hook(tmp_path, plan="risky plan", home=home, project=project, mode="needs-attention", log_path=log_path)
    )

    assert decision(first) == "ask"
    assert decision(second) == "ask"
    assert "needs-attention" in first["systemMessage"]
    assert log_path.read_text(encoding="utf-8").splitlines() == ["call", "call"]
    assert marker_files(tmp_path) == []


@requires_node
@pytest.mark.parametrize("mode", ["invalid", "fail"])
def test_invalid_or_failed_review_asks_and_does_not_write_marker(tmp_path: Path, mode: str) -> None:
    home, log_path = make_fake_home(tmp_path)
    project = make_project(tmp_path)

    output = parse_hook_output(
        run_hook(tmp_path, plan="plan", home=home, project=project, mode=mode, log_path=log_path)
    )

    assert decision(output) == "ask"
    assert "未完了" in output["systemMessage"]
    assert marker_files(tmp_path) == []


@requires_node
def test_explicit_bypass_allows_without_marker_for_non_approve(tmp_path: Path) -> None:
    home, log_path = make_fake_home(tmp_path)
    project = make_project(tmp_path)
    plan = "risky plan\nCodex-Review-Bypass: accepted false positive"

    output = parse_hook_output(
        run_hook(tmp_path, plan=plan, home=home, project=project, mode="needs-attention", log_path=log_path)
    )

    assert decision(output) == "allow"
    assert "accepted false positive" in output["systemMessage"]
    assert log_path.read_text(encoding="utf-8").splitlines() == ["call"]
    assert marker_files(tmp_path) == []


@requires_node
def test_worktree_change_invalidates_approve_marker(tmp_path: Path) -> None:
    home, log_path = make_fake_home(tmp_path)
    project = make_project(tmp_path)
    subprocess.run(["git", "init"], cwd=project, check=True, stdout=subprocess.DEVNULL)

    first = parse_hook_output(run_hook(tmp_path, plan="same plan", home=home, project=project, log_path=log_path))
    (project / "new.txt").write_text("changed\n", encoding="utf-8")
    second = parse_hook_output(run_hook(tmp_path, plan="same plan", home=home, project=project, log_path=log_path))

    assert decision(first) == "allow"
    assert decision(second) == "allow"
    assert log_path.read_text(encoding="utf-8").splitlines() == ["call", "call"]
    assert len(marker_files(tmp_path)) == 2
