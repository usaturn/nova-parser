"""原文被覆・参照整合・親子循環・プレイヤー可視性の検証。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from nova_parser.semistructure.models import (
    Audience,
    OcrPage,
    OcrRegion,
    SemanticSegment,
    SourceSpan,
)

ValidationCode = Literal[
    "source_gap",
    "source_overlap",
    "invalid_source_ref",
    "source_order_reversal",
    "parent_cycle",
    "gm_audience_visible",
    "unknown_audience_visible",
]


class ValidationError(BaseModel):
    """1件の検証失敗。"""

    code: ValidationCode
    message: str = Field(min_length=1)
    segment_id: str | None = None
    page: int | None = None
    rect_id: str | None = None


class ValidationReport(BaseModel):
    """コーパスまたは可視性検証の集約結果。"""

    coverage_ratio: float = Field(ge=0.0, le=1.0)
    errors: list[ValidationError] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """エラーが無いとき True。"""
        return not self.errors


def validate_corpus(
    pages: Sequence[OcrPage],
    segments: Sequence[SemanticSegment],
) -> ValidationReport:
    """OCR原文と正本セグメントの被覆・参照・順序・親子を検証する。

    各 `(page, rect_id)` について原文長 `[0, len(raw_text))` と全 `source_spans`
    の和集合を比較する。空白や改行も被覆対象に含める。
    """
    region_index = _build_region_index(pages)
    errors: list[ValidationError] = []

    # 領域ごとに被覆ビットを集約する
    covered: dict[tuple[int, str], list[bool]] = {
        key: [False] * len(region.raw_text) for key, region in region_index.items()
    }
    # 同一文字への複数被覆を検出するためカウントも持つ
    cover_counts: dict[tuple[int, str], list[int]] = {
        key: [0] * len(region.raw_text) for key, region in region_index.items()
    }

    for segment in segments:
        errors.extend(_check_source_order(segment))
        for span in segment.source_spans:
            key = (span.page, span.rect_id)
            region = region_index.get(key)
            if region is None:
                errors.append(
                    ValidationError(
                        code="invalid_source_ref",
                        message=f"存在しない領域を参照しています: page={span.page} rect_id={span.rect_id}",
                        segment_id=segment.segment_id,
                        page=span.page,
                        rect_id=span.rect_id,
                    )
                )
                continue
            text_len = len(region.raw_text)
            if span.start >= text_len or span.end > text_len:
                errors.append(
                    ValidationError(
                        code="invalid_source_ref",
                        message=(f"範囲が原文長を超えています: [{span.start}, {span.end}) / len={text_len}"),
                        segment_id=segment.segment_id,
                        page=span.page,
                        rect_id=span.rect_id,
                    )
                )
                # 範囲内に収まる部分だけ被覆へ加算する
                start = min(span.start, text_len)
                end = min(span.end, text_len)
            else:
                start = span.start
                end = span.end
            for index in range(start, end):
                cover_counts[key][index] += 1
                covered[key][index] = True

    total_chars = 0
    covered_chars = 0
    for key, region in region_index.items():
        flags = covered[key]
        counts = cover_counts[key]
        total_chars += len(region.raw_text)
        covered_chars += sum(1 for flag in flags if flag)

        gap_ranges = _uncovered_ranges(flags)
        for gap_start, gap_end in gap_ranges:
            errors.append(
                ValidationError(
                    code="source_gap",
                    message=f"原文が被覆されていません: [{gap_start}, {gap_end})",
                    page=key[0],
                    rect_id=key[1],
                )
            )

        overlap_ranges = _overlap_ranges(counts)
        for overlap_start, overlap_end in overlap_ranges:
            errors.append(
                ValidationError(
                    code="source_overlap",
                    message=f"source_spans が重複しています: [{overlap_start}, {overlap_end})",
                    page=key[0],
                    rect_id=key[1],
                )
            )

    errors.extend(_check_parent_cycles(segments))

    if total_chars == 0:
        coverage_ratio = 1.0
    else:
        coverage_ratio = covered_chars / total_chars

    return ValidationReport(coverage_ratio=coverage_ratio, errors=errors)


def validate_player_visibility(segments: Sequence[SemanticSegment]) -> ValidationReport:
    """プレイヤー向け導出に載せてはいけない audience を検出する。

    `audience=gm` と `audience=unknown` をエラーとして報告する。
    被覆率は可視性検証の対象外のため 1.0 を返す。
    """
    errors: list[ValidationError] = []
    for segment in segments:
        if segment.audience == Audience.GM:
            errors.append(
                ValidationError(
                    code="gm_audience_visible",
                    message="GM 限定セグメントがプレイヤー向け出力に含まれています",
                    segment_id=segment.segment_id,
                )
            )
        elif segment.audience == Audience.UNKNOWN:
            errors.append(
                ValidationError(
                    code="unknown_audience_visible",
                    message="audience が unknown のセグメントがプレイヤー向け出力に含まれています",
                    segment_id=segment.segment_id,
                )
            )
    return ValidationReport(coverage_ratio=1.0, errors=errors)


def _build_region_index(pages: Sequence[OcrPage]) -> dict[tuple[int, str], OcrRegion]:
    """(page_number, rect_id) → OcrRegion の索引を作る。"""
    index: dict[tuple[int, str], OcrRegion] = {}
    for page in pages:
        for region in page.regions:
            index[(region.page_number, region.rect_id)] = region
    return index


def _check_source_order(segment: SemanticSegment) -> list[ValidationError]:
    """同一セグメント内の source_spans が読み順で逆転していないか検査する。"""
    prev: SourceSpan | None = None
    for span in segment.source_spans:
        if prev is not None:
            reversed_page = span.page < prev.page
            reversed_same_rect = span.page == prev.page and span.rect_id == prev.rect_id and span.start < prev.start
            if reversed_page or reversed_same_rect:
                return [
                    ValidationError(
                        code="source_order_reversal",
                        message=(
                            f"source_spans の順序が逆転しています: "
                            f"({prev.page},{prev.rect_id},{prev.start}) → "
                            f"({span.page},{span.rect_id},{span.start})"
                        ),
                        segment_id=segment.segment_id,
                        page=span.page,
                        rect_id=span.rect_id,
                    )
                ]
        prev = span
    return []


def _check_parent_cycles(segments: Sequence[SemanticSegment]) -> list[ValidationError]:
    """parent_segment_id の循環を検出する。"""
    parents = {
        segment.segment_id: segment.parent_segment_id for segment in segments if segment.parent_segment_id is not None
    }
    known_ids = {segment.segment_id for segment in segments}
    errors: list[ValidationError] = []
    reported: set[str] = set()

    for segment_id in parents:
        if segment_id in reported:
            continue
        seen: list[str] = []
        current: str | None = segment_id
        while current is not None and current in known_ids:
            if current in seen:
                cycle_start = seen.index(current)
                cycle_nodes = seen[cycle_start:]
                for node in cycle_nodes:
                    if node not in reported:
                        errors.append(
                            ValidationError(
                                code="parent_cycle",
                                message=f"親子関係が循環しています: {' → '.join(cycle_nodes + [current])}",
                                segment_id=node,
                            )
                        )
                        reported.add(node)
                break
            seen.append(current)
            current = parents.get(current)
    return errors


def _uncovered_ranges(flags: Sequence[bool]) -> list[tuple[int, int]]:
    """False 連続区間を半開区間のリストで返す。"""
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    for index, flag in enumerate(flags):
        if not flag and start is None:
            start = index
        elif flag and start is not None:
            ranges.append((start, index))
            start = None
    if start is not None:
        ranges.append((start, len(flags)))
    return ranges


def _overlap_ranges(counts: Sequence[int]) -> list[tuple[int, int]]:
    """2回以上被覆された連続区間を半開区間のリストで返す。"""
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    for index, count in enumerate(counts):
        if count >= 2 and start is None:
            start = index
        elif count < 2 and start is not None:
            ranges.append((start, index))
            start = None
    if start is not None:
        ranges.append((start, len(counts)))
    return ranges
