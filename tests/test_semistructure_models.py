"""半構造化モデルの制約テスト。"""

import pytest
from pydantic import ValidationError

from nova_parser.semistructure.models import (
    Audience,
    BookOutline,
    DocumentType,
    OutlineSection,
    SemanticSegment,
    SourceSpan,
    StructureProposal,
    StructureWindow,
)
from tests.semistructure_factories import FakeClassifier, make_block


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


def test_structure_proposal_rejects_extra_top_level_field() -> None:
    """構造提案はLLMが返した未知のトップレベルフィールドを拒否する。"""
    with pytest.raises(ValidationError, match="summary"):
        StructureProposal.model_validate({"segments": [], "summary": "生成要約"})


def test_structure_proposal_rejects_generated_text_in_nested_segment() -> None:
    """構造提案はネストしたセグメントに生成本文を受理しない。"""
    with pytest.raises(ValidationError, match="normalized_text"):
        StructureProposal.model_validate(
            {
                "segments": [
                    {
                        "block_ids": ["b1"],
                        "content_type": "rule.explanation",
                        "audience": "shared",
                        "normalized_text": "生成本文",
                    }
                ]
            }
        )


def test_structure_proposal_requires_valid_processing_metadata() -> None:
    """構造提案は分類器・prompt契約・入力hashを必須で保持する。"""
    with pytest.raises(ValidationError):
        StructureProposal(segments=[])
    with pytest.raises(ValidationError, match="input_sha256"):
        StructureProposal(
            segments=[],
            classifier_id="gemini:test",
            prompt_contract_version="v1",
            input_sha256="not-a-hash",
        )


def test_structure_window_rejects_unknown_or_duplicate_allowed_block_ids() -> None:
    """返却許可IDは文脈内に存在し、重複してはならない。"""
    blocks = [make_block("b1"), make_block("b2")]
    with pytest.raises(ValidationError, match="存在"):
        StructureWindow(
            center_page=22,
            context_blocks=blocks,
            allowed_block_ids=["missing"],
        )
    with pytest.raises(ValidationError, match="重複"):
        StructureWindow(
            center_page=22,
            context_blocks=blocks,
            allowed_block_ids=["b1", "b1"],
        )


def test_book_outline_rejects_extra_top_level_field() -> None:
    """章構造はLLMが返した未知のトップレベルフィールドを拒否する。"""
    with pytest.raises(ValidationError, match="summary"):
        BookOutline.model_validate({"book_id": "eg", "sections": [], "summary": "生成要約"})


def test_outline_section_has_title_and_default_content_type() -> None:
    """章構造は章名とページ範囲と既定content_typeを保持する。"""
    section = OutlineSection(
        title="ルール",
        start_page=22,
        end_page=30,
        default_content_type="rule.explanation",
    )

    assert section.title == "ルール"
    assert section.default_content_type == "rule.explanation"


def test_outline_section_rejects_descending_page_range() -> None:
    """章構造は終了ページが開始ページより前の範囲を拒否する。"""
    with pytest.raises(ValidationError, match="昇順"):
        OutlineSection(
            title="ルール",
            start_page=30,
            end_page=22,
            default_content_type="rule.explanation",
        )


def test_book_outline_rejects_extra_field_in_nested_section() -> None:
    """章構造はネストした章候補の未知フィールドも拒否する。"""
    with pytest.raises(ValidationError, match="summary"):
        BookOutline.model_validate(
            {
                "book_id": "eg",
                "sections": [
                    {
                        "title": "ルール",
                        "start_page": 22,
                        "end_page": 30,
                        "default_content_type": "rule.explanation",
                        "summary": "生成要約",
                    }
                ],
            }
        )


def test_fake_classifier_returns_outline_with_section_defaults() -> None:
    """偽分類器の章構造もOutlineSectionの必須契約を満たす。"""
    outline = FakeClassifier.valid().infer_outline([make_block()])

    assert outline.sections[0].title == "テスト章"
    assert outline.sections[0].default_content_type == "unknown"
