"""原文被覆・参照・順序・audience 安全性の検証テスト。"""

from __future__ import annotations

from nova_parser.semistructure.models import Audience, SourceSpan
from nova_parser.semistructure.validate import validate_corpus, validate_player_visibility
from tests.semistructure_factories import make_page, make_region, make_segment


def test_validate_corpus_reports_missing_character_range() -> None:
    """原文の一部が source_spans に含まれないとき source_gap と coverage を報告する。"""
    report = validate_corpus(
        pages=[make_page(text="ABCDE")],
        segments=[make_segment(spans=[SourceSpan(page=22, rect_id="r1", start=0, end=4)])],
    )
    assert report.coverage_ratio == 0.8
    assert report.errors[0].code == "source_gap"


def test_validate_player_visibility_rejects_gm_and_unknown_in_export_set() -> None:
    """プレイヤー向け導出集合に混入した unknown / gm を拒否する。

    正本全体ではなく、player 派生に載った（または載ろうとしている）セグメント集合に対して使う。
    """
    report = validate_player_visibility(
        [
            make_segment(audience=Audience.UNKNOWN),
            make_segment(audience=Audience.GM),
        ]
    )
    assert {error.code for error in report.errors} == {
        "unknown_audience_visible",
        "gm_audience_visible",
    }


def test_validate_corpus_reports_overlap() -> None:
    """同一領域内で source_spans が重なると source_overlap になる。"""
    report = validate_corpus(
        pages=[make_page(text="ABCDE")],
        segments=[
            make_segment(
                "s1",
                spans=[SourceSpan(page=22, rect_id="r1", start=0, end=3)],
            ),
            make_segment(
                "s2",
                spans=[SourceSpan(page=22, rect_id="r1", start=2, end=5)],
            ),
        ],
    )
    assert any(error.code == "source_overlap" for error in report.errors)


def test_validate_corpus_reports_invalid_source_ref() -> None:
    """存在しない rect や範囲外オフセットは invalid_source_ref になる。"""
    report = validate_corpus(
        pages=[make_page(text="ABC")],
        segments=[
            make_segment(
                "s1",
                spans=[SourceSpan(page=22, rect_id="missing", start=0, end=1)],
            ),
            make_segment(
                "s2",
                spans=[SourceSpan(page=22, rect_id="r1", start=0, end=10)],
            ),
        ],
    )
    codes = {error.code for error in report.errors}
    assert "invalid_source_ref" in codes


def test_validate_corpus_reports_source_order_reversal() -> None:
    """同一セグメント内で source_spans の読み順が逆転すると source_order_reversal になる。"""
    report = validate_corpus(
        pages=[make_page(text="ABCDEF")],
        segments=[
            make_segment(
                spans=[
                    SourceSpan(page=22, rect_id="r1", start=3, end=6),
                    SourceSpan(page=22, rect_id="r1", start=0, end=3),
                ],
            ),
        ],
    )
    assert any(error.code == "source_order_reversal" for error in report.errors)


def test_validate_corpus_reports_parent_cycle() -> None:
    """parent_segment_id の循環は parent_cycle になる。"""
    s1 = make_segment("s1", parent_segment_id="s2")
    s2 = make_segment("s2", parent_segment_id="s1")
    report = validate_corpus(pages=[make_page(text="本文")], segments=[s1, s2])
    assert any(error.code == "parent_cycle" for error in report.errors)


def test_validate_corpus_full_coverage_has_no_gap() -> None:
    """全文字が被覆されていれば source_gap は出ず coverage は 1.0 になる。"""
    text = "ABCDE"
    report = validate_corpus(
        pages=[make_page(text=text)],
        segments=[make_segment(spans=[SourceSpan(page=22, rect_id="r1", start=0, end=len(text))])],
    )
    assert report.coverage_ratio == 1.0
    assert all(error.code != "source_gap" for error in report.errors)


def test_validate_corpus_covers_whitespace_and_newlines() -> None:
    """空白・改行も被覆対象に含め、欠落すれば source_gap になる。"""
    text = "A\n B"
    # 改行と空白を飛ばして A と B だけ被覆
    report = validate_corpus(
        pages=[make_page(text=text)],
        segments=[
            make_segment(
                spans=[
                    SourceSpan(page=22, rect_id="r1", start=0, end=1),
                    SourceSpan(page=22, rect_id="r1", start=3, end=4),
                ],
            ),
        ],
    )
    assert report.coverage_ratio < 1.0
    assert any(error.code == "source_gap" for error in report.errors)


def test_validate_corpus_multi_region_coverage() -> None:
    """複数領域の被覆率は全領域の文字数に対する被覆文字数で計算する。"""
    page = make_page(
        regions=[
            make_region("r1", "AB"),
            make_region("r2", "CD"),
        ],
    )
    report = validate_corpus(
        pages=[page],
        segments=[
            make_segment(
                spans=[SourceSpan(page=22, rect_id="r1", start=0, end=2)],
            ),
        ],
    )
    # r1 全被覆、r2 未被覆 → 2/4
    assert report.coverage_ratio == 0.5
    assert any(error.code == "source_gap" for error in report.errors)


def test_validate_player_visibility_allows_player_and_shared() -> None:
    """player / shared はプレイヤー向け可視性検証を通過する。"""
    report = validate_player_visibility(
        [
            make_segment("s1", audience=Audience.PLAYER),
            make_segment("s2", audience=Audience.SHARED),
        ]
    )
    assert report.errors == []
