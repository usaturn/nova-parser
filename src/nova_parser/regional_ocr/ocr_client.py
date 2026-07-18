"""Cloud Vision API を使った OCR クライアントユーティリティ。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from google.auth import exceptions as auth_exc
from google.cloud import vision

from nova_parser.regional_ocr.crop import crop_rectangle, to_png_bytes
from nova_parser.regional_ocr.errors import AdcNotConfiguredError, OcrBackendError
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

    return response.full_text_annotation.text or ""


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
