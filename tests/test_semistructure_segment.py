"""LLM提案から正本セグメントを決定的に組み立てるテスト。"""

from __future__ import annotations

import hashlib

from nova_parser.semistructure.models import Audience, DocumentType, DocumentTypeOverride, ReviewStatus
from nova_parser.semistructure.segment import assemble_segments, fallback_segment
from tests.semistructure_factories import make_block, make_manifest, make_proposal


def test_assemble_segments_composes_text_from_blocks_in_source_order() -> None:
    """複数ブロックは入力の source 順で本文と span を合成する。"""
    blocks = [make_block("b1", "前半"), make_block("b2", "後半")]
    proposal = make_proposal(block_ids=["b1", "b2"])

    segments = assemble_segments(blocks, proposal, make_manifest())

    assert segments[0].normalized_text == "前半\n\n後半"
    assert [span.rect_id for span in segments[0].source_spans] == ["r1", "r2"]


def test_segment_id_is_stable_for_same_input() -> None:
    """同一入力から生成する segment_id は決定的で安定している。"""
    blocks = [make_block("b1", "本文")]
    proposal = make_proposal(block_ids=["b1"])
    manifest = make_manifest()
    first = assemble_segments(blocks, proposal, manifest)[0].segment_id
    second = assemble_segments(blocks, proposal, manifest)[0].segment_id
    assert first == second


def test_unreferenced_block_becomes_unknown_fallback() -> None:
    """提案に含まれないブロックは原文を保持した unknown になる。"""
    segments = assemble_segments(
        [make_block("b1", "保持される原文")],
        make_proposal(segments=[]),
        make_manifest(),
    )
    assert segments[0].content_type == "unknown"
    assert segments[0].review_status == ReviewStatus.REQUIRED
    assert segments[0].raw_text == "保持される原文"


def test_compose_uses_source_order_not_proposal_order() -> None:
    """提案の block_ids 順ではなく (page, draw_order, source start) で本文を合成する。"""
    # 入力リスト・提案 ID とも b2→b1 だが、draw_order 上は b1 が先
    blocks = [
        make_block("b2", "後半", draw_order=1),
        make_block("b1", "前半", draw_order=0),
    ]
    proposal = make_proposal(block_ids=["b2", "b1"])

    segments = assemble_segments(blocks, proposal, make_manifest())

    assert len(segments) == 1
    assert segments[0].normalized_text == "前半\n\n後半"
    assert [span.rect_id for span in segments[0].source_spans] == ["r1", "r2"]


def test_unknown_id_does_not_discard_whole_proposal() -> None:
    """未知 ID を含む提案セグメントだけを落とし、他セグメントは組み立てる。"""
    blocks = [make_block("b1", "有効"), make_block("b2", "別")]
    proposal = make_proposal(
        segments=[
            make_proposal(block_ids=["missing"]).segments[0],
            make_proposal(block_ids=["b2"], segment={"content_type": "rule.note"}).segments[0],
        ]
    )

    segments = assemble_segments(blocks, proposal, make_manifest())

    by_type = {segment.content_type: segment for segment in segments}
    assert by_type["rule.note"].normalized_text == "別"
    assert by_type["unknown"].raw_text == "有効"
    assert by_type["unknown"].review_status == ReviewStatus.REQUIRED


def test_duplicate_block_ref_goes_to_fallback() -> None:
    """重複参照されたブロックは unknown fallback になり、提案全体は破棄しない。"""
    blocks = [make_block("b1", "一回目"), make_block("b2", "二回目")]
    first = make_proposal(block_ids=["b1"]).segments[0]
    second = make_proposal(block_ids=["b1", "b2"], segment={"content_type": "rule.note"}).segments[0]
    proposal = make_proposal(segments=[first, second])

    segments = assemble_segments(blocks, proposal, make_manifest())

    texts = {segment.normalized_text for segment in segments}
    assert "一回目" in texts
    # b1 は最初のセグメントで消費済み。二番目は重複として b2 も fallback
    fallbacks = [segment for segment in segments if segment.content_type == "unknown"]
    assert any(segment.raw_text == "二回目" for segment in fallbacks)


def test_non_contiguous_blocks_become_fallback() -> None:
    """中間ブロックを飛ばした提案は該当ブロックを unknown にする。"""
    blocks = [make_block("b1", "A"), make_block("b2", "B"), make_block("b3", "C")]
    proposal = make_proposal(block_ids=["b1", "b3"])

    segments = assemble_segments(blocks, proposal, make_manifest())

    assert all(segment.content_type == "unknown" for segment in segments)
    assert {segment.raw_text for segment in segments} == {"A", "B", "C"}


def test_gm_audience_fail_closed_keeps_gm_and_requires_review() -> None:
    """継承が GM のとき提案の player/shared でも audience は gm のまま REQUIRED にする。"""
    blocks = [make_block("b1", "GM限定", inherited_audience=Audience.GM)]
    proposal = make_proposal(block_ids=["b1"], segment={"audience": Audience.PLAYER})

    segment = assemble_segments(blocks, proposal, make_manifest())[0]

    assert segment.audience == Audience.GM
    assert segment.inherited_audience == Audience.GM
    assert segment.review_status == ReviewStatus.REQUIRED
    assert "audience_downgrade_candidate" in segment.processing.get("review_reasons", "")


def test_segment_id_matches_hash_formula() -> None:
    """segment_id は brief のハッシュ式と一致する。"""
    blocks = [make_block("b1", "本文")]
    proposal = make_proposal(
        block_ids=["b1"],
        segment={"content_type": "rule.explanation", "section_path": ["章", "節"]},
    )
    manifest = make_manifest(book_id="eg-test")

    segment = assemble_segments(blocks, proposal, manifest)[0]

    payload = "|".join(
        [
            "eg-test",
            "b1",
            "rule.explanation",
            "章/節",
        ]
    )
    expected = f"eg-test-{hashlib.sha256(payload.encode()).hexdigest()[:16]}"
    assert segment.segment_id == expected


def test_compose_segment_uses_document_type_override() -> None:
    """override 範囲内のページのセグメントは override の document_type になる。"""
    blocks = [make_block("b1", "シナリオ本文", page=55)]
    proposal = make_proposal(block_ids=["b1"])
    manifest = make_manifest(
        document_type_overrides=[
            DocumentTypeOverride(start_page=50, end_page=60, document_type=DocumentType.SCENARIO),
        ],
    )

    segments = assemble_segments(blocks, proposal, manifest)

    assert segments[0].document_type == DocumentType.SCENARIO


def test_compose_segment_uses_default_outside_override_range() -> None:
    """override 範囲外のページのセグメントは default_document_type になる。"""
    blocks = [make_block("b1", "ルール本文", page=22)]
    proposal = make_proposal(block_ids=["b1"])
    manifest = make_manifest(
        document_type_overrides=[
            DocumentTypeOverride(start_page=50, end_page=60, document_type=DocumentType.SCENARIO),
        ],
    )

    segments = assemble_segments(blocks, proposal, manifest)

    assert segments[0].document_type == DocumentType.RULEBOOK


def test_fallback_segment_uses_document_type_override() -> None:
    """分類失敗フォールバック経路でも override の document_type が適用される。"""
    blocks = [make_block("b1", "シナリオ本文", page=55)]
    manifest = make_manifest(
        document_type_overrides=[
            DocumentTypeOverride(start_page=50, end_page=60, document_type=DocumentType.SCENARIO),
        ],
    )

    segments = assemble_segments(
        blocks,
        make_proposal(segments=[]),
        manifest,
    )

    assert segments[0].content_type == "unknown"
    assert segments[0].document_type == DocumentType.SCENARIO


def test_compose_segment_mixed_override_adds_review_reason() -> None:
    """複数 override 範囲をまたぐブロックは default_document_type + レビュー理由になる。"""
    blocks = [
        make_block("b1", "前半", page=49, draw_order=0),
        make_block("b2", "後半", page=50, draw_order=1),
    ]
    proposal = make_proposal(block_ids=["b1", "b2"])
    manifest = make_manifest(
        document_type_overrides=[
            DocumentTypeOverride(start_page=50, end_page=60, document_type=DocumentType.SCENARIO),
        ],
    )

    segments = assemble_segments(blocks, proposal, manifest)

    assert segments[0].document_type == DocumentType.RULEBOOK
    assert "mixed_document_type_override" in segments[0].processing.get("review_reasons", "")


def test_fallback_segment_preserves_block_text_and_spans() -> None:
    """fallback_segment は原文・正規化・span を保持し unknown/REQUIRED にする。"""
    block = make_block("b1", "保持される原文")

    segment = fallback_segment(block, "unreferenced_block")

    assert segment.content_type == "unknown"
    assert segment.review_status == ReviewStatus.REQUIRED
    assert segment.raw_text == "保持される原文"
    assert segment.normalized_text == "保持される原文"
    assert segment.source_spans == block.source_spans
    assert "unreferenced_block" in segment.processing.get("review_reasons", "")
