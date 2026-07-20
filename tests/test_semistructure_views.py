"""Ruri 向け検索・トピック派生ビューのテスト。"""

from __future__ import annotations

from nova_parser.semistructure.models import Audience
from nova_parser.semistructure.views import (
    build_retrieval_view,
    build_topic_view,
    build_views,
)
from tests.semistructure_factories import make_segment


def test_player_views_exclude_gm_and_unknown() -> None:
    """プレイヤーモードでは GM / UNKNOWN を検索・トピック双方から除外する。"""
    segments = [
        make_segment("shared", Audience.SHARED),
        make_segment("gm", Audience.GM),
        make_segment("unknown", Audience.UNKNOWN),
    ]
    views = build_views(segments, audience_mode="player")
    assert [view.segment_id for view in views.retrieval] == ["shared"]
    assert [view.segment_id for view in views.topic] == ["shared"]


def test_retrieval_and_topic_prefixes_are_explicit() -> None:
    """短文でも長さヒューリスティックではなく明示プレフィックスを付ける。"""
    segment = make_segment("s1", Audience.SHARED, normalized_text="短い規則")
    assert build_retrieval_view(segment).text.startswith("検索文書: ")
    assert build_topic_view(segment).text.startswith("トピック: ")


def test_retrieval_view_field_order_and_title_fallback() -> None:
    """検索ビューの行順と、書籍タイトル未指定時の book_id フォールバック。"""
    segment = make_segment(
        "s1",
        Audience.SHARED,
        section_path=["章A", "節B"],
        content_type="rule.explanation",
        normalized_text="短い規則",
    )
    view = build_retrieval_view(segment)
    assert view.input_type == "document"
    assert view.segment_id == "s1"
    assert view.book_id == "eg-test"
    assert view.audience == Audience.SHARED
    lines = view.text.splitlines()
    assert lines[0] == "検索文書: 書籍: eg-test"
    assert lines[1] == "章節: 章A > 節B"
    assert lines[2] == "種別: rule.explanation"
    assert lines[3] == "本文: 短い規則"

    titled = build_retrieval_view(segment, title="テスト書籍")
    assert titled.text.splitlines()[0] == "検索文書: 書籍: テスト書籍"


def test_topic_view_keeps_prefix_when_entities_empty() -> None:
    """entities が空でも `トピック: ` 行を残し、短文を水増ししない。"""
    segment = make_segment(
        "s1",
        Audience.SHARED,
        section_path=["章A"],
        content_type="rule.term",
        normalized_text="短い",
        entities=[],
    )
    view = build_topic_view(segment)
    assert view.input_type == "topic"
    lines = view.text.splitlines()
    assert lines[0] == "トピック: "
    assert lines[1] == "章節: 章A"
    assert lines[2] == "種別: rule.term"
    assert lines[3] == "本文: 短い"
    # 100文字以上への水増しはしない
    assert len(view.text) < 100


def test_topic_view_joins_entities_with_ideographic_comma() -> None:
    """entities は読点「、」で結合する。"""
    segment = make_segment(
        "s1",
        entities=["TRPG", "ゲームマスター"],
        normalized_text="本文",
    )
    view = build_topic_view(segment)
    assert view.text.splitlines()[0] == "トピック: TRPG、ゲームマスター"


def test_player_views_include_player_and_shared() -> None:
    """プレイヤーモードは PLAYER と SHARED を含む。"""
    segments = [
        make_segment("player", Audience.PLAYER),
        make_segment("shared", Audience.SHARED),
    ]
    views = build_views(segments, audience_mode="player")
    assert [view.segment_id for view in views.retrieval] == ["player", "shared"]
    assert [view.segment_id for view in views.topic] == ["player", "shared"]


def test_all_mode_includes_gm() -> None:
    """audience_mode=all では GM も派生対象に含める。"""
    segments = [
        make_segment("shared", Audience.SHARED),
        make_segment("gm", Audience.GM),
    ]
    views = build_views(segments, audience_mode="all")
    assert [view.segment_id for view in views.retrieval] == ["shared", "gm"]


def test_build_views_uses_book_titles_map() -> None:
    """build_views は book_id → title の対応を検索ビューへ渡せる。"""
    segments = [make_segment("s1", Audience.SHARED, normalized_text="本文")]
    views = build_views(
        segments,
        audience_mode="player",
        book_titles={"eg-test": "テスト書籍"},
    )
    assert views.retrieval[0].text.startswith("検索文書: 書籍: テスト書籍")
