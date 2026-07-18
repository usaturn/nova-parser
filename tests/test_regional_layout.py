"""layout.py 純粋関数のユニットテスト。座標は 1000x1000 画像を前提とする。"""

from __future__ import annotations

from nova_parser.regional_ocr.layout import (
    cancel_overmerged,
    compute_vertical_blocks,
    drop_perimeter_rects,
    finalize_blocks,
    normalize_rects,
    split_bands,
    split_columns,
    split_vertical,
)
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


class TestSplitColumns:
    def test_two_columns_by_left_edge(self):
        a = _r(100, 100, 400, 200)
        b = _r(100, 320, 400, 150)
        c = _r(520, 100, 400, 370)
        assert split_columns([a, b, c], W) == [[a, b], [c]]

    def test_narrow_heading_joins_wider_body_column(self):
        # 狭い見出しが、より幅の広い本文列の内側に収まる場合は同一列
        heading = _r(150, 100, 200, 50)
        body = _r(100, 170, 400, 300)
        columns = split_columns([heading, body], W)
        assert len(columns) == 1
        assert sorted(r.y for r in columns[0]) == [100, 170]

    def test_rect_spanning_two_columns_is_independent_block(self):
        col_a = _r(100, 100, 300, 400)
        col_b = _r(600, 100, 300, 400)
        wide = _r(100, 550, 800, 100)
        columns = split_columns([col_a, col_b, wide], W)
        assert [wide] in columns
        assert len(columns) == 3

    def test_single_column_of_wide_rects_stays_one_column(self):
        # 全矩形が幅広（1 段組バンド）の場合は通常クラスタリングで 1 列
        a = _r(100, 100, 800, 150)
        b = _r(100, 300, 800, 150)
        assert split_columns([a, b], W) == [[a, b]]


class TestSplitVertical:
    def test_merges_stacked_paragraphs_in_same_column(self):
        column = [_r(100, 100, 400, 100), _r(100, 220, 400, 100)]
        assert split_vertical(column, column, W, H) == [column]

    def test_narrow_sidebar_merges_across_large_gap(self):
        # 欄外注釈候補（幅 25% 以下）は大きな縦空白を挟んでも統合する
        column = [_r(700, 100, 150, 100), _r(700, 500, 150, 100)]
        assert split_vertical(column, column, W, H) == [column]

    def test_splits_at_row_boundary_shared_with_neighbor_column(self):
        # 2×2 カード: 隣接列にも同じ行境界がある場合は分割する
        column = [_r(100, 100, 300, 150), _r(100, 300, 300, 150)]
        neighbors = [_r(450, 100, 300, 150), _r(450, 300, 300, 150)]
        groups = split_vertical(column, column + neighbors, W, H)
        assert groups == [[column[0]], [column[1]]]

    def test_splits_heading_with_different_width_and_large_gap(self):
        heading = _r(100, 100, 400, 50)
        body = _r(100, 210, 150, 100)
        groups = split_vertical([heading, body], [heading, body], W, H)
        assert groups == [[heading], [body]]

    def test_uncertain_gap_without_evidence_merges(self):
        # 根拠のない空白では分割しない（スペック 8: 単一の空白だけでは分割しない）
        column = [_r(100, 100, 400, 100), _r(100, 260, 400, 100)]
        assert split_vertical(column, column, W, H) == [column]


class TestCancelOvermerged:
    def test_cancels_group_spanning_two_other_columns(self):
        a1 = _r(100, 100, 300, 100)
        a2 = _r(100, 400, 900, 80)  # 統合すると 2 列をまたぐ
        g2 = [_r(450, 100, 300, 100)]
        g3 = [_r(800, 100, 150, 100)]
        result = cancel_overmerged([[a1, a2], g2, g3], W)
        assert [a1] in result and [a2] in result
        assert len(result) == 4

    def test_keeps_normal_column_groups(self):
        g1 = [_r(100, 100, 300, 100), _r(100, 220, 300, 100)]
        g2 = [_r(450, 100, 300, 100)]
        assert cancel_overmerged([g1, g2], W) == [g1, g2]


class TestFinalizeBlocks:
    def test_adds_padding_ratios(self):
        # pad_x = 1000*0.004 = 4px, pad_y = 1000*0.003 = 3px
        out = finalize_blocks([[_r(100, 100, 300, 200)]], W, H)
        assert out == [_r(96, 97, 308, 206)]

    def test_padding_stops_at_midpoint_between_neighbors(self):
        left = [_r(100, 100, 300, 200)]
        right = [_r(406, 100, 300, 200)]  # 空白 6px → 中点 x=403
        out = finalize_blocks([left, right], W, H)
        assert out[0] == _r(96, 97, 307, 206)
        assert out[1] == _r(403, 97, 307, 206)

    def test_clamps_to_image_bounds(self):
        out = finalize_blocks([[_r(2, 2, 100, 100)]], W, H)
        assert out == [_r(0, 0, 106, 105)]

    def test_preserves_group_order(self):
        g1 = [_r(500, 100, 100, 100)]
        g2 = [_r(100, 100, 100, 100)]
        out = finalize_blocks([g1, g2], W, H)
        assert out[0].x > out[1].x  # 並び替えは行わない（順序はパイプラインが決める）


class TestComputeVerticalBlocks:
    def test_empty_input_returns_empty(self):
        assert compute_vertical_blocks(W, H, []) == []

    def test_invalid_image_size_returns_empty(self):
        assert compute_vertical_blocks(0, H, [_r(10, 10, 20, 20)]) == []

    def test_perimeter_only_page_falls_back_to_normalized_paragraphs(self):
        # 有効な縦ブロックを生成できない場合は妥当な元段落を返す（スペック 8）
        rect = _r(100, 10, 200, 30)
        assert compute_vertical_blocks(W, H, [rect]) == [rect]

    def test_two_column_page_with_page_number(self):
        p1 = _r(100, 100, 380, 240)
        p2 = _r(100, 360, 380, 300)
        q1 = _r(520, 100, 380, 280)
        q2 = _r(520, 400, 380, 320)
        page_no = _r(480, 950, 40, 30)
        out = compute_vertical_blocks(W, H, [p1, p2, q1, q2, page_no])
        # 2 列がそれぞれ 1 ブロックへ統合され、ページ番号は出力に残らない
        assert out == [_r(96, 97, 388, 566), _r(516, 97, 388, 626)]

    def test_output_order_is_band_top_down_then_left_right(self):
        upper = [_r(100, 100, 400, 200), _r(520, 100, 400, 200)]
        lower = [_r(100, 340, 400, 200), _r(520, 340, 400, 200)]
        out = compute_vertical_blocks(W, H, [upper[1], lower[0], upper[0], lower[1]])
        assert [(b.y < 300, b.x < 300) for b in out] == [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]
