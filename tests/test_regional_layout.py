"""layout.py 純粋関数のユニットテスト。座標は 1000x1000 画像を前提とする。"""

from __future__ import annotations

from nova_parser.regional_ocr.layout import normalize_rects
from nova_parser.regional_ocr.models import BlockRect

W, H = 1000, 1000


def _r(x: int, y: int, w: int, h: int) -> BlockRect:
    return BlockRect(x=x, y=y, width=w, height=h)


class TestNormalizeRects:
    def test_clamps_to_image_bounds(self):
        assert normalize_rects([_r(990, 100, 50, 50)], W, H) == [_r(990, 100, 10, 50)]

    def test_drops_degenerate_after_clamp(self):
        assert normalize_rects([_r(1000, 100, 5, 5)], W, H) == []

    def test_drops_contained_rect_keeping_covering_one(self):
        outer = _r(100, 100, 200, 200)
        inner = _r(120, 120, 50, 50)
        assert normalize_rects([inner, outer], W, H) == [outer]

    def test_keeps_partially_crossing_rects(self):
        a = _r(100, 100, 100, 100)
        b = _r(150, 150, 100, 100)
        assert normalize_rects([a, b], W, H) == [a, b]

    def test_merges_near_identical_rects_into_one(self):
        a = _r(100, 100, 100, 100)
        b = _r(101, 101, 100, 100)
        assert len(normalize_rects([a, b], W, H)) == 1

    def test_output_is_sorted_top_then_left(self):
        a = _r(500, 300, 100, 100)
        b = _r(100, 100, 100, 100)
        assert normalize_rects([a, b], W, H) == [b, a]
