"""Cloud Vision API を使った OCR クライアントユーティリティ。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from google.auth import exceptions as auth_exc
from google.cloud import vision

from nova_parser.regional_ocr.crop import crop_rectangle, to_png_bytes
from nova_parser.regional_ocr.errors import AdcNotConfiguredError, OcrBackendError
from nova_parser.regional_ocr.models import Rectangle

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
