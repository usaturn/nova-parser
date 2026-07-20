"""再実行可能な半構造化パイプラインのテスト。"""

from __future__ import annotations

from pathlib import Path

from nova_parser.semistructure.models import Audience, AudienceOverride, SemanticSegment
from nova_parser.semistructure.pipeline import run_pipeline
from nova_parser.semistructure.storage import read_jsonl
from tests.semistructure_factories import (
    FakeClassifier,
    make_config,
    make_manifest,
    write_region_fixture,
)


def _setup_two_page_workspace(tmp_path: Path) -> Path:
    """manifest + 2ページの regions.json を make_config の既定配置へ用意する。"""
    manifest = make_manifest(
        audience_overrides=[
            AudienceOverride(start_page=170, end_page=259, audience=Audience.GM),
        ],
    )
    (tmp_path / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    input_dir = tmp_path / "input"
    write_region_fixture(input_dir / "p022.regions.json", image_name="p022.png", text="ページ22の本文")
    write_region_fixture(input_dir / "p234.regions.json", image_name="p234.png", text="ページ234の本文")
    return tmp_path


def test_pipeline_writes_canonical_review_and_views(tmp_path: Path) -> None:
    """正本・レビュー Markdown・派生ビューを所定パスへ書き出す。"""
    _setup_two_page_workspace(tmp_path)
    report = run_pipeline(make_config(tmp_path), classifier=FakeClassifier.valid())

    assert report.pages == 2
    assert (tmp_path / "out/segments.jsonl").is_file()
    assert (tmp_path / "out/review/pending.md").is_file()
    assert (tmp_path / "out/derived/retrieval-inputs.jsonl").is_file()
    assert (tmp_path / "out/derived/topic-inputs.jsonl").is_file()


def test_pipeline_falls_back_when_one_page_classifier_fails(tmp_path: Path) -> None:
    """1ページの分類失敗は全体中断せず unknown フォールバックにする。"""
    _setup_two_page_workspace(tmp_path)
    report = run_pipeline(
        make_config(tmp_path),
        classifier=FakeClassifier.fail_on_page(234),
    )
    assert report.failed_pages == [234]
    assert (
        read_jsonl(
            tmp_path / "out/segments.jsonl",
            SemanticSegment,
        )[-1].content_type
        == "unknown"
    )


def test_pipeline_dry_run_skips_llm_and_writes_nothing(tmp_path: Path) -> None:
    """dry-run は正規化までで止まり、LLM も正本出力もしない。"""
    _setup_two_page_workspace(tmp_path)
    config = make_config(tmp_path, dry_run=True)
    report = run_pipeline(config, classifier=FakeClassifier.valid())

    assert report.pages == 2
    assert report.regions == 2
    assert report.llm_calls == 0
    assert report.input_errors == 0
    assert not (tmp_path / "out/segments.jsonl").exists()


def test_pipeline_uses_page_cache_on_second_run(tmp_path: Path) -> None:
    """2回目実行ではキャッシュを使い classify 呼び出しを減らす。"""
    _setup_two_page_workspace(tmp_path)
    classifier = FakeClassifier.valid()
    first = run_pipeline(make_config(tmp_path), classifier=classifier)
    assert first.llm_calls >= 1

    second_classifier = FakeClassifier.fail_on_page(22)
    # キャッシュが効いていれば page 22 の classify 失敗に到達しない
    second = run_pipeline(make_config(tmp_path), classifier=second_classifier)
    assert second.failed_pages == []
    assert (tmp_path / "out" / ".cache").is_dir()
    assert any((tmp_path / "out" / ".cache").iterdir())
