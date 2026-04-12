"""crop モード: カード領域を検出・切り出す。

Gemini Vision によるカード検出と、Document AI OCR ブロック座標による検出の両方をサポートする。
Document AI の型に直接依存せず、duck typing で Document オブジェクトを受け取る。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image


@dataclass
class CardRegion:
    """検出されたカード領域。"""

    left: int
    top: int
    right: int
    bottom: int
    confidence: float
    text_snippet: str


@dataclass
class PageBlocks:
    """ページのブロック情報とページ寸法。"""

    regions: list[CardRegion]
    page_width: int
    page_height: int


def detect_cards_with_gemini(image_path: Path) -> list[CardRegion]:
    """Gemini Vision でカード領域を検出し、ピクセル座標の CardRegion リストを返す。"""
    from google.genai import types

    from nova_parser.ocr import MIME_TYPES, generate_json
    from nova_parser.prompts import CARD_DETECT_PROMPT

    mime_type = MIME_TYPES[image_path.suffix.lower()]
    image_bytes = image_path.read_bytes()

    result = generate_json(
        [
            CARD_DETECT_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
    )

    cards_raw = result.get("cards", []) if isinstance(result, dict) else []
    if not cards_raw:
        return []

    with Image.open(image_path) as img:
        img_width, img_height = img.size

    regions: list[CardRegion] = []
    for card in cards_raw:
        left = int(card["left"] * img_width)
        top = int(card["top"] * img_height)
        right = int(card["right"] * img_width)
        bottom = int(card["bottom"] * img_height)
        label = card.get("label", "")
        regions.append(CardRegion(left, top, right, bottom, confidence=1.0, text_snippet=label))

    return regions


def extract_block_regions(document: Any, page_index: int = 0) -> PageBlocks:
    """Document の block から PageBlocks（CardRegion リスト + ページ寸法）を抽出する。"""
    page = document.pages[page_index]
    width = page.dimension.width
    height = page.dimension.height
    text = document.text

    regions: list[CardRegion] = []
    for block in page.blocks:
        vertices = block.layout.bounding_poly.normalized_vertices
        if len(vertices) < 4:
            continue

        left = int(vertices[0].x * width)
        top = int(vertices[0].y * height)
        right = int(vertices[2].x * width)
        bottom = int(vertices[2].y * height)

        snippet = ""
        for segment in block.layout.text_anchor.text_segments:
            start = int(segment.start_index)
            end = int(segment.end_index)
            snippet += text[start:end]
        snippet = snippet[:100]

        regions.append(CardRegion(left, top, right, bottom, block.layout.confidence, snippet))

    return PageBlocks(regions=regions, page_width=int(width), page_height=int(height))


def cluster_blocks(
    regions: list[CardRegion],
    page_width: int,
    page_height: int,
    gap_threshold: float = 0.02,
) -> list[CardRegion]:
    """近接するブロックをクラスタリングして統合した領域を返す。

    gap_threshold: ページ高さに対する垂直方向ギャップの比率閾値。
    """
    if not regions:
        return []

    sorted_regions = sorted(regions, key=lambda r: (r.top, r.left))
    gap_px = int(page_height * gap_threshold)

    groups: list[list[CardRegion]] = [[sorted_regions[0]]]

    for region in sorted_regions[1:]:
        merged = False
        for group in groups:
            group_left = min(r.left for r in group)
            group_right = max(r.right for r in group)
            group_bottom = max(r.bottom for r in group)

            vertical_close = region.top - group_bottom <= gap_px
            h_overlap_start = max(group_left, region.left)
            h_overlap_end = min(group_right, region.right)
            h_overlap = max(0, h_overlap_end - h_overlap_start)
            region_width = region.right - region.left
            horizontal_overlap = h_overlap / region_width if region_width > 0 else 0

            if vertical_close and horizontal_overlap > 0.3:
                group.append(region)
                merged = True
                break

        if not merged:
            groups.append([region])

    result: list[CardRegion] = []
    for group in groups:
        left = min(r.left for r in group)
        top = min(r.top for r in group)
        right = max(r.right for r in group)
        bottom = max(r.bottom for r in group)
        avg_conf = sum(r.confidence for r in group) / len(group)
        snippet = group[0].text_snippet
        result.append(CardRegion(left, top, right, bottom, avg_conf, snippet))

    return result


def filter_card_candidates(
    regions: list[CardRegion],
    page_width: int,
    page_height: int,
    min_area_ratio: float = 0.05,
    max_area_ratio: float = 0.80,
) -> list[CardRegion]:
    """面積比率でカード候補をフィルタリングする。"""
    page_area = page_width * page_height
    if page_area == 0:
        return []

    result: list[CardRegion] = []
    for r in regions:
        area = (r.right - r.left) * (r.bottom - r.top)
        ratio = area / page_area
        if min_area_ratio <= ratio <= max_area_ratio:
            result.append(r)

    return result


def crop_cards(
    image: Image.Image,
    regions: list[CardRegion],
    padding: int = 15,
) -> list[tuple[CardRegion, Image.Image]]:
    """画像から各領域をパディング付きでクロップする。"""
    img_width, img_height = image.size

    result: list[tuple[CardRegion, Image.Image]] = []
    for region in regions:
        left = max(0, region.left - padding)
        top = max(0, region.top - padding)
        right = min(img_width, region.right + padding)
        bottom = min(img_height, region.bottom + padding)
        cropped = image.crop((left, top, right, bottom))
        result.append((region, cropped))

    return result


def detect_and_crop_cards(
    image: Image.Image,
    document: Any,
    *,
    min_area_ratio: float = 0.05,
    max_area_ratio: float = 0.80,
    padding: int = 15,
) -> list[tuple[CardRegion, Image.Image]]:
    """Document AI の解析結果からカード領域を検出・切り出す。

    クラスタリング・フィルタリング後にクロップする。
    image は呼び出し元で開いた PIL Image、document は process_image_with_documentai() の戻り値。
    """
    page_blocks = extract_block_regions(document)
    clusters = cluster_blocks(page_blocks.regions, page_blocks.page_width, page_blocks.page_height)
    candidates = filter_card_candidates(
        clusters, page_blocks.page_width, page_blocks.page_height, min_area_ratio, max_area_ratio
    )

    if not candidates:
        return []

    return crop_cards(image, candidates, padding)
