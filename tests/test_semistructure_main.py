"""半構造化 CLI のテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from nova_parser.semistructure import main as main_mod
from tests.semistructure_factories import make_manifest, write_region_fixture


def _setup_cli_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    """CLI 用の manifest / input / output パスを用意する。"""
    manifest = make_manifest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    input_dir = tmp_path / "input"
    write_region_fixture(input_dir / "p022.regions.json", image_name="p022.png", text="本文")
    write_region_fixture(input_dir / "p234.regions.json", image_name="p234.png", text="本文")
    output_dir = tmp_path / "out"
    return manifest_path, input_dir, output_dir


def test_main_dry_run_prints_counts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--dry-run は件数を表示し、正本を書かない。"""
    manifest_path, input_dir, output_dir = _setup_cli_workspace(tmp_path)

    main_mod.main(
        [
            "--manifest",
            str(manifest_path),
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ]
    )

    captured = capsys.readouterr().out
    assert "pages=2" in captured
    assert "regions=2" in captured
    assert "llm_calls=0" in captured
    assert "input_errors=0" in captured
    assert not (output_dir / "segments.jsonl").exists()


def test_main_without_api_key_does_not_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API キー無しの通常実行は BackendUnavailableError 相当で止まり正本を上書きしない。"""
    from nova_parser import gemini_backend

    manifest_path, input_dir, output_dir = _setup_cli_workspace(tmp_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    sentinel = output_dir / "segments.jsonl"
    sentinel.write_text('{"sentinel": true}\n', encoding="utf-8")
    original = sentinel.read_text(encoding="utf-8")

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("VERTEX_AI_API_KEY", raising=False)
    # dotenv 経由で復活しないよう空を強制
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("VERTEX_AI_API_KEY", "")
    # 先行テストで初期化された backend 状態を捨て、空キーで再評価させる
    gemini_backend.reset_for_tests()

    with pytest.raises(SystemExit) as exc_info:
        main_mod.main(
            [
                "--manifest",
                str(manifest_path),
                "--input-dir",
                str(input_dir),
                "--output-dir",
                str(output_dir),
            ]
        )

    assert exc_info.value.code != 0
    assert sentinel.read_text(encoding="utf-8") == original
    gemini_backend.reset_for_tests()


def test_main_wires_review_decisions_and_no_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI 引数が PipelineConfig へ渡ることを確認する。"""
    manifest_path, input_dir, output_dir = _setup_cli_workspace(tmp_path)
    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text("", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run_pipeline(config, classifier=None):  # type: ignore[no-untyped-def]
        captured["config"] = config
        captured["classifier"] = classifier

        class _Report:
            pages = 2
            regions = 2
            llm_calls = 0
            input_errors = 0
            failed_pages: list[int] = []
            review_candidates = 0
            segments = 0
            dry_run = False

        return _Report()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(main_mod, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(main_mod, "ensure_backend_available", lambda: None)
    monkeypatch.setattr(
        main_mod,
        "GeminiStructureClassifier",
        lambda **kwargs: object(),
    )

    main_mod.main(
        [
            "--manifest",
            str(manifest_path),
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--review-decisions",
            str(decisions),
            "--no-cache",
        ]
    )

    config = captured["config"]
    assert config.manifest_path == manifest_path
    assert config.input_dir == input_dir
    assert config.output_dir == output_dir
    assert config.review_decisions == decisions
    assert config.no_cache is True
    assert config.dry_run is False
    assert captured["classifier"] is not None
