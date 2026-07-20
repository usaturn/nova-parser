"""半構造化の構造評価と検索ランキング評価（純 Python）。"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from nova_parser.semistructure.models import Audience, SemanticSegment, SourceSpan
from nova_parser.semistructure.storage import read_jsonl

# GM 情報が player / shared へ落ちる重大誤りとして数える降格先
_CRITICAL_DOWNGRADE_TARGETS = frozenset({Audience.PLAYER, Audience.SHARED})


@dataclass(frozen=True)
class StructureMetrics:
    """正本セグメントと正解の構造比較結果。"""

    source_coverage: float
    boundary_match: float
    content_type_match: float
    audience_match: float
    critical_audience_errors: int


@dataclass(frozen=True)
class RetrievalMetrics:
    """検索ランキング評価の平均指標。"""

    recall_at_k: float
    mrr: float
    ndcg_at_k: float


class GoldQuery(BaseModel):
    """正解関連セグメント付きの検索質問。"""

    query_id: str = Field(min_length=1)
    text: str = ""
    relevant_ids: list[str] = Field(min_length=1)
    query_type: str = Field(default="", min_length=0)


def evaluate_structure(
    gold: Sequence[SemanticSegment],
    actual: Sequence[SemanticSegment],
) -> StructureMetrics:
    """正解セグメントと実際の正本を比較して構造メトリクスを返す。

    - セグメントは可能な限り `segment_id` で対応付ける
    - 原文被覆率は gold の source span 文字集合に対する actual の被覆割合
    - 境界一致は同一 segment_id で source_spans 集合が完全一致する割合
    - content_type / audience 一致は対応 actual が同値である gold の割合
    - critical_audience_errors は gold=GM かつ actual が player/shared の件数
    """
    if not gold:
        return StructureMetrics(
            source_coverage=1.0,
            boundary_match=1.0,
            content_type_match=1.0,
            audience_match=1.0,
            critical_audience_errors=0,
        )

    actual_by_id = {segment.segment_id: segment for segment in actual}
    gold_chars = _char_set_from_segments(gold)
    actual_chars = _char_set_from_segments(actual)
    if gold_chars:
        source_coverage = len(gold_chars & actual_chars) / len(gold_chars)
    else:
        source_coverage = 1.0

    total = len(gold)
    boundary_hits = 0
    content_type_hits = 0
    audience_hits = 0
    critical_errors = 0

    for gold_segment in gold:
        actual_segment = actual_by_id.get(gold_segment.segment_id)
        if actual_segment is None:
            continue
        if _span_key_set(gold_segment.source_spans) == _span_key_set(actual_segment.source_spans):
            boundary_hits += 1
        if gold_segment.content_type == actual_segment.content_type:
            content_type_hits += 1
        if gold_segment.audience == actual_segment.audience:
            audience_hits += 1
        if gold_segment.audience == Audience.GM and actual_segment.audience in _CRITICAL_DOWNGRADE_TARGETS:
            critical_errors += 1

    return StructureMetrics(
        source_coverage=source_coverage,
        boundary_match=boundary_hits / total,
        content_type_match=content_type_hits / total,
        audience_match=audience_hits / total,
        critical_audience_errors=critical_errors,
    )


def evaluate_rankings(
    queries: Sequence[GoldQuery],
    ranked_ids: Mapping[str, Sequence[str]],
    k: int = 10,
) -> RetrievalMetrics:
    """クエリごとの順位リストから Recall@k / MRR / nDCG@k の平均を返す。"""
    if not queries:
        return RetrievalMetrics(recall_at_k=0.0, mrr=0.0, ndcg_at_k=0.0)
    if k < 1:
        raise ValueError("k は 1 以上である必要があります")

    recalls: list[float] = []
    rrs: list[float] = []
    ndcgs: list[float] = []

    for query in queries:
        ranked = list(ranked_ids.get(query.query_id, ()))[:k]
        relevant = set(query.relevant_ids)
        if not relevant:
            recalls.append(0.0)
            rrs.append(0.0)
            ndcgs.append(0.0)
            continue

        hits = [doc_id for doc_id in ranked if doc_id in relevant]
        recalls.append(len(hits) / len(relevant))
        rrs.append(_reciprocal_rank(ranked, relevant))
        ndcgs.append(_ndcg_at_k(ranked, relevant, k=k))

    n = len(queries)
    return RetrievalMetrics(
        recall_at_k=sum(recalls) / n,
        mrr=sum(rrs) / n,
        ndcg_at_k=sum(ndcgs) / n,
    )


def load_gold_segments(path: Path) -> list[SemanticSegment]:
    """正解セグメント JSONL を読み込む。"""
    return read_jsonl(Path(path), SemanticSegment)


def load_gold_queries(path: Path) -> list[GoldQuery]:
    """正解クエリ JSONL を読み込む。"""
    return read_jsonl(Path(path), GoldQuery)


def resolve_gold_segments_path(path: Path) -> Path:
    """ファイルまたはディレクトリから gold-segments.jsonl を解決する。"""
    path = Path(path)
    if path.is_dir():
        candidate = path / "gold-segments.jsonl"
        if not candidate.is_file():
            raise FileNotFoundError(f"gold-segments.jsonl が見つかりません: {path}")
        return candidate
    if not path.is_file():
        raise FileNotFoundError(f"gold パスが存在しません: {path}")
    return path


def format_structure_metrics(metrics: StructureMetrics) -> str:
    """CLI 表示用に構造メトリクスを整形する。"""
    return "\n".join(
        [
            f"source_coverage={metrics.source_coverage:.4f}",
            f"boundary_match={metrics.boundary_match:.4f}",
            f"content_type_match={metrics.content_type_match:.4f}",
            f"audience_match={metrics.audience_match:.4f}",
            f"critical_audience_errors={metrics.critical_audience_errors}",
        ]
    )


def evaluate_gold_against_output(gold_path: Path, output_dir: Path) -> StructureMetrics:
    """gold パスと output_dir/segments.jsonl を比較する。"""
    resolved = resolve_gold_segments_path(gold_path)
    actual_path = Path(output_dir) / "segments.jsonl"
    if not actual_path.is_file():
        raise FileNotFoundError(f"評価対象の segments.jsonl がありません: {actual_path}")
    gold = load_gold_segments(resolved)
    actual = read_jsonl(actual_path, SemanticSegment)
    return evaluate_structure(gold, actual)


def _char_set_from_segments(segments: Sequence[SemanticSegment]) -> set[tuple[int, str, int]]:
    """セグメント群の source_spans を (page, rect_id, offset) 集合へ展開する。"""
    chars: set[tuple[int, str, int]] = set()
    for segment in segments:
        for span in segment.source_spans:
            for offset in range(span.start, span.end):
                chars.add((span.page, span.rect_id, offset))
    return chars


def _span_key_set(spans: Sequence[SourceSpan]) -> set[tuple[int, str, int, int]]:
    """境界比較用に span をタプル集合へ正規化する。"""
    return {(span.page, span.rect_id, span.start, span.end) for span in spans}


def _reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float:
    """最初の関連文書の逆順位。無ければ 0。"""
    for index, doc_id in enumerate(ranked, start=1):
        if doc_id in relevant:
            return 1.0 / index
    return 0.0


def _ndcg_at_k(ranked: Sequence[str], relevant: set[str], *, k: int) -> float:
    """二値関連度の nDCG@k。"""
    gains = [1.0 if doc_id in relevant else 0.0 for doc_id in ranked[:k]]
    # 不足分は 0 で埋める（上位 k 件）
    if len(gains) < k:
        gains.extend([0.0] * (k - len(gains)))
    dcg = _dcg(gains)
    ideal_hits = min(len(relevant), k)
    ideal = [1.0] * ideal_hits + [0.0] * (k - ideal_hits)
    idcg = _dcg(ideal)
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def _dcg(gains: Sequence[float]) -> float:
    """1-indexed rank の DCG（割引は log2(rank+1)）。"""
    total = 0.0
    for index, gain in enumerate(gains):
        if gain == 0.0:
            continue
        # rank = index + 1 → log2(rank + 1) = log2(index + 2)
        total += gain / math.log2(index + 2)
    return total
