from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "pr_review_workspace.py"
SPEC = importlib.util.spec_from_file_location("pr_review_workspace", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
workspace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workspace)

THREAD_ID = "019fd23a-4723-7e02-83d9-58f32849f5ab"


def write_rollout(codex_home: Path, models: list[str], thread_id: str = THREAD_ID) -> Path:
    rollout = codex_home / "sessions" / "2026" / "08" / "05" / f"rollout-{thread_id}.jsonl"
    rollout.parent.mkdir(parents=True, exist_ok=True)
    with rollout.open("w", encoding="utf-8") as stream:
        for model in models:
            record = {
                "type": "turn_context",
                "payload": {"model": model},
            }
            stream.write(json.dumps(record) + "\n")
    return rollout


def write_rollout_text(codex_home: Path, text: str) -> Path:
    rollout = codex_home / "sessions" / "2026" / "08" / "05" / f"rollout-{THREAD_ID}.jsonl"
    rollout.parent.mkdir(parents=True, exist_ok=True)
    rollout.write_text(text, encoding="utf-8")
    return rollout


def test_resolve_codex_model_name_uses_latest_turn_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    codex_home = tmp_path / "codex"
    write_rollout(codex_home, ["gpt-5", "gpt-5.6-sol"])
    (codex_home / "config.toml").write_text('model = "gpt-5"\n', encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD_ID)

    assert workspace.resolve_codex_model_name() == "gpt-5.6-sol"


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("missing-thread", "CODEX_THREAD_ID"),
        ("missing-rollout", "rollout"),
        ("missing-context", "turn_context"),
        ("unsafe-model", "safe filename"),
        ("non-unique-rollout", "exactly one"),
        ("invalid-json", "invalid rollout JSON"),
    ],
)
def test_resolve_codex_model_name_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    setup: str,
    message: str,
) -> None:
    codex_home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)

    if setup != "missing-thread":
        monkeypatch.setenv("CODEX_THREAD_ID", THREAD_ID)
    if setup == "missing-context":
        rollout = write_rollout(codex_home, [])
        rollout.write_text('{"type":"event_msg","payload":{}}\n', encoding="utf-8")
    if setup == "unsafe-model":
        # Spaces and other non-filename characters remain rejected after `/` → `-`.
        write_rollout(codex_home, ["gpt 5.6-sol"])
    if setup == "non-unique-rollout":
        write_rollout(codex_home, ["gpt-5.6-sol"])
        write_rollout(
            codex_home / "sessions" / "2026" / "08" / "05" / "other",
            ["gpt-5.6-sol"],
        )
    if setup == "invalid-json":
        write_rollout(codex_home, ["gpt-5.6-sol"]).write_text("this is not json\n", encoding="utf-8")

    with pytest.raises(workspace.WorkspaceError, match=message):
        workspace.resolve_codex_model_name()


def test_resolve_codex_model_name_replaces_slash_with_hyphen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    codex_home = tmp_path / "codex"
    write_rollout(codex_home, ["opencode/deepseek-v4-flash-free"])
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD_ID)

    assert workspace.resolve_codex_model_name() == "opencode-deepseek-v4-flash-free"


def test_resolve_codex_model_name_ignores_unterminated_partial_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex"
    complete = json.dumps({"type": "turn_context", "payload": {"model": "gpt-5.6-sol"}})
    write_rollout_text(codex_home, complete + '\n{"type":"event_msg"')
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD_ID)

    assert workspace.resolve_codex_model_name() == "gpt-5.6-sol"


@pytest.mark.parametrize(
    "unexpected_record",
    [
        123,
        ["turn_context"],
        {"type": "turn_context", "payload": None},
        {"type": "turn_context", "payload": []},
        {"type": "turn_context", "payload": {"model": None}},
    ],
)
def test_resolve_codex_model_name_skips_records_outside_expected_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unexpected_record: object,
) -> None:
    codex_home = tmp_path / "codex"
    lines = [
        json.dumps(unexpected_record),
        json.dumps({"type": "turn_context", "payload": {"model": "gpt-5.6-sol"}}),
    ]
    write_rollout_text(codex_home, "\n".join(lines) + "\n")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD_ID)

    assert workspace.resolve_codex_model_name() == "gpt-5.6-sol"


def test_resolve_codex_model_name_rejects_malformed_completed_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    codex_home = tmp_path / "codex"
    write_rollout_text(
        codex_home,
        '{"type":"turn_context","payload":{"model":"gpt-5.6-sol"}}\nnot-json\n',
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD_ID)

    with pytest.raises(workspace.WorkspaceError, match="invalid rollout JSON at line 2"):
        workspace.resolve_codex_model_name()


def test_resolve_runtime_model_name_uses_explicit_name_outside_codex() -> None:
    assert workspace.resolve_runtime_model_name("opus-5", {}) == (
        "opus-5",
        "explicit",
    )


def test_resolve_runtime_model_name_replaces_slash_with_hyphen() -> None:
    assert workspace.resolve_runtime_model_name("opencode/deepseek-v4-flash-free", {}) == (
        "opencode-deepseek-v4-flash-free",
        "explicit",
    )


@pytest.mark.parametrize(
    ("model_name", "message"),
    [
        (None, "model name is required outside Codex"),
        ("opus 5", "safe filename"),
        ("../evil", "safe filename"),
    ],
)
def test_resolve_runtime_model_name_fails_closed_outside_codex(
    model_name: str | None,
    message: str,
) -> None:
    with pytest.raises(workspace.WorkspaceError, match=message):
        workspace.resolve_runtime_model_name(model_name, {})


def test_resolve_runtime_model_name_rejects_codex_override(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    write_rollout(codex_home, ["gpt-5.6-sol"])
    environ = {
        "CODEX_HOME": str(codex_home),
        "CODEX_THREAD_ID": THREAD_ID,
    }

    with pytest.raises(workspace.WorkspaceError, match="does not match Codex runtime"):
        workspace.resolve_runtime_model_name("gpt-5", environ)


def test_resolve_runtime_model_name_accepts_slash_equivalent_explicit_in_codex(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex"
    write_rollout(codex_home, ["opencode/deepseek-v4-flash-free"])
    environ = {
        "CODEX_HOME": str(codex_home),
        "CODEX_THREAD_ID": THREAD_ID,
    }

    assert workspace.resolve_runtime_model_name("opencode/deepseek-v4-flash-free", environ) == (
        "opencode-deepseek-v4-flash-free",
        "codex-rollout",
    )


def test_review_artifact_paths_preserve_exact_model_name(tmp_path: Path) -> None:
    draft, destination = workspace.review_artifact_paths(
        tmp_path / "review-backup",
        "fix/herdr-session-cwd",
        "gpt-5.6-sol",
    )

    assert draft == tmp_path / "review-backup" / "gpt-5.6-sol.md"
    assert destination == "reviews/fix-herdr-session-cwd/gpt-5.6-sol.md"


def test_review_artifact_paths_use_slash_sanitized_model_name(tmp_path: Path) -> None:
    draft, destination = workspace.review_artifact_paths(
        tmp_path / "review-backup",
        "fix/herdr-session-cwd",
        "opencode-deepseek-v4-flash-free",
    )

    assert draft == (tmp_path / "review-backup" / "opencode-deepseek-v4-flash-free.md")
    assert destination == "reviews/fix-herdr-session-cwd/opencode-deepseek-v4-flash-free.md"


def test_destination_fingerprint_distinguishes_symlink_entries(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("review\n", encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(target.name)
    dangling = tmp_path / "dangling.md"
    dangling.symlink_to("missing.md")

    target_fingerprint = workspace.destination_fingerprint(target)
    link_fingerprint = workspace.destination_fingerprint(link)
    dangling_fingerprint = workspace.destination_fingerprint(dangling)

    assert target_fingerprint["kind"] == "file"
    assert link_fingerprint["kind"] == "symlink"
    assert dangling_fingerprint["kind"] == "symlink"
    assert link_fingerprint["sha256"] != dangling_fingerprint["sha256"]


def test_snapshot_existing_review_copies_regular_file(tmp_path: Path) -> None:
    backup_dir = tmp_path / "review-backup"
    backup_dir.mkdir()
    destination = tmp_path / "reviews/branch/gpt-5.6-sol.md"
    destination.parent.mkdir(parents=True)
    destination.write_text("existing review\n", encoding="utf-8")

    fingerprint, previous = workspace.snapshot_existing_review(destination, backup_dir)

    assert fingerprint == workspace.destination_fingerprint(destination)
    assert previous == backup_dir / "previous-review.md"
    assert previous.read_text(encoding="utf-8") == "existing review\n"


def test_snapshot_existing_review_reports_missing(tmp_path: Path) -> None:
    backup_dir = tmp_path / "review-backup"
    backup_dir.mkdir()
    destination = tmp_path / "reviews/branch/gpt-5.6-sol.md"

    fingerprint, previous = workspace.snapshot_existing_review(destination, backup_dir)

    assert fingerprint == {"path": str(destination), "kind": "missing"}
    assert previous is None
    assert list(backup_dir.iterdir()) == []


@pytest.mark.parametrize("kind", ["directory", "symlink", "fifo"])
def test_snapshot_existing_review_rejects_non_regular(tmp_path: Path, kind: str) -> None:
    backup_dir = tmp_path / "review-backup"
    backup_dir.mkdir()
    destination = tmp_path / "reviews/branch/gpt-5.6-sol.md"
    destination.parent.mkdir(parents=True)
    if kind == "directory":
        destination.mkdir()
    elif kind == "symlink":
        target = tmp_path / "other-model.md"
        target.write_text("must not be read\n", encoding="utf-8")
        destination.symlink_to(target)
    else:
        os.mkfifo(destination)

    with pytest.raises(
        workspace.WorkspaceError,
        match="existing review destination must be a regular file",
    ):
        workspace.snapshot_existing_review(destination, backup_dir)
    assert list(backup_dir.iterdir()) == []


def test_snapshot_existing_review_rejects_source_race(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backup_dir = tmp_path / "review-backup"
    backup_dir.mkdir()
    destination = tmp_path / "reviews/branch/gpt-5.6-sol.md"
    destination.parent.mkdir(parents=True)
    destination.write_text("existing review\n", encoding="utf-8")
    original = workspace.destination_fingerprint
    calls = 0

    def changing(path: Path) -> dict[str, str]:
        nonlocal calls
        result = original(path)
        if path == destination:
            calls += 1
            if calls == 2:
                return {**result, "sha256": "0" * 64}
        return result

    monkeypatch.setattr(workspace, "destination_fingerprint", changing)
    with pytest.raises(
        workspace.WorkspaceError,
        match="existing review changed while snapshotting",
    ):
        workspace.snapshot_existing_review(destination, backup_dir)
    assert not (backup_dir / "previous-review.md").exists()


def test_atomic_copy_replaces_internal_destination_symlink_entry(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    branch_dir = repo / "reviews" / "branch"
    branch_dir.mkdir(parents=True)
    target = branch_dir / "actual.md"
    target.write_text("old target\n", encoding="utf-8")
    link = branch_dir / "model.md"
    link.symlink_to(target.name)
    draft = tmp_path / "draft.md"
    draft.write_text("new review\n", encoding="utf-8")

    destination = workspace.safe_destination(repo, "reviews/branch/model.md")
    assert destination == link

    workspace.atomic_copy(draft, destination)

    assert not destination.is_symlink()
    assert destination.read_text(encoding="utf-8") == "new review\n"
    assert target.read_text(encoding="utf-8") == "old target\n"


def test_safe_destination_rejects_symlink_escape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    reviews = repo / "reviews"
    outside = repo / "outside"
    reviews.mkdir(parents=True)
    outside.mkdir()
    (reviews / "branch").symlink_to(outside, target_is_directory=True)

    with pytest.raises(workspace.WorkspaceError, match="escapes"):
        workspace.safe_destination(repo, "reviews/branch/model.md")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def make_repo(path: Path, *, tracked_reviews: bool = True) -> str:
    path.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    git(path, "config", "user.name", "Test User")
    git(path, "config", "user.email", "test@example.com")
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    git(path, "add", "README.md")
    if tracked_reviews:
        old_review = path / "reviews" / "fix-herdr-session-cwd" / "gpt-5.md"
        old_review.parent.mkdir(parents=True)
        old_review.write_text("existing alias\n", encoding="utf-8")
        git(path, "add", "reviews/fix-herdr-session-cwd/gpt-5.md")
    git(path, "commit", "-m", "fixture")
    return git(path, "rev-parse", "HEAD")


def test_create_requires_explicit_model_outside_codex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    temp_root = tmp_path / "sessions"

    with pytest.raises(workspace.WorkspaceError, match="required outside Codex"):
        workspace.create(
            argparse.Namespace(
                repo=str(tmp_path / "unused-repo"),
                pr_number=5,
                commit="unused-commit",
                head_branch="fix/model-name",
                model_name=None,
                temp_root=str(temp_root),
            )
        )

    assert not temp_root.exists()


def test_create_pins_slash_model_name_as_hyphenated_filename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    repo = tmp_path / "repo"
    commit = make_repo(repo)

    result = workspace.create(
        argparse.Namespace(
            repo=str(repo),
            pr_number=42,
            commit=commit,
            head_branch="fix/model-name",
            model_name="opencode/deepseek-v4-flash-free",
            temp_root=str(tmp_path / "sessions"),
        )
    )

    assert result["model_name"] == "opencode-deepseek-v4-flash-free"
    assert result["destination"] == "reviews/fix-model-name/opencode-deepseek-v4-flash-free.md"
    assert result["draft"].endswith("/opencode-deepseek-v4-flash-free.md")


def test_create_pins_explicit_model_outside_codex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    repo = tmp_path / "repo"
    commit = make_repo(repo)

    result = workspace.create(
        argparse.Namespace(
            repo=str(repo),
            pr_number=5,
            commit=commit,
            head_branch="fix/model-name",
            model_name="opus-5",
            temp_root=str(tmp_path / "sessions"),
        )
    )

    state = json.loads(Path(result["state_file"]).read_text(encoding="utf-8"))
    assert result["model_name"] == "opus-5"
    assert result["model_source"] == "explicit"
    assert result["destination"] == "reviews/fix-model-name/opus-5.md"
    assert state["version"] == 6
    assert state["model_source"] == "explicit"


def test_save_uses_pinned_explicit_model_without_codex_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    repo = tmp_path / "repo-save"
    commit = make_repo(repo)
    result = workspace.create(
        argparse.Namespace(
            repo=str(repo),
            pr_number=5,
            commit=commit,
            head_branch="fix/model-name",
            model_name="opus-5",
            temp_root=str(tmp_path / "save-sessions"),
        )
    )
    Path(result["draft"]).write_text("review\n", encoding="utf-8")

    saved = workspace.save(argparse.Namespace(state=result["state_file"]))

    assert saved["destination"].endswith("/reviews/fix-model-name/opus-5.md")
    assert Path(saved["destination"]).read_text(encoding="utf-8") == "review\n"


def test_save_rejects_unknown_model_source(created_session: dict[str, Any]) -> None:
    result = created_session["result"]
    state_file = Path(result["state_file"])
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["model_source"] = "unknown"
    state_file.write_text(json.dumps(state) + "\n", encoding="utf-8")

    with pytest.raises(workspace.WorkspaceError, match="invalid PR-review session state"):
        workspace.save(argparse.Namespace(state=str(state_file)))


def test_create_pins_model_and_artifact_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    codex_home = tmp_path / "codex"
    write_rollout(codex_home, ["gpt-5.6-sol"])
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD_ID)
    repo = tmp_path / "repo"
    commit = make_repo(repo)

    result = workspace.create(
        argparse.Namespace(
            repo=str(repo),
            pr_number=4,
            commit=commit,
            head_branch="fix/herdr-session-cwd",
            model_name=None,
            temp_root=str(tmp_path / "sessions"),
        )
    )

    assert result["model_name"] == "gpt-5.6-sol"
    assert result["destination"] == "reviews/fix-herdr-session-cwd/gpt-5.6-sol.md"
    assert Path(result["draft"]).name == "gpt-5.6-sol.md"
    assert (repo / "reviews/fix-herdr-session-cwd/gpt-5.md").read_text(encoding="utf-8") == "existing alias\n"
    state = json.loads(Path(result["state_file"]).read_text(encoding="utf-8"))
    assert state["version"] == 6
    assert result["previous_review"] is None
    assert state["previous_review"] is None
    assert state["model_source"] == "codex-rollout"
    assert result["model_source"] == "codex-rollout"
    assert state["head_branch"] == "fix/herdr-session-cwd"
    assert state["model_name"] == "gpt-5.6-sol"
    assert state["draft"] == result["draft"]
    assert state["destination"] == result["destination"]


def test_create_pins_existing_review_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    codex_home = tmp_path / "codex"
    write_rollout(codex_home, ["gpt-5.6-sol"])
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD_ID)
    repo = tmp_path / "repo"
    commit = make_repo(repo)
    own_review = repo / "reviews/fix-herdr-session-cwd/gpt-5.6-sol.md"
    own_review.write_text("own existing review\n", encoding="utf-8")

    result = workspace.create(
        argparse.Namespace(
            repo=str(repo),
            pr_number=4,
            commit=commit,
            head_branch="fix/herdr-session-cwd",
            model_name=None,
            temp_root=str(tmp_path / "sessions"),
        )
    )

    previous = Path(str(result["previous_review"]))
    state = json.loads(Path(result["state_file"]).read_text(encoding="utf-8"))
    assert previous.name == "previous-review.md"
    assert previous.read_text(encoding="utf-8") == "own existing review\n"
    assert state["version"] == 6
    assert state["previous_review"] == str(previous)
    assert state["destination_fingerprint"] == workspace.destination_fingerprint(own_review)


def test_load_state_rejects_tampered_previous_review(
    created_session: dict[str, Any],
) -> None:
    state_file = Path(created_session["result"]["state_file"])
    state = json.loads(state_file.read_text(encoding="utf-8"))
    outside = state_file.parent.parent / "another-review.md"
    outside.write_text("outside session\n", encoding="utf-8")
    state["previous_review"] = str(outside)
    state_file.write_text(json.dumps(state) + "\n", encoding="utf-8")

    with pytest.raises(
        workspace.WorkspaceError,
        match="previous review snapshot does not match its session",
    ):
        workspace.load_state(str(state_file))


@pytest.mark.parametrize("head_branch", ["", "/", ".", ".."])
def test_review_artifact_paths_reject_invalid_branch(tmp_path: Path, head_branch: str) -> None:
    with pytest.raises(workspace.WorkspaceError, match="head branch"):
        workspace.review_artifact_paths(tmp_path, head_branch, "gpt-5.6-sol")


def test_save_parser_rejects_caller_selected_paths() -> None:
    with pytest.raises(SystemExit):
        workspace.parser().parse_args(
            [
                "save",
                "--state",
                "/tmp/session.json",
                "--draft",
                "/tmp/gpt-5.md",
                "--destination",
                "reviews/branch/gpt-5.md",
            ]
        )


def test_create_parser_accepts_explicit_model_name() -> None:
    args = workspace.parser().parse_args(
        [
            "create",
            "--repo",
            "/repo",
            "--pr-number",
            "5",
            "--commit",
            "deadbeef",
            "--head-branch",
            "fix/model-name",
            "--model-name",
            "opus-5",
        ]
    )

    assert args.model_name == "opus-5"


def create_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    tracked_reviews: bool = True,
) -> dict[str, Any]:
    codex_home = tmp_path / "codex"
    write_rollout(codex_home, ["gpt-5.6-sol"])
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD_ID)
    repo = tmp_path / "repo"
    commit = make_repo(repo, tracked_reviews=tracked_reviews)
    result = workspace.create(
        argparse.Namespace(
            repo=str(repo),
            pr_number=4,
            commit=commit,
            head_branch="fix/herdr-session-cwd",
            model_name=None,
            temp_root=str(tmp_path / "sessions"),
        )
    )
    return {"result": result, "codex_home": codex_home, "repo": repo}


@pytest.fixture
def created_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return create_session(tmp_path, monkeypatch)


def test_save_uses_only_pinned_paths(created_session: dict[str, Any]) -> None:
    result = created_session["result"]
    draft = Path(result["draft"])
    draft.write_text("review\n", encoding="utf-8")

    saved = workspace.save(argparse.Namespace(state=result["state_file"]))

    assert saved["destination"].endswith("/reviews/fix-herdr-session-cwd/gpt-5.6-sol.md")
    assert Path(saved["destination"]).read_text(encoding="utf-8") == "review\n"


def test_save_allows_another_review_destination_to_change(
    created_session: dict[str, Any],
) -> None:
    result = created_session["result"]
    repo = created_session["repo"]
    Path(result["draft"]).write_text("codex review\n", encoding="utf-8")
    other = repo / "reviews/fix-herdr-session-cwd/gemini-3.6-flash.md"
    other.write_text("gemini review\n", encoding="utf-8")

    saved = workspace.save(argparse.Namespace(state=result["state_file"]))

    assert Path(saved["destination"]).read_text(encoding="utf-8") == "codex review\n"
    assert other.read_text(encoding="utf-8") == "gemini review\n"


def test_save_allows_untracked_reviews_directory_to_appear(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = create_session(tmp_path, monkeypatch, tracked_reviews=False)
    result = session["result"]
    repo = session["repo"]
    Path(result["draft"]).write_text("codex review\n", encoding="utf-8")
    other = repo / "reviews" / "fix-herdr-session-cwd" / "gemini.md"
    other.parent.mkdir(parents=True)
    other.write_text("gemini review\n", encoding="utf-8")
    assert git(repo, "status", "--porcelain") == "?? reviews/"

    saved = workspace.save(argparse.Namespace(state=result["state_file"]))

    assert Path(saved["destination"]).read_text(encoding="utf-8") == "codex review\n"
    assert other.read_text(encoding="utf-8") == "gemini review\n"


@pytest.mark.parametrize("collision", ["reviews", "branch"])
def test_save_rejects_non_directory_destination_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collision: str,
) -> None:
    session = create_session(tmp_path, monkeypatch, tracked_reviews=False)
    result = session["result"]
    repo = session["repo"]
    Path(result["draft"]).write_text("review\n", encoding="utf-8")
    if collision == "reviews":
        (repo / "reviews").write_text("collision\n", encoding="utf-8")
    else:
        reviews = repo / "reviews"
        reviews.mkdir()
        (reviews / "fix-herdr-session-cwd").write_text("collision\n", encoding="utf-8")

    with pytest.raises(
        workspace.WorkspaceError,
        match="review destination parent is not a directory",
    ):
        workspace.save(argparse.Namespace(state=result["state_file"]))


def test_save_rejects_changed_pinned_destination(
    created_session: dict[str, Any],
) -> None:
    result = created_session["result"]
    repo = created_session["repo"]
    Path(result["draft"]).write_text("new review\n", encoding="utf-8")
    destination = repo / result["destination"]
    destination.write_text("concurrent review\n", encoding="utf-8")

    with pytest.raises(workspace.WorkspaceError, match="review destination changed"):
        workspace.save(argparse.Namespace(state=result["state_file"]))

    assert destination.read_text(encoding="utf-8") == "concurrent review\n"


def test_first_session_wins_same_destination(
    created_session: dict[str, Any],
) -> None:
    first = created_session["result"]
    repo = created_session["repo"]
    commit = git(repo, "rev-parse", "HEAD")
    second = workspace.create(
        argparse.Namespace(
            repo=str(repo),
            pr_number=4,
            commit=commit,
            head_branch="fix/herdr-session-cwd",
            model_name=None,
            temp_root=str(Path(first["state_file"]).parents[1]),
        )
    )
    Path(first["draft"]).write_text("first review\n", encoding="utf-8")
    Path(second["draft"]).write_text("second review\n", encoding="utf-8")

    workspace.save(argparse.Namespace(state=first["state_file"]))
    with pytest.raises(workspace.WorkspaceError, match="review destination changed"):
        workspace.save(argparse.Namespace(state=second["state_file"]))

    destination = repo / first["destination"]
    assert destination.read_text(encoding="utf-8") == "first review\n"


def test_save_allows_unrelated_main_changes(created_session: dict[str, Any]) -> None:
    result = created_session["result"]
    repo = created_session["repo"]
    Path(result["draft"]).write_text("review\n", encoding="utf-8")
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    scratch = repo / ".pr-review-scratch"
    scratch.mkdir()
    (scratch / "diff.txt").write_text("scratch\n", encoding="utf-8")

    saved = workspace.save(argparse.Namespace(state=result["state_file"]))

    assert Path(saved["destination"]).read_text(encoding="utf-8") == "review\n"


def test_create_state_omits_main_snapshot(created_session: dict[str, Any]) -> None:
    state_file = Path(created_session["result"]["state_file"])

    state = json.loads(state_file.read_text(encoding="utf-8"))

    assert state["version"] == 6
    assert "main_snapshot" not in state


def test_load_state_rejects_previous_version(created_session: dict[str, Any]) -> None:
    state_file = Path(created_session["result"]["state_file"])
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["version"] = 5
    state_file.write_text(json.dumps(state) + "\n", encoding="utf-8")

    with pytest.raises(workspace.WorkspaceError, match="invalid PR-review session state"):
        workspace.load_state(str(state_file))


def test_save_rejects_changed_runtime_model(created_session: dict[str, Any]) -> None:
    result = created_session["result"]
    codex_home = created_session["codex_home"]
    Path(result["draft"]).write_text("review\n", encoding="utf-8")
    write_rollout(codex_home, ["gpt-5.6-sol", "gpt-5"])

    with pytest.raises(workspace.WorkspaceError, match="runtime model changed"):
        workspace.save(argparse.Namespace(state=result["state_file"]))


def test_save_rejects_tampered_destination(created_session: dict[str, Any]) -> None:
    result = created_session["result"]
    state_file = Path(result["state_file"])
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["destination"] = "reviews/fix-herdr-session-cwd/gpt-5.md"
    state_file.write_text(json.dumps(state) + "\n", encoding="utf-8")

    with pytest.raises(workspace.WorkspaceError, match="destination does not match"):
        workspace.save(argparse.Namespace(state=str(state_file)))


def test_save_waits_for_repository_review_lock(
    created_session: dict[str, Any],
) -> None:
    result = created_session["result"]
    repo = created_session["repo"]
    Path(result["draft"]).write_text("review\n", encoding="utf-8")
    destination = repo / result["destination"]

    with workspace.review_save_lock(repo):
        process = subprocess.Popen(
            [sys.executable, str(SCRIPT), "save", "--state", result["state_file"]],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=os.environ.copy(),
        )
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=1)
        assert not destination.exists()

    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 0, stderr
    assert json.loads(stdout)["destination"] == str(destination)
    assert destination.read_text(encoding="utf-8") == "review\n"
