"""Cloud Vision API を使った OCR クライアントユーティリティ。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from google.auth import exceptions as auth_exc
from google.cloud import vision

from nova_parser.regional_ocr.crop import crop_rectangle, to_png_bytes
from nova_parser.regional_ocr.errors import AdcNotConfiguredError, OcrBackendError
from nova_parser.regional_ocr.layout import COLUMN_X_OVERLAP_RATIO
from nova_parser.regional_ocr.models import BlockRect, Rectangle

if TYPE_CHECKING:
    from PIL.Image import Image


def build_vision_client() -> vision.ImageAnnotatorClient:
    """ADC で ImageAnnotatorClient を生成し、認証エラーは AdcNotConfiguredError でラップする。"""
    try:
        return vision.ImageAnnotatorClient()
    except auth_exc.DefaultCredentialsError as exc:
        msg = (
            "Application Default Credentials が設定されていません。"
            "`gcloud auth application-default login` を実行してください。"
        )
        raise AdcNotConfiguredError(msg) from exc


def _block_x_range(block: object) -> tuple[int, int]:
    """OCR block の bounding box の X 範囲 (左端, 右端) を返す。頂点なしは (0, 0)。"""
    bounding_box = getattr(block, "bounding_box", None)
    xs = [getattr(vertex, "x", 0) for vertex in getattr(bounding_box, "vertices", [])]
    if not xs:
        return (0, 0)
    return (min(xs), max(xs))


def _block_right(block: object) -> int:
    """OCR block の bounding box 右端 X 座標を返す。頂点なしは 0。"""
    return _block_x_range(block)[1]


def _block_top(block: object) -> int:
    """OCR block の bounding box 上端 Y 座標を返す。頂点なしは 0。"""
    bounding_box = getattr(block, "bounding_box", None)
    ys = [getattr(vertex, "y", 0) for vertex in getattr(bounding_box, "vertices", [])]
    return min(ys, default=0)


def _same_column(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """2 つの X 範囲が同一列とみなせるか（狭い方の幅に対する重なり率で判定）。"""
    overlap = min(a[1], b[1]) - max(a[0], b[0])
    if overlap <= 0:
        return False
    min_width = min(a[1] - a[0], b[1] - b[0])
    return min_width > 0 and overlap / min_width >= COLUMN_X_OVERLAP_RATIO


def _symbol_break(symbol: object) -> tuple[str, bool]:
    """Cloud Vision の detected break を (文字, symbol の前へ挿入するか) へ変換する。"""
    text_property = getattr(symbol, "property", None)
    detected_break = getattr(text_property, "detected_break", None)
    break_type = getattr(detected_break, "type_", None)
    break_types = vision.TextAnnotation.DetectedBreak.BreakType
    # HYPHEN は「テキストに含まれない行末ハイフン」（行の折り返し）なので改行も伴う
    text = {
        break_types.SPACE: " ",
        break_types.SURE_SPACE: " ",
        break_types.EOL_SURE_SPACE: "\n",
        break_types.LINE_BREAK: "\n",
        break_types.HYPHEN: "-\n",
    }.get(break_type, "")
    return text, bool(getattr(detected_break, "is_prefix", False))


def _block_text(block: object) -> str:
    """OCR block 内の symbol と detected break からテキストを復元する。"""
    parts: list[str] = []
    for paragraph in getattr(block, "paragraphs", []):
        for word in getattr(paragraph, "words", []):
            for symbol in getattr(word, "symbols", []):
                break_text, is_prefix = _symbol_break(symbol)
                symbol_text = getattr(symbol, "text", "")
                parts.extend((break_text, symbol_text) if is_prefix else (symbol_text, break_text))
    return "".join(parts).rstrip()


def _vertical_columns(blocks: list[object]) -> list[list[object]]:
    """block を縦書きの列ごとにまとめ、右の列から順に返す。

    右端 X の降順に走査し、直前の列と X 範囲が重なる block を同じ列へ束ねる。
    画像幅に依存しない重なり率で判定するため、クロップの大きさに左右されない。
    """
    columns: list[list[object]] = []
    spans: list[tuple[int, int]] = []
    for block in sorted(blocks, key=_block_right, reverse=True):
        span = _block_x_range(block)
        if columns and _same_column(spans[-1], span):
            columns[-1].append(block)
            spans[-1] = (min(spans[-1][0], span[0]), max(spans[-1][1], span[1]))
            continue
        columns.append([block])
        spans.append(span)
    return columns


def _vertical_text(annotation: object) -> str:
    """構造化 OCR block を縦書きの読み順（列は右→左、列内は上→下）でテキスト化する。"""
    blocks = [block for page in getattr(annotation, "pages", []) for block in getattr(page, "blocks", [])]
    if not blocks:
        return getattr(annotation, "text", "") or ""
    ordered = [block for column in _vertical_columns(blocks) for block in sorted(column, key=_block_top)]
    return "\n".join(text for block in ordered if (text := _block_text(block))).rstrip()


def ocr_rectangle(
    client: vision.ImageAnnotatorClient,
    image: "Image",
    rect: Rectangle,
    *,
    language_hints: Sequence[str] = ("ja",),
) -> str:
    """画像から rect 領域をクロップし Cloud Vision text_detection で OCR してテキストを返す。"""
    cropped = crop_rectangle(image, rect)
    png_bytes = to_png_bytes(cropped)

    vision_image = vision.Image(content=png_bytes)
    image_context = vision.ImageContext(language_hints=list(language_hints))
    response = client.text_detection(image=vision_image, image_context=image_context)

    if response.error.message:
        msg = f"Cloud Vision API エラー: {response.error.message}"
        raise OcrBackendError(msg)

    annotation = response.full_text_annotation
    if rect.reading_order == "vertical":
        return _vertical_text(annotation)
    return annotation.text or ""


def detect_blocks(
    client: vision.ImageAnnotatorClient,
    image: "Image",
    *,
    language_hints: Sequence[str] = ("ja",),
) -> list[BlockRect]:
    """画像全体を Cloud Vision document_text_detection にかけ、block の矩形一覧を返す。"""
    png_bytes = to_png_bytes(image)

    vision_image = vision.Image(content=png_bytes)
    image_context = vision.ImageContext(language_hints=list(language_hints))
    response = client.document_text_detection(image=vision_image, image_context=image_context)

    if response.error.message:
        msg = f"Cloud Vision API エラー: {response.error.message}"
        raise OcrBackendError(msg)

    annotation = response.full_text_annotation
    pages = annotation.pages if annotation else []
    blocks: list[BlockRect] = []
    for page in pages:
        for block in page.blocks:
            rect = _bounding_box_to_rect(block.bounding_box, image.width, image.height)
            if rect is not None:
                blocks.append(rect)
    return blocks


def _bounding_box_to_rect(bounding_box: object, image_width: int, image_height: int) -> BlockRect | None:
    """bounding_box（回転四角形の可能性あり）を画像境界にクランプした軸平行矩形へ変換する。

    頂点がない場合や、クランプ後に幅・高さが 1px 未満に退化する場合は None を返す。
    """
    vertices = list(bounding_box.vertices)  # type: ignore[attr-defined]
    if not vertices:
        return None
    xs = [getattr(v, "x", 0) for v in vertices]
    ys = [getattr(v, "y", 0) for v in vertices]
    left = max(0, min(xs))
    top = max(0, min(ys))
    right = min(image_width, max(xs))
    bottom = min(image_height, max(ys))
    if right - left < 1 or bottom - top < 1:
        return None
    return BlockRect(x=left, y=top, width=right - left, height=bottom - top)
