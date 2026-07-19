"""regional OCR出力を半構造化パイプラインへ取り込む入力境界。"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from nova_parser.regional_ocr.models import ImageSession, RegionRecord
from nova_parser.semistructure.models import Audience, BookManifest, OcrPage, OcrRegion


def load_pages(input_dir: Path, manifest: BookManifest) -> list[OcrPage]:
    """OCRセッションを検査し、ページ番号順のOCRページへ変換する。"""
    page_pattern = re.compile(manifest.page_pattern)
    pages_by_number: dict[int, OcrPage] = {}

    for path in sorted(input_dir.glob(manifest.input_glob)):
        page_number = _extract_page_number(path, page_pattern)
        if page_number in pages_by_number:
            raise ValueError(f"ページ番号が重複しています: {page_number}")

        source = path.read_bytes()
        session = ImageSession.model_validate_json(source)
        regions = [
            _convert_region(region, session, manifest.book_id, page_number)
            for region in sorted(session.regions, key=lambda item: item.rectangle.draw_order)
        ]
        pages_by_number[page_number] = OcrPage(
            book_id=manifest.book_id,
            page_number=page_number,
            image_name=session.image_name,
            image_width=session.image_width,
            image_height=session.image_height,
            regions=regions,
            source_sha256=f"sha256:{hashlib.sha256(source).hexdigest()}",
            inherited_audience=_audience_for_page(manifest, page_number),
        )

    return [pages_by_number[page] for page in sorted(pages_by_number)]


def _extract_page_number(path: Path, page_pattern: re.Pattern[str]) -> int:
    match = page_pattern.search(path.name)
    if match is None:
        raise ValueError(f"ファイル名からページ番号を取得できません: {path.name}")
    try:
        return int(match.group("page"))
    except (IndexError, KeyError) as error:
        raise ValueError("page_patternには名前付きグループ 'page' が必要です") from error


def _convert_region(
    region: RegionRecord,
    session: ImageSession,
    book_id: str,
    page_number: int,
) -> OcrRegion:
    rectangle = region.rectangle
    if region.ocr_status != "done":
        raise ValueError(f"OCRが完了していません: {session.image_name} / {rectangle.rect_id} ({region.ocr_status})")
    if region.text is None:
        raise ValueError(f"OCR本文がありません: {session.image_name} / {rectangle.rect_id}")
    if rectangle.right > session.image_width or rectangle.bottom > session.image_height:
        raise ValueError(f"矩形が画像外です: {session.image_name} / {rectangle.rect_id}")

    return OcrRegion(
        book_id=book_id,
        page_number=page_number,
        image_name=session.image_name,
        rectangle=rectangle,
        raw_text=region.text,
        ocr_status=region.ocr_status,
    )


def _audience_for_page(manifest: BookManifest, page_number: int) -> Audience:
    audience = manifest.default_audience
    for override in manifest.audience_overrides:
        if override.start_page <= page_number <= override.end_page:
            audience = override.audience
    return audience
