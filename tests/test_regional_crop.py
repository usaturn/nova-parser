"""regional_ocr.crop のユニットテスト（AC-11〜AC-14）。"""

from __future__ import annotations

import pytest
from PIL import Image

from nova_parser.regional_ocr.crop import crop_rectangle, to_png_bytes
from nova_parser.regional_ocr.models import Rectangle

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_image(width: int, height: int, mode: str = "RGB") -> Image.Image:
    """テスト用のメモリ上の画像を生成する。"""
    return Image.new(mode, (width, height), color=(128, 128, 128))


def _make_rect(*, x: int, y: int, width: int, height: int, rect_id: str = "r1", draw_order: int = 0) -> Rectangle:
    """Rectangle を簡潔に生成するヘルパー。"""
    return Rectangle(rect_id=rect_id, draw_order=draw_order, x=x, y=y, width=width, height=height)


# ---------------------------------------------------------------------------
# AC-11: 正常なクロップ（画像内に収まる）
# ---------------------------------------------------------------------------


def test_crop_rectangle_returns_correct_size_for_valid_region():
    """AC-11: crop_rectangle に 1000x800 の Pillow Image と x=100, y=200, width=300, height=400 の
    Rectangle を渡したとき、返却 Image のサイズが (300, 400) となる。
    """
    image = _make_image(1000, 800)
    rect = _make_rect(x=100, y=200, width=300, height=400)
    result = crop_rectangle(image, rect)
    assert result.size == (300, 400)


# ---------------------------------------------------------------------------
# AC-12: クランプあり（部分的に画像外）だが面積ゼロにならない
# ---------------------------------------------------------------------------


def test_crop_rectangle_clamps_to_image_boundary_without_value_error():
    """AC-12: crop_rectangle に 100x100 の Pillow Image と x=90, y=90, width=50, height=50 の
    Rectangle を渡したとき（クランプにより 10x10 に縮小）、返却 Image のサイズが (10, 10) となる。
    """
    image = _make_image(100, 100)
    rect = _make_rect(x=90, y=90, width=50, height=50)
    result = crop_rectangle(image, rect)
    assert result.size == (10, 10)


# ---------------------------------------------------------------------------
# AC-13: クランプ後に面積ゼロ → ValueError
# ---------------------------------------------------------------------------


def test_crop_rectangle_raises_value_error_when_clamped_area_is_zero():
    """AC-13: crop_rectangle に 100x100 の Pillow Image と x=100, y=0, width=10, height=10 の
    Rectangle を渡したとき（クランプ後に width=0 となり面積ゼロ）、ValueError が raise される。
    クランプ判定は `(clamped_right - clamped_left) <= 0 or (clamped_bottom - clamped_top) <= 0`。
    """
    image = _make_image(100, 100)
    rect = _make_rect(x=100, y=0, width=10, height=10)
    with pytest.raises(ValueError):
        crop_rectangle(image, rect)


# ---------------------------------------------------------------------------
# AC-14: to_png_bytes の返却値が PNG バイト列
# ---------------------------------------------------------------------------


def test_to_png_bytes_returns_bytes_with_png_signature():
    """AC-14: to_png_bytes に Pillow Image を渡したとき、返却値が bytes 型であり、
    先頭 8 バイトが PNG シグネチャ (b'\\x89PNG\\r\\n\\x1a\\n') と一致する。
    """
    image = _make_image(50, 50)
    result = to_png_bytes(image)
    assert isinstance(result, bytes)
    assert result[:8] == b"\x89PNG\r\n\x1a\n"
