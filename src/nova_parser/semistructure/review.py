"""人手レビューキューと Markdown の生成。"""

from __future__ import annotations

import json
from collections.abc import Sequence

from nova_parser.semistructure.models import (
    OcrPage,
    ReviewItem,
    ReviewStatus,
    SemanticSegment,
)

# 危険度の高い理由（audience 漏洩・降格候補など）
_HIGH_SEVERITY_REASONS = frozenset(
    {
        "audience_downgrade_candidate",
        "gm_audience_visible",
        "unknown_audience_visible",
        "unknown_block_id",
        "duplicate_block_ref",
        "non_contiguous_block_ids",
        "parent_cycle",
        "source_gap",
        "source_overlap",
        "invalid_source_ref",
        "source_order_reversal",
    }
)

_DEFAULT_REASON = "review_required"


def build_review_items(
    segments: Sequence[SemanticSegment],
    *,
    pages: Sequence[OcrPage] | None = None,
) -> list[ReviewItem]:
    """レビューが必要なセグメントから ReviewItem 一覧を構築する。

    Parameters
    ----------
    segments:
        正本セグメント列。並びは前後文脈の解決に使う。
    pages:
        任意。`image_name` を page 番号から解決するために使う。
        省略時は image_name は None。

    Notes
    -----
    - `review_status == REQUIRED` のセグメントを対象にする。
    - 理由は `processing["review_reasons"]` の CSV を優先し、空なら既定理由を使う。
    - `context_before` / `context_after` は列内の直前・直後セグメントの raw_text。
    """
    image_by_page = _image_name_index(pages or [])
    items: list[ReviewItem] = []

    for index, segment in enumerate(segments):
        if segment.review_status != ReviewStatus.REQUIRED:
            continue

        reasons = _extract_reasons(segment)
        first_span = segment.source_spans[0]
        image_name = image_by_page.get(first_span.page)
        context_before = segments[index - 1].raw_text if index > 0 else ""
        context_after = segments[index + 1].raw_text if index + 1 < len(segments) else ""

        items.append(
            ReviewItem(
                review_id=_review_id(segment),
                segment_id=segment.segment_id,
                reasons=reasons,
                source_spans=list(segment.source_spans),
                raw_text=segment.raw_text,
                normalized_text=segment.normalized_text,
                image_name=image_name,
                context_before=context_before,
                context_after=context_after,
                status=ReviewStatus.REQUIRED,
            )
        )
    return items


def render_review_markdown(items: Sequence[ReviewItem]) -> str:
    """レビュー項目を人手確認用 Markdown に整形する。

    各項目へ review_id、危険度、理由、書籍、ページ、rect_id、原文、正規化案、
    前後ブロック、元画像名、承認・却下時に記録すべき JSON 例を出す。
    秘密情報を含む環境変数や LLM レスポンス全体は出力しない。
    """
    if not items:
        return "# レビューキュー\n\n対象項目はありません。\n"

    lines: list[str] = [
        "# レビューキュー",
        "",
        f"件数: {len(items)}",
        "",
    ]
    for index, item in enumerate(items, start=1):
        severity = _severity(item.reasons)
        book_id = _book_id_from_review_id(item.review_id)
        pages = sorted({span.page for span in item.source_spans})
        rect_ids = sorted({span.rect_id for span in item.source_spans})
        page_text = ", ".join(str(page) for page in pages)
        rect_text = ", ".join(rect_ids)

        lines.extend(
            [
                f"## {index}. {item.review_id}",
                "",
                f"- **review_id**: `{item.review_id}`",
                f"- **segment_id**: `{item.segment_id}`",
                f"- **危険度 (severity)**: {severity}",
                f"- **理由 (reasons)**: {', '.join(item.reasons)}",
                f"- **書籍 (book_id)**: {book_id or '(不明)'}",
                f"- **ページ (page)**: {page_text}",
                f"- **rect_id**: {rect_text}",
                f"- **元画像名 (image_name)**: {item.image_name or '(なし)'}",
                f"- **status**: `{item.status.value}`",
                "",
                "### 原文 (raw_text)",
                "",
                "```text",
                item.raw_text,
                "```",
                "",
                "### 正規化案 (normalized_text)",
                "",
                "```text",
                item.normalized_text,
                "```",
                "",
                "### 前文脈 (context_before)",
                "",
                "```text",
                item.context_before or "(なし)",
                "```",
                "",
                "### 後文脈 (context_after)",
                "",
                "```text",
                item.context_after or "(なし)",
                "```",
                "",
                "### 承認時に記録する JSON 例",
                "",
                "```json",
                _decision_json_example(item, status="approved"),
                "```",
                "",
                "### 却下時に記録する JSON 例",
                "",
                "```json",
                _decision_json_example(item, status="rejected"),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _extract_reasons(segment: SemanticSegment) -> list[str]:
    """processing CSV から理由リストを取り出す。"""
    raw = segment.processing.get("review_reasons", "").strip()
    if not raw:
        return [_DEFAULT_REASON]
    reasons = [part.strip() for part in raw.split(",") if part.strip()]
    return reasons or [_DEFAULT_REASON]


def _review_id(segment: SemanticSegment) -> str:
    """書籍とセグメントから安定した review_id を作る。"""
    return f"{segment.book_id}:{segment.segment_id}"


def _book_id_from_review_id(review_id: str) -> str:
    """`build_review_items` が付与する `book_id:segment_id` 形式から書籍 ID を取り出す。"""
    if ":" not in review_id:
        return ""
    return review_id.split(":", 1)[0]


def _image_name_index(pages: Sequence[OcrPage]) -> dict[int, str]:
    """page_number → image_name の索引。"""
    return {page.page_number: page.image_name for page in pages}


def _severity(reasons: Sequence[str]) -> str:
    """理由集合から危険度ラベルを決める。"""
    if any(reason in _HIGH_SEVERITY_REASONS for reason in reasons):
        return "high"
    if reasons == [_DEFAULT_REASON]:
        return "medium"
    return "medium"


def _decision_json_example(item: ReviewItem, *, status: str) -> str:
    """ReviewDecision 相当の記録例を JSON 文字列で返す。"""
    payload = {
        "review_id": item.review_id,
        "segment_id": item.segment_id,
        "status": status,
        "input_hash": "<source-sha256-or-input-hash>",
        "processing_version": "<pipeline-or-prompt-version>",
        "decided_by": "<reviewer-id>",
        "comment": "",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
