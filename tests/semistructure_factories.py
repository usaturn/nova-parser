"""半構造化テストで共有する型付きファクトリ。"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Self

from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
from nova_parser.semistructure.models import (
    Audience,
    BookManifest,
    BookOutline,
    DocumentType,
    NormalizedBlock,
    OcrPage,
    OcrRegion,
    OutlineSection,
    PipelineConfig,
    ProposalSegment,
    SemanticSegment,
    SourceSpan,
    StructureProposal,
    StructureWindow,
)


def make_manifest(**overrides: Any) -> BookManifest:
    """既定値を持つ書籍マニフェストを作る。"""
    values = {
        "book_id": "eg-test",
        "title": "テスト書籍",
        "default_document_type": DocumentType.RULEBOOK,
        "default_audience": Audience.SHARED,
    }
    values.update(overrides)
    return BookManifest(**values)


def make_region(rect_id: str = "r1", text: str = "本文", **overrides: Any) -> OcrRegion:
    """既定値を持つOCR領域を作る。"""
    page_number = overrides.pop("page", 22)
    default_draw_order = int(rect_id[1:]) - 1 if rect_id.startswith("r") and rect_id[1:].isdigit() else 0
    rectangle = overrides.pop(
        "rectangle",
        Rectangle(
            rect_id=rect_id,
            draw_order=overrides.pop("draw_order", default_draw_order),
            x=0,
            y=0,
            width=100,
            height=100,
        ),
    )
    values = {
        "book_id": "eg-test",
        "page_number": page_number,
        "image_name": f"p{page_number:03}.png",
        "rectangle": rectangle,
        "raw_text": text,
        "ocr_status": "done",
    }
    values.update(overrides)
    return OcrRegion(**values)


def make_page(text: str = "本文", **overrides: Any) -> OcrPage:
    """既定値を持つOCRページを作る。"""
    page_number = overrides.pop("page", 22)
    regions = overrides.pop("regions", None)
    values = {
        "book_id": "eg-test",
        "page_number": page_number,
        "image_name": f"p{page_number:03}.png",
        "image_width": 1000,
        "image_height": 1400,
        "regions": regions if regions is not None else [make_region(text=text, page=page_number)],
        "source_sha256": f"sha256:{'0' * 64}",
        "inherited_audience": Audience.SHARED,
    }
    values.update(overrides)
    return OcrPage(**values)


def make_block(block_id: str = "b1", text: str = "本文", **overrides: Any) -> NormalizedBlock:
    """既定値を持つ正規化ブロックを作る。"""
    page = overrides.pop("page", 22)
    rect_id = overrides.pop("rect_id", block_id.replace("b", "r", 1))
    default_draw_order = int(block_id[1:]) - 1 if block_id.startswith("b") and block_id[1:].isdigit() else 0
    values = {
        "block_id": block_id,
        "book_id": "eg-test",
        "page": page,
        "draw_order": default_draw_order,
        "raw_text": text,
        "normalized_text": text,
        "source_spans": [SourceSpan(page=page, rect_id=rect_id, start=0, end=len(text))],
        "inherited_audience": Audience.SHARED,
    }
    values.update(overrides)
    return NormalizedBlock(**values)


def make_proposal(block_ids: list[str] | None = None, **overrides: Any) -> StructureProposal:
    """既定値を持つ構造提案を作る。"""
    segment_overrides = overrides.pop("segment", {})
    segment_values = {
        "block_ids": block_ids if block_ids is not None else ["b1"],
        "section_path": ["テスト節"],
        "content_type": "rule.explanation",
        "audience": Audience.SHARED,
    }
    segment_values.update(segment_overrides)
    values = {
        "segments": [ProposalSegment(**segment_values)],
        "classifier_id": "fake-classifier",
        "prompt_contract_version": "test-v1",
        "input_sha256": f"sha256:{'0' * 64}",
    }
    values.update(overrides)
    return StructureProposal(**values)


def make_segment(
    segment_id: str = "s1",
    audience: Audience = Audience.SHARED,
    **overrides: Any,
) -> SemanticSegment:
    """既定値を持つ正本セグメントを作る。"""
    text = overrides.pop("normalized_text", "本文")
    raw_text = overrides.pop("raw_text", text)
    spans = overrides.pop(
        "spans",
        [SourceSpan(page=22, rect_id="r1", start=0, end=len(raw_text))],
    )
    values = {
        "segment_id": segment_id,
        "book_id": "eg-test",
        "document_type": DocumentType.RULEBOOK,
        "section_path": ["テスト節"],
        "content_type": "rule.explanation",
        "audience": audience,
        "inherited_audience": audience,
        "source_spans": spans,
        "raw_text": raw_text,
        "normalized_text": text,
    }
    values.update(overrides)
    return SemanticSegment(**values)


def make_window(block_ids: list[str] | None = None, **overrides: Any) -> StructureWindow:
    """指定ID順のブロックを持つ分類窓を作る。"""
    blocks = overrides.pop("blocks", None)
    center_page = overrides.pop("center_page", overrides.pop("page", 22))
    if blocks is None:
        blocks = [
            make_block(block_id, rect_id=f"r{index}", page=center_page)
            for index, block_id in enumerate(block_ids or ["b1"], start=1)
        ]
    allowed_block_ids = overrides.pop(
        "allowed_block_ids",
        [block.block_id for block in blocks if block.page == center_page],
    )
    values = {
        "center_page": center_page,
        "context_blocks": blocks,
        "allowed_block_ids": allowed_block_ids,
    }
    values.update(overrides)
    return StructureWindow(**values)


def make_config(root: Path, **overrides: Any) -> PipelineConfig:
    """一時ディレクトリ配下のパイプライン設定を作る。"""
    values = {
        "manifest_path": root / "manifest.json",
        "input_dir": root / "input",
        "output_dir": root / "out",
    }
    values.update(overrides)
    return PipelineConfig(**values)


def write_region_fixture(path: Path, *, image_name: str, text: str = "本文") -> None:
    """実際のImageSession形式でregions.json fixtureを保存する。"""
    rectangle = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=100, height=100)
    session = ImageSession(
        image_name=image_name,
        image_width=1000,
        image_height=1400,
        regions=[RegionRecord(rectangle=rectangle, text=text, ocr_status="done")],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session.model_dump_json(), encoding="utf-8")


class FakeClassifier:
    """成功とページ単位失敗を切り替えられる決定的な偽分類器。"""

    classifier_id = "fake-classifier"

    def __init__(self, fail_page: int | None = None) -> None:
        self._fail_page = fail_page

    @classmethod
    def valid(cls) -> Self:
        """常に有効な提案を返す分類器を作る。"""
        return cls()

    @classmethod
    def fail_on_page(cls, page: int) -> Self:
        """指定ページを含む窓だけ失敗する分類器を作る。"""
        return cls(fail_page=page)

    def infer_outline(self, blocks: Sequence[NormalizedBlock]) -> BookOutline:
        """入力ブロックの範囲を覆う決定的なアウトラインを返す。"""
        pages = [block.page for block in blocks]
        section = OutlineSection(
            title="テスト章",
            start_page=min(pages),
            end_page=max(pages),
            default_content_type="unknown",
        )
        return BookOutline(book_id=blocks[0].book_id, sections=[section])

    def classify(self, window: StructureWindow) -> StructureProposal:
        """入力ブロックを順番どおり1セグメントとして返す。"""
        if self._fail_page is not None and window.center_page == self._fail_page:
            raise RuntimeError("classifier failure")
        return make_proposal(block_ids=window.allowed_block_ids)
