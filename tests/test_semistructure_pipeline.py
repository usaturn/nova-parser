"""再実行可能な半構造化パイプラインのテスト。"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from nova_parser.semistructure.models import (
    Audience,
    AudienceOverride,
    NormalizedBlock,
    ReviewDecision,
    ReviewStatus,
    SemanticSegment,
    StructureProposal,
    StructureWindow,
)
from nova_parser.semistructure.pipeline import run_pipeline
from nova_parser.semistructure.storage import read_jsonl, resolve_segment_input_hash, write_jsonl_atomic
from tests.semistructure_factories import (
    FakeClassifier,
    make_config,
    make_manifest,
    make_proposal,
    write_region_fixture,
)


class _AudiencePreservingClassifier(FakeClassifier):
    """ブロックの inherited_audience を提案 audience に反映する分類器。"""

    def classify(self, window: StructureWindow) -> StructureProposal:
        if self._fail_page is not None and window.center_page == self._fail_page:
            raise RuntimeError("classifier failure")
        blocks = [block for block in window.context_blocks if block.block_id in window.allowed_block_ids]
        audience = _fail_closed_audience(blocks)
        return make_proposal(
            block_ids=window.allowed_block_ids,
            segment={"audience": audience},
        )


def _fail_closed_audience(blocks: Sequence[NormalizedBlock]) -> Audience:
    audiences = [block.inherited_audience for block in blocks]
    if any(audience == Audience.GM for audience in audiences):
        return Audience.GM
    if any(audience == Audience.UNKNOWN for audience in audiences):
        return Audience.UNKNOWN
    unique = set(audiences)
    if len(unique) == 1:
        return audiences[0]
    return Audience.SHARED


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


def test_pipeline_no_cache_reclassifies_even_when_cache_exists(tmp_path: Path) -> None:
    """no_cache=True のときは既存キャッシュを読まず classify を再実行する。"""
    _setup_two_page_workspace(tmp_path)
    run_pipeline(make_config(tmp_path), classifier=FakeClassifier.valid())
    assert any((tmp_path / "out" / ".cache").iterdir())

    # キャッシュがあれば page 22 は成功するはずだが、no_cache なら失敗に到達する
    report = run_pipeline(
        make_config(tmp_path, no_cache=True),
        classifier=FakeClassifier.fail_on_page(22),
    )
    assert 22 in report.failed_pages


def test_pipeline_excludes_gm_from_player_views_without_forcing_required(tmp_path: Path) -> None:
    """正当な GM は正本に残り player 派生から除外され、可視性理由だけで REQUIRED にしない。"""
    _setup_two_page_workspace(tmp_path)
    run_pipeline(make_config(tmp_path), classifier=_AudiencePreservingClassifier.valid())

    segments = read_jsonl(tmp_path / "out/segments.jsonl", SemanticSegment)
    gm_segments = [segment for segment in segments if segment.audience == Audience.GM]
    assert gm_segments, "manifest の GM 範囲から GM セグメントが生成される想定"
    for segment in gm_segments:
        reasons = segment.processing.get("review_reasons", "")
        assert "gm_audience_visible" not in reasons
        assert "audience_downgrade_candidate" not in reasons
        assert segment.review_status == ReviewStatus.NOT_REQUIRED

    # 派生は player モードのため GM は載らない
    retrieval = (tmp_path / "out/derived/retrieval-inputs.jsonl").read_text(encoding="utf-8")
    for segment in gm_segments:
        assert segment.segment_id not in retrieval


def test_pipeline_keeps_approved_gm_on_rerun(tmp_path: Path) -> None:
    """APPROVED 済みの正当な GM は再実行しても APPROVED のまま残る。"""
    _setup_two_page_workspace(tmp_path)
    classifier = _AudiencePreservingClassifier.valid()
    run_pipeline(make_config(tmp_path), classifier=classifier)
    segments = read_jsonl(tmp_path / "out/segments.jsonl", SemanticSegment)
    gm = next(segment for segment in segments if segment.audience == Audience.GM)

    decisions_path = tmp_path / "out/review/decisions.jsonl"
    write_jsonl_atomic(
        decisions_path,
        [
            ReviewDecision(
                review_id=f"{gm.book_id}:{gm.segment_id}",
                segment_id=gm.segment_id,
                status=ReviewStatus.APPROVED,
                input_hash=resolve_segment_input_hash(gm),
                processing_version="test-v1",
                decided_by="tester",
                comment="正当な GM シナリオ",
            )
        ],
    )

    run_pipeline(
        make_config(tmp_path, review_decisions=decisions_path),
        classifier=_AudiencePreservingClassifier.valid(),
    )
    rerun = read_jsonl(tmp_path / "out/segments.jsonl", SemanticSegment)
    approved = next(segment for segment in rerun if segment.segment_id == gm.segment_id)
    assert approved.audience == Audience.GM
    assert approved.review_status == ReviewStatus.APPROVED
    assert "gm_audience_visible" not in approved.processing.get("review_reasons", "")

    retrieval = (tmp_path / "out/derived/retrieval-inputs.jsonl").read_text(encoding="utf-8")
    assert approved.segment_id not in retrieval
