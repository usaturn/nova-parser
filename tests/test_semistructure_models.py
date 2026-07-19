"""半構造化モデルの制約テスト。"""

import pytest
from pydantic import ValidationError

from nova_parser.semistructure.models import (
    Audience,
    DocumentType,
    SemanticSegment,
    SourceSpan,
)


def test_source_span_rejects_empty_range() -> None:
    """SourceSpan は空の文字範囲を拒否する。"""
    with pytest.raises(ValidationError):
        SourceSpan(page=22, rect_id="r1", start=4, end=4)


def test_semantic_segment_rejects_player_child_of_gm() -> None:
    """GM範囲を継承した未承認セグメントは player へ降格できない。"""
    with pytest.raises(ValidationError, match="GM"):
        SemanticSegment(
            segment_id="s1",
            book_id="eg",
            document_type=DocumentType.RULEBOOK,
            section_path=["シナリオ"],
            content_type="scenario.handout",
            audience=Audience.PLAYER,
            inherited_audience=Audience.GM,
            source_spans=[SourceSpan(page=234, rect_id="r1", start=0, end=10)],
            raw_text="0123456789",
            normalized_text="0123456789",
        )
