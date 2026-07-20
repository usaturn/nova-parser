"""ステージ実行・ページ単位キャッシュ・部分失敗を統合する半構造化パイプライン。"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from nova_parser.semistructure.input import load_pages
from nova_parser.semistructure.llm import PROMPT_CONTRACT_VERSION, StructureClassifier, build_structure_windows
from nova_parser.semistructure.manifest import load_manifest
from nova_parser.semistructure.models import (
    EmbeddingInput,
    NormalizedBlock,
    PipelineConfig,
    ReviewItem,
    ReviewStatus,
    SemanticSegment,
    StructureProposal,
    StructureWindow,
)
from nova_parser.semistructure.normalize import normalize_pages
from nova_parser.semistructure.review import build_review_items, render_review_markdown
from nova_parser.semistructure.segment import assemble_segments, fallback_segment
from nova_parser.semistructure.storage import (
    apply_review_decisions,
    load_review_decisions,
    write_jsonl_atomic,
    write_text_atomic,
)
from nova_parser.semistructure.validate import ValidationError, validate_corpus, validate_player_visibility
from nova_parser.semistructure.views import build_views

# 正規化規則バージョン（キャッシュキー構成要素）
NORMALIZE_RULE_VERSION = "ja-word-wrap-v1"
CLASSIFIER_FAILURE_REASON = "classifier_failure"


@dataclass(slots=True)
class PipelineReport:
    """パイプライン実行結果の集約。"""

    pages: int = 0
    regions: int = 0
    failed_pages: list[int] = field(default_factory=list)
    llm_calls: int = 0
    input_errors: int = 0
    review_candidates: int = 0
    review_required: int = 0
    segments: int = 0
    source_coverage: float = 1.0
    validation_errors: int = 0
    dry_run: bool = False


def run_pipeline(
    config: PipelineConfig,
    classifier: StructureClassifier | None = None,
) -> PipelineReport:
    """マニフェストから派生ビューまでを固定ステージ順で実行する。

    Parameters
    ----------
    config:
        入出力パスと dry-run / no-cache フラグ。
    classifier:
        構造分類器。`config.dry_run` のときは不要（None 可）。

    Notes
    -----
    - ページ単位の分類失敗は書籍全体を中断せず unknown フォールバックにする。
    - `--no-cache` はキャッシュ読み取りのみ無効化し、正本の原文検証は常に行う。
    - dry-run は入力検査と決定的正規化までで停止し、出力を書かない。
    """
    manifest = load_manifest(config.manifest_path)
    pages = load_pages(config.input_dir, manifest)
    blocks = normalize_pages(pages)

    report = PipelineReport(
        pages=len(pages),
        regions=sum(len(page.regions) for page in pages),
        input_errors=0,
        dry_run=config.dry_run,
        review_candidates=sum(1 for block in blocks if block.review_reasons),
    )

    if config.dry_run:
        report.llm_calls = 0
        return report

    if classifier is None:
        raise ValueError("通常実行には StructureClassifier が必要です")

    manifest_sha = _file_sha256(config.manifest_path)
    cache_dir = config.output_dir / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    outline = classifier.infer_outline(blocks)
    report.llm_calls += 1

    windows = build_structure_windows(blocks, outline=outline)
    blocks_by_page: dict[int, list[NormalizedBlock]] = {}
    for block in blocks:
        blocks_by_page.setdefault(block.page, []).append(block)

    segments: list[SemanticSegment] = []
    failed_pages: list[int] = []

    for window in windows:
        page_blocks = blocks_by_page.get(window.center_page, [])
        if not page_blocks:
            continue
        cache_key = _cache_key(
            context_digest=_context_digest(window),
            manifest_sha=manifest_sha,
            model_id=classifier.classifier_id,
            schema_version=manifest.schema_version,
        )
        cache_path = cache_dir / f"{window.center_page}-{cache_key}.json"

        try:
            proposal, used_cache = _load_or_classify(
                window=window,
                classifier=classifier,
                cache_path=cache_path,
                no_cache=config.no_cache,
            )
            if not used_cache:
                report.llm_calls += 1
            page_segments = assemble_segments(page_blocks, proposal, manifest)
        except Exception:
            failed_pages.append(window.center_page)
            page_segments = [
                fallback_segment(
                    block,
                    CLASSIFIER_FAILURE_REASON,
                    document_type=manifest.default_document_type,
                    classifier_id=classifier.classifier_id,
                    prompt_contract_version=PROMPT_CONTRACT_VERSION,
                )
                for block in page_blocks
            ]
        segments.extend(page_segments)

    if config.review_decisions is not None and config.review_decisions.is_file():
        decisions = load_review_decisions(config.review_decisions)
        segments = apply_review_decisions(segments, decisions)

    corpus_report = validate_corpus(pages, segments)
    segments = _apply_validation_to_segments(segments, corpus_report.errors)

    # プレイヤー安全性の一次防御は build_views(audience_mode="player")。
    # 可視性検証は派生に実際に載った集合だけにかけ、正当な GM を REQUIRED に戻さない。
    # フィルタ不具合で gm/unknown が混入した場合のみレビューキューへ回す（exit 4 にはしない）。
    book_titles = {manifest.book_id: manifest.title}
    view_source = _exclude_rejected(segments)
    player_views = build_views(
        view_source,
        audience_mode="player",
        book_titles=book_titles,
    )
    exported_ids = {item.segment_id for item in player_views.retrieval}
    exported_segments = [segment for segment in view_source if segment.segment_id in exported_ids]
    visibility = validate_player_visibility(exported_segments)
    if not visibility.ok:
        segments = _apply_validation_to_segments(segments, visibility.errors)
        view_source = _exclude_rejected(segments)
        player_views = build_views(
            view_source,
            audience_mode="player",
            book_titles=book_titles,
        )

    review_items = build_review_items(segments, pages=pages)
    _write_outputs(
        config.output_dir,
        segments=segments,
        review_items=review_items,
        retrieval=player_views.retrieval,
        topic=player_views.topic,
    )

    report.failed_pages = failed_pages
    report.segments = len(segments)
    report.review_candidates = len(review_items)
    report.review_required = len(review_items)
    report.source_coverage = corpus_report.coverage_ratio
    report.validation_errors = len(corpus_report.errors)
    return report


def _exclude_rejected(segments: Sequence[SemanticSegment]) -> list[SemanticSegment]:
    """REJECTED セグメントを派生対象から外す。"""
    return [segment for segment in segments if segment.review_status != ReviewStatus.REJECTED]


def _write_outputs(
    output_dir: Path,
    *,
    segments: Sequence[SemanticSegment],
    review_items: Sequence[ReviewItem],
    retrieval: Sequence[EmbeddingInput],
    topic: Sequence[EmbeddingInput],
) -> None:
    """正本・レビュー・派生ビューを所定レイアウトへ書き出す。"""
    write_jsonl_atomic(output_dir / "segments.jsonl", segments)
    write_jsonl_atomic(output_dir / "review" / "queue.jsonl", review_items)
    write_text_atomic(output_dir / "review" / "pending.md", render_review_markdown(review_items))
    write_jsonl_atomic(output_dir / "derived" / "retrieval-inputs.jsonl", retrieval)
    write_jsonl_atomic(output_dir / "derived" / "topic-inputs.jsonl", topic)


def _load_or_classify(
    *,
    window: StructureWindow,
    classifier: StructureClassifier,
    cache_path: Path,
    no_cache: bool,
) -> tuple[StructureProposal, bool]:
    """キャッシュがあれば読み、なければ classify して保存する。"""
    if not no_cache and cache_path.is_file():
        proposal = StructureProposal.model_validate_json(cache_path.read_text(encoding="utf-8"))
        return proposal, True

    proposal = classifier.classify(window)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(proposal.model_dump_json(ensure_ascii=False), encoding="utf-8")
    return proposal, False


def _context_digest(window: StructureWindow) -> str:
    """窓の全文脈ブロックとアウトラインから決定的ダイジェストを算出する。"""
    parts: list[str] = []
    for block in window.context_blocks:
        parts.append(f"{block.block_id}|{block.normalized_text}|{block.inherited_audience}")
    if window.outline is not None:
        parts.append(window.outline.model_dump_json())
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _cache_key(
    *,
    context_digest: str,
    manifest_sha: str,
    model_id: str,
    schema_version: int,
) -> str:
    """ページ単位キャッシュキーを SHA-256 で算出する。"""
    payload = "|".join(
        [
            context_digest,
            f"sha256:{manifest_sha}" if not manifest_sha.startswith("sha256:") else manifest_sha,
            NORMALIZE_RULE_VERSION,
            PROMPT_CONTRACT_VERSION,
            model_id,
            str(schema_version),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    """ファイル内容の SHA-256 十六進を返す。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _apply_validation_to_segments(
    segments: Sequence[SemanticSegment],
    errors: Sequence[ValidationError],
) -> list[SemanticSegment]:
    """検証エラーを該当セグメントの review 理由へ反映する。"""
    reasons_by_id: dict[str, list[str]] = {}
    for error in errors:
        if not error.segment_id:
            continue
        reasons_by_id.setdefault(error.segment_id, []).append(error.code)

    if not reasons_by_id:
        return list(segments)

    updated: list[SemanticSegment] = []
    for segment in segments:
        codes = reasons_by_id.get(segment.segment_id)
        if not codes:
            updated.append(segment)
            continue
        processing = dict(segment.processing)
        existing = [part for part in processing.get("review_reasons", "").split(",") if part]
        for code in codes:
            if code not in existing:
                existing.append(code)
        processing["review_reasons"] = ",".join(existing)
        updated.append(
            segment.model_copy(
                update={
                    "review_status": ReviewStatus.REQUIRED,
                    "processing": processing,
                }
            )
        )
    return updated
