"""layout.py 純粋関数のユニットテスト。座標は 1000x1000 画像を前提とする。"""

from __future__ import annotations

from nova_parser.regional_ocr.layout import drop_perimeter_rects, normalize_rects, split_bands
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


class TestDropPerimeterRects:
    def test_drops_isolated_page_number_at_bottom(self):
        body = _r(100, 100, 800, 700)
        page_no = _r(480, 960, 40, 25)
        assert drop_perimeter_rects([body, page_no], W, H) == [body]

    def test_keeps_rect_extending_beyond_perimeter_band(self):
        # 上端 7% 帯（0..70px）をまたいで本文側へ伸びる矩形は除外しない
        crossing = _r(100, 40, 300, 60)
        assert drop_perimeter_rects([crossing], W, H) == [crossing]

    def test_keeps_band_rect_connected_to_body(self):
        # 帯内でも本文と縦に連続していれば除外しない
        caption = _r(100, 20, 300, 40)
        body = _r(100, 65, 300, 400)
        assert drop_perimeter_rects([caption, body], W, H) == [caption, body]

    def test_keeps_tall_rect_inside_band(self):
        # 高さが「小矩形」閾値を超えるものは外周要素とみなさない
        tall = _r(100, 5, 300, 60)
        assert drop_perimeter_rects([tall], W, H) == [tall]

    def test_drops_isolated_header_at_top(self):
        header = _r(700, 15, 200, 30)
        body = _r(100, 200, 800, 600)
        assert drop_perimeter_rects([header, body], W, H) == [body]


class TestSplitBands:
    def test_splits_at_gap_common_to_all_columns(self):
        upper = [_r(100, 100, 400, 200), _r(520, 100, 400, 200)]
        lower = [_r(100, 340, 400, 200), _r(520, 340, 400, 200)]
        bands = split_bands(upper + lower, W, H)
        assert len(bands) == 2
        assert sorted(b.y for b in bands[0]) == [100, 100]
        assert sorted(b.y for b in bands[1]) == [340, 340]

    def test_gap_only_in_narrow_sidebar_does_not_split(self):
        # 本文列が連続していれば、欄外注釈内の大きな空白では領域分割しない
        main = _r(100, 100, 350, 600)
        sidebar_top = _r(600, 100, 150, 100)
        sidebar_bottom = _r(600, 400, 150, 100)
        bands = split_bands([main, sidebar_top, sidebar_bottom], W, H)
        assert len(bands) == 1
        assert len(bands[0]) == 3

    def test_band_heading_spanning_two_columns_becomes_own_band(self):
        upper = [_r(100, 100, 400, 200), _r(520, 100, 400, 200)]
        heading = _r(100, 305, 820, 40)
        lower = [_r(100, 350, 400, 200), _r(520, 350, 400, 200)]
        bands = split_bands(upper + [heading] + lower, W, H)
        assert len(bands) == 3
        assert bands[1] == [heading]

    def test_single_column_page_is_one_band_despite_gaps(self):
        # 暫定列が 1 のページでは空白による分割を行わない（縦統合は Task 7 の担当）
        rects = [_r(100, 100, 800, 150), _r(100, 400, 800, 150)]
        bands = split_bands(rects, W, H)
        assert len(bands) == 1
