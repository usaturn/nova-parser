"""LLM提案から正本セグメントを決定的に組み立てる。"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from nova_parser.semistructure.models import (
    Audience,
    BookManifest,
    DocumentType,
    NormalizedBlock,
    ProposalSegment,
    ReviewStatus,
    SemanticSegment,
    SourceSpan,
    StructureProposal,
)

_TEXT_JOIN = "\n\n"


def assemble_segments(
    blocks: Sequence[NormalizedBlock],
    proposal: StructureProposal,
    manifest: BookManifest,
) -> list[SemanticSegment]:
    """提案の参照IDから正規化ブロックを合成し、正本セグメント一覧を返す。

    未知ID・重複参照・飛び越し（非連続）は提案全体を破棄せず、該当ブロックだけを
    unknown fallback にする。本文合成は常に source 順で行う。
    """
    blocks_by_id = {block.block_id: block for block in blocks}
    source_ordered = sorted(blocks, key=_source_key)
    source_index = {block.block_id: index for index, block in enumerate(source_ordered)}

    claimed: set[str] = set()
    fallback_reasons: dict[str, str] = {}
    assembled_by_first_block: dict[str, SemanticSegment] = {}

    for proposal_segment in proposal.segments:
        failure = _validate_proposal_segment(
            proposal_segment.block_ids,
            blocks_by_id=blocks_by_id,
            source_index=source_index,
            claimed=claimed,
        )
        if failure is not None:
            for block_id in proposal_segment.block_ids:
                if block_id in blocks_by_id and block_id not in claimed:
                    fallback_reasons.setdefault(block_id, failure)
            continue

        ordered = sorted(
            (blocks_by_id[block_id] for block_id in proposal_segment.block_ids),
            key=_source_key,
        )
        for block in ordered:
            claimed.add(block.block_id)

        segment = _compose_segment(
            ordered,
            proposal_segment=proposal_segment,
            proposal=proposal,
            manifest=manifest,
        )
        assembled_by_first_block[ordered[0].block_id] = segment

    results: list[SemanticSegment] = []
    for block in source_ordered:
        if block.block_id in assembled_by_first_block:
            results.append(assembled_by_first_block[block.block_id])
            continue
        if block.block_id in claimed:
            continue
        reason = fallback_reasons.get(block.block_id, "unreferenced_block")
        results.append(
            fallback_segment(
                block,
                reason,
                document_type=manifest.default_document_type,
                classifier_id=proposal.classifier_id,
                prompt_contract_version=proposal.prompt_contract_version,
                input_sha256=proposal.input_sha256,
            )
        )
    return results


def fallback_segment(
    block: NormalizedBlock,
    reason: str,
    *,
    document_type: DocumentType = DocumentType.UNKNOWN,
    classifier_id: str = "",
    prompt_contract_version: str = "",
    input_sha256: str = "",
) -> SemanticSegment:
    """1ブロックを原文保持の unknown セグメントへ落とす。"""
    reasons = list(block.review_reasons)
    if reason and reason not in reasons:
        reasons.append(reason)

    processing: dict[str, str] = {}
    if classifier_id:
        processing["classifier_id"] = classifier_id
    if prompt_contract_version:
        processing["prompt_contract_version"] = prompt_contract_version
    if input_sha256:
        processing["input_sha256"] = input_sha256
    if reasons:
        processing["review_reasons"] = ",".join(reasons)

    return SemanticSegment(
        segment_id=_segment_id(
            block.book_id,
            [block.block_id],
            "unknown",
            [],
        ),
        parent_segment_id=None,
        book_id=block.book_id,
        document_type=document_type,
        section_path=[],
        content_type="unknown",
        audience=block.inherited_audience,
        inherited_audience=block.inherited_audience,
        source_spans=list(block.source_spans),
        raw_text=block.raw_text,
        normalized_text=block.normalized_text,
        entities=[],
        normalization_ops=list(block.operations),
        field_confidence={},
        processing=processing,
        review_status=ReviewStatus.REQUIRED,
    )


def _compose_segment(
    ordered_blocks: Sequence[NormalizedBlock],
    *,
    proposal_segment: ProposalSegment,
    proposal: StructureProposal,
    manifest: BookManifest,
) -> SemanticSegment:
    inherited = _inherited_audience(ordered_blocks)
    audience = proposal_segment.audience
    review_status = ReviewStatus.NOT_REQUIRED
    reasons = list(proposal_segment.review_reasons)

    for block in ordered_blocks:
        for reason in block.review_reasons:
            if reason not in reasons:
                reasons.append(reason)

    if inherited == Audience.GM and audience in {Audience.PLAYER, Audience.SHARED}:
        audience = Audience.GM
        review_status = ReviewStatus.REQUIRED
        if "audience_downgrade_candidate" not in reasons:
            reasons.append("audience_downgrade_candidate")

    if reasons:
        review_status = ReviewStatus.REQUIRED

    source_spans: list[SourceSpan] = [span for block in ordered_blocks for span in block.source_spans]
    normalization_ops = [op for block in ordered_blocks for op in block.operations]

    processing: dict[str, str] = {
        "classifier_id": proposal.classifier_id,
        "prompt_contract_version": proposal.prompt_contract_version,
        "input_sha256": proposal.input_sha256,
    }
    if reasons:
        processing["review_reasons"] = ",".join(reasons)

    return SemanticSegment(
        segment_id=_segment_id(
            manifest.book_id,
            proposal_segment.block_ids,
            proposal_segment.content_type,
            proposal_segment.section_path,
        ),
        parent_segment_id=proposal_segment.parent_segment_id,
        book_id=manifest.book_id,
        document_type=manifest.default_document_type,
        section_path=list(proposal_segment.section_path),
        content_type=proposal_segment.content_type,
        audience=audience,
        inherited_audience=inherited,
        source_spans=source_spans,
        raw_text=_TEXT_JOIN.join(block.raw_text for block in ordered_blocks),
        normalized_text=_TEXT_JOIN.join(block.normalized_text for block in ordered_blocks),
        entities=list(proposal_segment.entities),
        normalization_ops=normalization_ops,
        field_confidence=dict(proposal_segment.field_confidence),
        processing=processing,
        review_status=review_status,
    )


def _validate_proposal_segment(
    block_ids: Sequence[str],
    *,
    blocks_by_id: dict[str, NormalizedBlock],
    source_index: dict[str, int],
    claimed: set[str],
) -> str | None:
    """無効な提案セグメントなら失敗理由を返す。有効なら None。"""
    if len(block_ids) != len(set(block_ids)):
        return "duplicate_block_ref"
    if any(block_id not in blocks_by_id for block_id in block_ids):
        return "unknown_block_id"
    if any(block_id in claimed for block_id in block_ids):
        return "duplicate_block_ref"

    indices = sorted(source_index[block_id] for block_id in block_ids)
    # 飛び越し（非連続）: source 上で中間ブロックを飛ばしている
    if indices[-1] - indices[0] + 1 != len(indices):
        return "non_contiguous_block_ids"
    return None


def _inherited_audience(blocks: Sequence[NormalizedBlock]) -> Audience:
    """参照ブロック群の継承 audience を fail-closed に畳み込む。"""
    audiences = [block.inherited_audience for block in blocks]
    if any(audience == Audience.GM for audience in audiences):
        return Audience.GM
    if any(audience == Audience.UNKNOWN for audience in audiences):
        return Audience.UNKNOWN
    unique = set(audiences)
    if len(unique) == 1:
        return audiences[0]
    return Audience.SHARED


def _source_key(block: NormalizedBlock) -> tuple[int, int, int]:
    """本文合成・順序判定に使う安定キー。"""
    start = block.source_spans[0].start if block.source_spans else 0
    return (block.page, block.draw_order, start)


def _segment_id(
    book_id: str,
    block_ids: Sequence[str],
    content_type: str,
    section_path: Sequence[str],
) -> str:
    """書籍IDと境界から決定的な segment_id を生成する。"""
    payload = "|".join(
        [
            book_id,
            ",".join(block_ids),
            content_type,
            "/".join(section_path),
        ]
    )
    return f"{book_id}-{hashlib.sha256(payload.encode()).hexdigest()[:16]}"
