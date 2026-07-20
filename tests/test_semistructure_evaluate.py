"""半構造化の構造評価・検索評価テスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nova_parser.semistructure import main as main_mod
from nova_parser.semistructure.evaluate import (
    GoldQuery,
    evaluate_rankings,
    evaluate_structure,
    load_gold_queries,
    load_gold_segments,
    resolve_gold_segments_path,
)
from nova_parser.semistructure.models import Audience, SourceSpan
from tests.semistructure_factories import make_segment

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "semistructure"
_GOLD_SEGMENTS = _FIXTURE_DIR / "gold-segments.jsonl"
_GOLD_QUERIES = _FIXTURE_DIR / "gold-queries.jsonl"


def test_evaluate_rankings_computes_recall_and_ndcg() -> None:
    """関連文書が2位のとき Recall@k=1、MRR=0.5、0<nDCG@k<1 になる。"""
    queries = [GoldQuery(query_id="q1", relevant_ids=["s2"])]
    ranked = {"q1": ["s1", "s2", "s3"]}
    metrics = evaluate_rankings(queries, ranked, k=3)

    assert metrics.recall_at_k == 1.0
    assert metrics.mrr == 0.5
    assert 0.0 < metrics.ndcg_at_k < 1.0


def test_structure_metrics_count_gm_downgrade_as_critical() -> None:
    """正解が GM で実際が PLAYER のとき重大な audience エラーを数える。"""
    metrics = evaluate_structure(
        gold=[make_segment("s1", Audience.GM)],
        actual=[make_segment("s1", Audience.PLAYER)],
    )
    assert metrics.critical_audience_errors == 1


def test_evaluate_structure_perfect_match_is_one() -> None:
    """同一セグメントなら被覆率と各一致率が 1.0 になる。"""
    gold = [
        make_segment(
            "s1",
            Audience.SHARED,
            content_type="rule.explanation",
            section_path=["章", "節"],
            spans=[SourceSpan(page=22, rect_id="r1", start=0, end=4)],
            raw_text="本文AB",
            normalized_text="本文AB",
        )
    ]
    metrics = evaluate_structure(gold=gold, actual=list(gold))
    assert metrics.source_coverage == 1.0
    assert metrics.boundary_match == 1.0
    assert metrics.content_type_match == 1.0
    assert metrics.audience_match == 1.0
    assert metrics.critical_audience_errors == 0


def test_evaluate_structure_partial_coverage_and_mismatches() -> None:
    """span 不足と content_type / audience 不一致を比率で報告する。"""
    gold = [
        make_segment(
            "s1",
            Audience.SHARED,
            content_type="rule.explanation",
            spans=[SourceSpan(page=22, rect_id="r1", start=0, end=4)],
            raw_text="ABCD",
            normalized_text="ABCD",
        )
    ]
    actual = [
        make_segment(
            "s1",
            Audience.PLAYER,
            content_type="world.setting",
            spans=[SourceSpan(page=22, rect_id="r1", start=0, end=2)],
            raw_text="ABCD",
            normalized_text="AB",
        )
    ]
    metrics = evaluate_structure(gold=gold, actual=actual)
    assert metrics.source_coverage == 0.5
    assert metrics.boundary_match == 0.0
    assert metrics.content_type_match == 0.0
    assert metrics.audience_match == 0.0


def test_evaluate_rankings_averages_multiple_queries() -> None:
    """複数クエリの指標を平均する。"""
    queries = [
        GoldQuery(query_id="q1", relevant_ids=["a"]),
        GoldQuery(query_id="q2", relevant_ids=["x", "y"]),
    ]
    ranked = {
        "q1": ["a", "b"],  # recall=1, mrr=1, ndcg=1
        "q2": ["z", "w"],  # recall=0, mrr=0, ndcg=0
    }
    metrics = evaluate_rankings(queries, ranked, k=2)
    assert metrics.recall_at_k == 0.5
    assert metrics.mrr == 0.5
    assert metrics.ndcg_at_k == 0.5


def test_gold_fixtures_cover_representative_pages_and_query_types() -> None:
    """代表6ページの gold セグメントと10件以上の検索質問がある。"""
    segments = load_gold_segments(_GOLD_SEGMENTS)
    queries = load_gold_queries(_GOLD_QUERIES)

    pages = {span.page for segment in segments for span in segment.source_spans}
    assert {22, 23, 203, 249, 251, 259}.issubset(pages)

    assert len(queries) >= 10
    by_type: dict[str, int] = {}
    for query in queries:
        by_type[query.query_type] = by_type.get(query.query_type, 0) + 1
    for required in ("rule", "world", "character", "scenario", "similar"):
        assert by_type.get(required, 0) >= 2, f"{required} が不足: {by_type}"

    for segment in segments:
        assert segment.source_spans
        assert segment.section_path
        assert segment.content_type
        assert segment.audience


def test_resolve_gold_segments_path_accepts_dir_or_file(tmp_path: Path) -> None:
    """ディレクトリ指定時は gold-segments.jsonl を解決する。"""
    gold_file = tmp_path / "gold-segments.jsonl"
    gold_file.write_text("{}\n", encoding="utf-8")
    assert resolve_gold_segments_path(tmp_path) == gold_file
    assert resolve_gold_segments_path(gold_file) == gold_file


def test_main_evaluate_gold_prints_structure_metrics(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--evaluate-gold は pipeline を走らせず構造メトリクスを表示する。"""
    gold = make_segment("s1", Audience.GM)
    actual = make_segment("s1", Audience.PLAYER)
    gold_path = tmp_path / "gold-segments.jsonl"
    gold_path.write_text(gold.model_dump_json(ensure_ascii=False) + "\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "segments.jsonl").write_text(
        actual.model_dump_json(ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    main_mod.main(
        [
            "--output-dir",
            str(output_dir),
            "--evaluate-gold",
            str(gold_path),
        ]
    )

    out = capsys.readouterr().out
    assert "critical_audience_errors=1" in out
    assert "source_coverage=" in out
    assert "boundary_match=" in out
    assert "content_type_match=" in out
    assert "audience_match=" in out


def test_gold_fixture_jsonl_is_parseable() -> None:
    """fixture の各行が JSON としてパースできる。"""
    for path in (_GOLD_SEGMENTS, _GOLD_QUERIES):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                json.loads(line)
