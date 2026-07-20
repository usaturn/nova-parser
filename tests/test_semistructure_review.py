"""レビューキューと Markdown 生成・判断適用のテスト。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from nova_parser.semistructure.models import (
    Audience,
    ReviewDecision,
    ReviewStatus,
    SemanticSegment,
    SourceSpan,
)
from nova_parser.semistructure.review import build_review_items, render_review_markdown
from nova_parser.semistructure.storage import (
    apply_review_decisions,
    load_review_decisions,
    read_jsonl,
    write_jsonl_atomic,
)
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


def test_write_and_read_jsonl_atomic_roundtrip(tmp_path: Path) -> None:
    """同一ディレクトリ一時ファイル経由の原子書き込みと往復読み出し。"""
    path = tmp_path / "out" / "segments.jsonl"
    segments = [
        make_segment("s1", normalized_text="一"),
        make_segment("s2", normalized_text="二"),
    ]

    write_jsonl_atomic(path, segments)

    assert path.is_file()
    # 一時ファイルが残っていないこと
    assert list(path.parent.glob("*.tmp")) == []
    loaded = read_jsonl(path, SemanticSegment)
    assert [segment.segment_id for segment in loaded] == ["s1", "s2"]
    assert loaded[0].normalized_text == "一"
    # ensure_ascii=False で日本語がエスケープされない
    raw = path.read_text(encoding="utf-8")
    assert "一" in raw
    assert "\\u" not in raw


def test_load_review_decisions_keyed_by_review_id(tmp_path: Path) -> None:
    """decisions JSONL を review_id キーの辞書として読み込む。"""
    path = tmp_path / "decisions.jsonl"
    decision = ReviewDecision(
        review_id="eg-test:s1",
        segment_id="s1",
        status=ReviewStatus.APPROVED,
        input_hash="sha256:" + "a" * 64,
        processing_version="test-v1",
        decided_by="reviewer-1",
        comment="ok",
    )
    write_jsonl_atomic(path, [decision])

    loaded = load_review_decisions(path)

    assert set(loaded) == {"eg-test:s1"}
    assert loaded["eg-test:s1"].status == ReviewStatus.APPROVED
    assert loaded["eg-test:s1"].comment == "ok"


def test_apply_review_decisions_when_hash_matches() -> None:
    """review_id と input_hash が一致する判断だけ status を適用する。"""
    input_hash = "sha256:" + "b" * 64
    segment = make_segment(
        "s1",
        review_status=ReviewStatus.REQUIRED,
        processing={
            "input_hash": input_hash,
            "review_reasons": "low_confidence",
        },
    )
    decisions = {
        "eg-test:s1": ReviewDecision(
            review_id="eg-test:s1",
            segment_id="s1",
            status=ReviewStatus.APPROVED,
            input_hash=input_hash,
            processing_version="test-v1",
            decided_by="reviewer-1",
        ),
    }

    applied = apply_review_decisions([segment], decisions)

    assert len(applied) == 1
    assert applied[0].review_status == ReviewStatus.APPROVED


def test_apply_review_decisions_stale_when_hash_mismatches() -> None:
    """入力ハッシュが変わった判断は stale_review_decision として再レビューへ戻す。"""
    segment = make_segment(
        "s1",
        review_status=ReviewStatus.NOT_REQUIRED,
        processing={"input_hash": "sha256:" + "c" * 64},
    )
    decisions = {
        "eg-test:s1": ReviewDecision(
            review_id="eg-test:s1",
            segment_id="s1",
            status=ReviewStatus.APPROVED,
            input_hash="sha256:" + "d" * 64,
            processing_version="test-v1",
            decided_by="reviewer-1",
        ),
    }

    applied = apply_review_decisions([segment], decisions)

    assert applied[0].review_status == ReviewStatus.REQUIRED
    reasons = applied[0].processing.get("review_reasons", "")
    assert "stale_review_decision" in reasons.split(",")


def test_apply_review_decisions_matches_input_sha256_fallback() -> None:
    """processing.input_hash が無くても input_sha256 と照合できる。"""
    digest = "sha256:" + "e" * 64
    segment = make_segment(
        "s1",
        review_status=ReviewStatus.REQUIRED,
        processing={"input_sha256": digest},
    )
    decisions = {
        "eg-test:s1": ReviewDecision(
            review_id="eg-test:s1",
            segment_id="s1",
            status=ReviewStatus.REJECTED,
            input_hash=digest,
            processing_version="test-v1",
            decided_by="reviewer-1",
        ),
    }

    applied = apply_review_decisions([segment], decisions)

    assert applied[0].review_status == ReviewStatus.REJECTED
