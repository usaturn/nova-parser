"""OCR領域内だけを対象にした、追跡可能で決定的な改行正規化。"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from nova_parser.semistructure.models import (
    NormalizationOperation,
    NormalizedBlock,
    OcrPage,
    OcrRegion,
    SourceSpan,
)

HARD_BREAK_PREFIXES = ("■", "●", "▼", "◆", "◇", "・")
SENTENCE_ENDINGS = ("。", "！", "？", "!", "?", "：", ":")

_TABLE_SPACING = re.compile(r"[ \u3000]{2,}")
_PHYSICAL_LINE = re.compile(r"(.*?)(\r\n|\r|\n|$)")
_SHORT_LINE_LENGTH = 4


@dataclass(frozen=True, slots=True)
class PhysicalLine:
    """OCR領域内の改行を除いた1物理行と原文オフセット。"""

    page: int
    rect_id: str
    text: str
    start: int
    end: int
    line_break: str = "\n"


@dataclass(frozen=True, slots=True)
class JoinDecision:
    """隣接物理行に対する決定的な結合判定。"""

    should_join: bool
    rule_id: str | None = None
    review_reason: str | None = None


def should_keep_break(left: str, right: str) -> bool:
    """明示的な境界らしい改行を保持する。"""
    return (
        not left
        or not right
        or left.endswith(SENTENCE_ENDINGS)
        or right.startswith(HARD_BREAK_PREFIXES)
        or left.startswith(HARD_BREAK_PREFIXES)
    )


def classify_line_join(left: PhysicalLine, right: PhysicalLine) -> JoinDecision:
    """隣接行を、安全な同一領域内の語中改行だけに限定して分類する。

    ページまたぎ・領域またぎは結合しないが、正規化が領域内だけを対象にするため
    これは通常の安全な非結合であり、レビュー理由にはしない。
    レビュー理由は表・箇条書き・短行など「人が見た方が良い曖昧境界」に限る。
    """
    if left.page != right.page or left.rect_id != right.rect_id:
        return JoinDecision(should_join=False)
    if left.text.startswith(HARD_BREAK_PREFIXES) or right.text.startswith(HARD_BREAK_PREFIXES):
        return JoinDecision(should_join=False, review_reason="bullet_list_structure")
    if _TABLE_SPACING.search(left.text) or _TABLE_SPACING.search(right.text):
        return JoinDecision(should_join=False, review_reason="table_like_spacing")
    if not left.text or not right.text or left.text.endswith(SENTENCE_ENDINGS):
        return JoinDecision(should_join=False)
    if min(len(left.text), len(right.text)) <= _SHORT_LINE_LENGTH:
        return JoinDecision(should_join=False, review_reason="short_independent_line")
    if should_keep_break(left.text, right.text):
        return JoinDecision(should_join=False)
    return JoinDecision(should_join=True, rule_id="ja-word-wrap-v1")


def normalize_pages(pages: Sequence[OcrPage]) -> list[NormalizedBlock]:
    """ページと領域を安定順に並べ、各領域内の安全な改行だけを除去する。

    領域・ページの単なる隣接は review_reasons にしない（結合は領域内のみで、
    隣接境界を REQUIRED 化するとキューが溢れるため）。
    """
    blocks: list[NormalizedBlock] = []

    for page in sorted(pages, key=lambda item: item.page_number):
        for region in sorted(page.regions, key=lambda item: item.draw_order):
            if not region.raw_text:
                continue
            blocks.append(_normalize_region(page, region))

    return blocks


def _normalize_region(page: OcrPage, region: OcrRegion) -> NormalizedBlock:
    lines = _physical_lines(region)
    normalized_parts: list[str] = []
    operations: list[NormalizationOperation] = []
    review_reasons: list[str] = []

    for index, line in enumerate(lines):
        normalized_parts.append(line.text)
        if index == len(lines) - 1:
            normalized_parts.append(line.line_break)
            continue

        decision = classify_line_join(line, lines[index + 1])
        if decision.should_join:
            operations.append(
                NormalizationOperation(
                    type="join_physical_lines",
                    rule_id=decision.rule_id or "ja-word-wrap-v1",
                    details={
                        "left_end": str(line.end),
                        "right_start": str(lines[index + 1].start),
                    },
                )
            )
        else:
            normalized_parts.append(line.line_break)
            if decision.review_reason and decision.review_reason not in review_reasons:
                review_reasons.append(decision.review_reason)

    return NormalizedBlock(
        block_id=f"{page.book_id}:p{page.page_number:03}:{region.rect_id}",
        book_id=page.book_id,
        page=page.page_number,
        draw_order=region.draw_order,
        raw_text=region.raw_text,
        normalized_text="".join(normalized_parts),
        source_spans=[
            SourceSpan(
                page=page.page_number,
                rect_id=region.rect_id,
                start=0,
                end=len(region.raw_text),
            )
        ],
        operations=operations,
        inherited_audience=page.inherited_audience,
        review_reasons=review_reasons,
    )


def _physical_lines(region: OcrRegion) -> list[PhysicalLine]:
    lines: list[PhysicalLine] = []
    for match in _PHYSICAL_LINE.finditer(region.raw_text):
        text, line_break = match.groups()
        if not text and not line_break and match.start() == len(region.raw_text):
            break
        lines.append(
            PhysicalLine(
                page=region.page_number,
                rect_id=region.rect_id,
                text=text,
                start=match.start(),
                end=match.start() + len(text),
                line_break=line_break,
            )
        )
    return lines
