"""OCR原文を保った決定的な改行正規化のテスト。"""

from nova_parser.semistructure.models import SourceSpan
from nova_parser.semistructure.normalize import (
    PhysicalLine,
    classify_line_join,
    normalize_pages,
)
from tests.semistructure_factories import make_page, make_region


def test_normalize_joins_word_wrap_and_records_operation() -> None:
    page = make_page(text="ゲームマス\nターが進行する。")

    blocks = normalize_pages([page])

    assert blocks[0].raw_text == "ゲームマス\nターが進行する。"
    assert blocks[0].normalized_text == "ゲームマスターが進行する。"
    assert blocks[0].operations[0].type == "join_physical_lines"
    assert blocks[0].operations[0].rule_id == "ja-word-wrap-v1"
    assert blocks[0].source_spans == [SourceSpan(page=22, rect_id="r1", start=0, end=14)]


def test_normalize_does_not_auto_join_different_regions() -> None:
    page = make_page(regions=[make_region("r1", "本文"), make_region("r2", "欄外注釈")])

    blocks = normalize_pages([page])

    assert [block.normalized_text for block in blocks] == ["本文", "欄外注釈"]
    assert blocks[1].review_reasons == ["cross_region_relation"]


def test_classify_line_join_keeps_sentence_boundary() -> None:
    left = PhysicalLine(page=22, rect_id="r1", text="一文目です。", start=0, end=6)
    right = PhysicalLine(page=22, rect_id="r1", text="次の文です", start=7, end=12)

    decision = classify_line_join(left, right)

    assert decision.should_join is False
    assert decision.rule_id is None
    assert decision.review_reason is None


def test_normalize_marks_bullet_structure_for_review() -> None:
    page = make_page(text="説明\n●項目")

    block = normalize_pages([page])[0]

    assert block.normalized_text == "説明\n●項目"
    assert block.review_reasons == ["bullet_list_structure"]


def test_normalize_marks_table_like_spacing_for_review() -> None:
    page = make_page(text="名前  値\n筋力  10")

    block = normalize_pages([page])[0]

    assert block.normalized_text == "名前  値\n筋力  10"
    assert block.review_reasons == ["table_like_spacing"]


def test_normalize_marks_short_independent_lines_for_review() -> None:
    page = make_page(text="見出し\n注釈")

    block = normalize_pages([page])[0]

    assert block.normalized_text == "見出し\n注釈"
    assert block.review_reasons == ["short_independent_line"]


def test_normalize_does_not_join_short_heading_to_long_body() -> None:
    page = make_page(text="見出し\nこれは本文として続く独立文です。")

    block = normalize_pages([page])[0]

    assert block.normalized_text == "見出し\nこれは本文として続く独立文です。"
    assert block.review_reasons == ["short_independent_line"]


def test_normalize_skips_empty_ocr_region() -> None:
    page = make_page(
        regions=[
            make_region("r1", ""),
            make_region("r2", "本文"),
        ]
    )

    blocks = normalize_pages([page])

    assert [block.block_id for block in blocks] == ["eg-test:p022:r2"]
    assert blocks[0].review_reasons == []


def test_normalize_preserves_terminal_line_break_without_an_operation() -> None:
    page = make_page(text="本文\n")

    block = normalize_pages([page])[0]

    assert block.raw_text == "本文\n"
    assert block.normalized_text == "本文\n"
    assert block.operations == []


def test_normalize_marks_page_boundary_without_combining_pages() -> None:
    pages = [make_page(page=22, text="前ページ"), make_page(page=23, text="次ページ")]

    blocks = normalize_pages(pages)

    assert [block.normalized_text for block in blocks] == ["前ページ", "次ページ"]
    assert blocks[1].review_reasons == ["cross_page_relation"]


def test_normalize_is_deterministic_by_page_and_draw_order() -> None:
    page_23 = make_page(page=23, regions=[make_region("r3", "三", page=23, draw_order=2)])
    page_22 = make_page(
        page=22,
        regions=[
            make_region("r2", "二", draw_order=1),
            make_region("r1", "一", draw_order=0),
        ],
    )

    blocks = normalize_pages([page_23, page_22])

    assert [block.block_id for block in blocks] == [
        "eg-test:p022:r1",
        "eg-test:p022:r2",
        "eg-test:p023:r3",
    ]
    assert [block.normalized_text for block in blocks] == ["一", "二", "三"]


def test_p022_keeps_distinct_regions_and_joins_only_word_wrap() -> None:
    page = make_page(
        page=22,
        regions=[
            make_region("r1", "■ゲームマスター", draw_order=0),
            make_region("r2", "欄外注釈", draw_order=1),
            make_region("r3", "ゲームマス\nターが進行する。", draw_order=2),
        ],
    )

    blocks = normalize_pages([page])

    assert [block.normalized_text for block in blocks] == [
        "■ゲームマスター",
        "欄外注釈",
        "ゲームマスターが進行する。",
    ]
    assert [block.source_spans for block in blocks] == [
        [SourceSpan(page=22, rect_id="r1", start=0, end=8)],
        [SourceSpan(page=22, rect_id="r2", start=0, end=4)],
        [SourceSpan(page=22, rect_id="r3", start=0, end=14)],
    ]
    assert blocks[2].operations[0].rule_id == "ja-word-wrap-v1"
