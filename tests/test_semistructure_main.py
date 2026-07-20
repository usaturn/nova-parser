"""半構造化 CLI のテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from nova_parser.semistructure import main as main_mod
from nova_parser.semistructure.models import EmbeddingInput, SemanticSegment
from nova_parser.semistructure.storage import read_jsonl
from tests.semistructure_factories import FakeClassifier, make_manifest, write_region_fixture


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


def test_main_dry_run_with_evaluate_gold_uses_existing_segments(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--dry-run + --evaluate-gold は既存 segments.jsonl があれば評価する。"""
    from nova_parser.semistructure.models import Audience
    from tests.semistructure_factories import make_segment

    manifest_path, input_dir, output_dir = _setup_cli_workspace(tmp_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    gold = make_segment("s1", Audience.GM)
    actual = make_segment("s1", Audience.PLAYER)
    gold_path = tmp_path / "gold-segments.jsonl"
    gold_path.write_text(gold.model_dump_json(ensure_ascii=False) + "\n", encoding="utf-8")
    (output_dir / "segments.jsonl").write_text(
        actual.model_dump_json(ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    main_mod.main(
        [
            "--manifest",
            str(manifest_path),
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--dry-run",
            "--evaluate-gold",
            str(gold_path),
        ]
    )

    captured = capsys.readouterr()
    assert "pages=2" in captured.out
    assert "critical_audience_errors=1" in captured.out
    assert "source_coverage=" in captured.out


def test_main_dry_run_with_evaluate_gold_without_segments_prints_message(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--dry-run + --evaluate-gold で segments.jsonl が無いときは明確なメッセージを出す。"""
    from nova_parser.semistructure.models import Audience
    from tests.semistructure_factories import make_segment

    manifest_path, input_dir, output_dir = _setup_cli_workspace(tmp_path)
    gold = make_segment("s1", Audience.GM)
    gold_path = tmp_path / "gold-segments.jsonl"
    gold_path.write_text(gold.model_dump_json(ensure_ascii=False) + "\n", encoding="utf-8")

    main_mod.main(
        [
            "--manifest",
            str(manifest_path),
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--dry-run",
            "--evaluate-gold",
            str(gold_path),
        ]
    )

    captured = capsys.readouterr()
    assert "pages=2" in captured.out
    assert "evaluate-gold" in captured.err
    assert "segments.jsonl" in captured.err


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

    exit_code = main_mod.main(
        [
            "--manifest",
            str(manifest_path),
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code != 0
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
            review_required = 0
            segments = 0
            source_coverage = 1.0
            validation_errors = 0
            dry_run = False

        return _Report()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(main_mod, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(main_mod, "ensure_backend_available", lambda: None)
    monkeypatch.setattr(main_mod, "build_classifier", lambda _config: object())

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


def test_cli_end_to_end_with_fake_classifier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """FakeClassifier で CLI 全体を通し、正本と派生ビューが出力される。"""
    monkeypatch.setattr(main_mod, "build_classifier", lambda _: FakeClassifier.valid())
    fixture_dir = Path(__file__).parent / "fixtures" / "semistructure"
    exit_code = main_mod.main(
        [
            "--manifest",
            str(fixture_dir / "manifest.json"),
            "--input-dir",
            str(fixture_dir),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 0
    assert read_jsonl(tmp_path / "out/segments.jsonl", SemanticSegment)
    assert read_jsonl(tmp_path / "out/derived/retrieval-inputs.jsonl", EmbeddingInput)
    assert read_jsonl(tmp_path / "out/derived/topic-inputs.jsonl", EmbeddingInput)
