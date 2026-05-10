"""矩形領域のクロップおよび PNG バイト列変換ユーティリティ。"""

from __future__ import annotations

import io

from PIL import Image

from nova_parser.regional_ocr.models import Rectangle


def crop_rectangle(image: Image.Image, rect: Rectangle) -> Image.Image:
    """画像から矩形領域を切り出して返す。画像境界でクランプし、面積ゼロの場合は ValueError を raise する。"""
    clamped_left = max(0, rect.x)
    clamped_top = max(0, rect.y)
    clamped_right = min(image.width, rect.x + rect.width)
    clamped_bottom = min(image.height, rect.y + rect.height)

    if (clamped_right - clamped_left) <= 0 or (clamped_bottom - clamped_top) <= 0:
        raise ValueError("クランプ後の矩形領域の面積がゼロになりました")

    return image.crop((clamped_left, clamped_top, clamped_right, clamped_bottom))


def to_png_bytes(image: Image.Image) -> bytes:
    """Pillow Image を PNG フォーマットのバイト列に変換して返す。"""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
