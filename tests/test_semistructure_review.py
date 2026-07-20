"""レビューキューと Markdown 生成のテスト。"""

from __future__ import annotations

import json
import re

from nova_parser.semistructure.models import Audience, ReviewStatus, SourceSpan
from nova_parser.semistructure.review import build_review_items, render_review_markdown
from tests.semistructure_factories import make_page, make_segment


def test_build_review_items_from_required_segments() -> None:
    """REQUIRED セグメントから理由・span・画像名を持つ ReviewItem を作る。"""
    segments = [
        make_segment(
            "s1",
            review_status=ReviewStatus.REQUIRED,
            processing={"review_reasons": "audience_downgrade_candidate,unknown_block_id"},
            spans=[SourceSpan(page=22, rect_id="r1", start=0, end=2)],
            raw_text="原文A",
            normalized_text="正規A",
        ),
        make_segment(
            "s2",
            review_status=ReviewStatus.NOT_REQUIRED,
            raw_text="対象外",
        ),
    ]
    pages = [make_page(text="原文A")]

    items = build_review_items(segments, pages=pages)

    assert len(items) == 1
    item = items[0]
    assert item.segment_id == "s1"
    assert item.status == ReviewStatus.REQUIRED
    assert item.reasons == ["audience_downgrade_candidate", "unknown_block_id"]
    assert item.raw_text == "原文A"
    assert item.normalized_text == "正規A"
    assert item.image_name == "p022.png"
    assert item.source_spans[0].rect_id == "r1"
    assert item.review_id


def test_build_review_items_fills_neighbor_context() -> None:
    """前後セグメントの本文を context_before / context_after に入れる。"""
    segments = [
        make_segment("s0", raw_text="前文", normalized_text="前文"),
        make_segment(
            "s1",
            review_status=ReviewStatus.REQUIRED,
            processing={"review_reasons": "low_confidence"},
            raw_text="対象",
            normalized_text="対象",
        ),
        make_segment("s2", raw_text="後文", normalized_text="後文"),
    ]

    items = build_review_items(segments)

    assert len(items) == 1
    assert items[0].context_before == "前文"
    assert items[0].context_after == "後文"


def test_build_review_items_default_reason_when_missing() -> None:
    """review_reasons が無くても REQUIRED なら既定理由で項目化する。"""
    segments = [
        make_segment(
            "s1",
            review_status=ReviewStatus.REQUIRED,
            processing={},
        ),
    ]

    items = build_review_items(segments)

    assert len(items) == 1
    assert items[0].reasons
    assert items[0].reasons[0]


def test_render_review_markdown_includes_required_fields() -> None:
    """Markdown に ID・危険度・理由・位置・原文・正規化・前後・画像・JSON 例を含む。"""
    segments = [
        make_segment("s0", raw_text="前文", normalized_text="前文"),
        make_segment(
            "s1",
            audience=Audience.GM,
            review_status=ReviewStatus.REQUIRED,
            processing={"review_reasons": "audience_downgrade_candidate"},
            spans=[SourceSpan(page=22, rect_id="r1", start=0, end=2)],
            raw_text="秘密の原文",
            normalized_text="秘密の正規化",
        ),
        make_segment("s2", raw_text="後文", normalized_text="後文"),
    ]
    items = build_review_items(segments, pages=[make_page(text="秘密の原文")])
    markdown = render_review_markdown(items)

    assert items[0].review_id in markdown
    assert "audience_downgrade_candidate" in markdown
    assert "eg-test" in markdown  # 書籍
    assert "22" in markdown  # ページ
    assert "r1" in markdown
    assert "秘密の原文" in markdown
    assert "秘密の正規化" in markdown
    assert "前文" in markdown
    assert "後文" in markdown
    assert "p022.png" in markdown
    # 危険度
    assert re.search(r"危険度|severity", markdown, re.IGNORECASE)
    # 承認・却下の JSON 例
    assert "approved" in markdown
    assert "rejected" in markdown
    # 秘密情報や LLM 生レスポンスをダンプしない
    assert "VERTEX_AI_API_KEY" not in markdown
    assert "GOOGLE_GENAI" not in markdown


def test_render_review_markdown_json_examples_are_parseable() -> None:
    """承認・却下の JSON 例は ReviewDecision 相当のキーを持つ。"""
    segments = [
        make_segment(
            "s1",
            review_status=ReviewStatus.REQUIRED,
            processing={"review_reasons": "table_like_spacing"},
        ),
    ]
    items = build_review_items(segments)
    markdown = render_review_markdown(items)

    # fenced JSON ブロックを抽出
    blocks = re.findall(r"```json\n(.*?)\n```", markdown, re.DOTALL)
    assert len(blocks) >= 2
    payloads = [json.loads(block) for block in blocks]
    statuses = {payload["status"] for payload in payloads}
    assert statuses == {"approved", "rejected"}
    for payload in payloads:
        assert payload["review_id"] == items[0].review_id
        assert payload["segment_id"] == "s1"
        assert "input_hash" in payload
        assert "processing_version" in payload
        assert "decided_by" in payload
