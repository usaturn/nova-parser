from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
AGENTS_SKILL = REPO_ROOT / ".agents/skills/pr-review/SKILL.md"
CLAUDE_SKILL = REPO_ROOT / ".claude/skills/pr-review/SKILL.md"
AGENTS_HELPER = REPO_ROOT / ".agents/skills/pr-review/scripts/pr_review_workspace.py"
CLAUDE_HELPER = REPO_ROOT / ".claude/skills/pr-review/scripts/pr_review_workspace.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_review_contract(content: str) -> None:
    assert 'gh pr diff "$PR_NUMBER"' in content
    assert 'git rev-parse --short=12 "$PR_HEAD"' in content
    assert 'date -u +"%Y-%m-%dT%H:%M:%SZ"' in content
    assert "previous_review" in content
    assert "Review history" in content
    assert "Reviewed at (UTC)" in content
    assert "Initial" in content
    assert "Update" in content
    assert "検出時 HEAD" in content
    assert "Resolved findings" in content
    assert "解消確認時 HEAD" in content
    assert "不明（旧形式）" in content
    assert content.count("headRefOid") >= 3
    assert "他モデルのレビュー本文" in content
    assert 'PR_URL=$(printf \'%s\' "$PR_JSON" | jq -r .url)' in content
    assert 'if printf \'%s\' "$PR_URL" | grep -q devenv; then' in content
    assert 'MAIN_ROOT="$TOPLEVEL/devenv"' in content
    assert 'MAIN_ROOT="$(pwd)"' in content
    assert "git remote get-url origin" not in content
    assert "追跡パス" not in content


@pytest.mark.parametrize("skill", [AGENTS_SKILL, CLAUDE_SKILL])
def test_pr_review_skills_define_review_update_contract(skill: Path) -> None:
    assert_review_contract(read(skill))


def test_pr_review_helpers_are_identical() -> None:
    assert CLAUDE_HELPER.read_bytes() == AGENTS_HELPER.read_bytes()


def test_claude_skill_allows_required_commands() -> None:
    content = read(CLAUDE_SKILL)
    assert "Bash(date *)" in content
    assert '--model-name "$MODEL_NAME"' in content
    assert ".claude/skills/pr-review/scripts/pr_review_workspace.py" in content
    # Claude allowed-tools only permit Edit/Write under /tmp/pr-review-*/...
    assert "--temp-root /tmp" in content
