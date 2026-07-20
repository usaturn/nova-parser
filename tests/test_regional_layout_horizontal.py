"""layout_horizontal.py 純粋関数のユニットテスト。座標は 1000x1000 画像を前提とする。

閾値（W=H=1000 のとき）: 断片幅 100 / 吸収間隔 80 / 上端揃え 30 / 断片高さ比 0.50
/ プロファイル端 30 / 統合間隔 250 / 高さ類似比 0.88 / 類似統合間隔 80
"""

from __future__ import annotations

from nova_parser.regional_ocr.layout_horizontal import (
    absorb_narrow_fragments,
    compute_horizontal_blocks,
    merge_by_y_profile,
)
from nova_parser.regional_ocr.models import BlockRect

W, H = 1000, 1000


def _r(x: int, y: int, w: int, h: int) -> BlockRect:
    return BlockRect(x=x, y=y, width=w, height=h)


def _boxes(clusters: list[list[BlockRect]]) -> set[tuple[int, int, int, int]]:
    """クラスタ集合を外接 (left, top, right, bottom) の set へ変換し順序非依存で比較する。"""
    return {
        (min(r.left for r in c), min(r.top for r in c), max(r.right for r in c), max(r.bottom for r in c))
        for c in clusters
    }


class TestAbsorbNarrowFragments:
    def test_absorbs_top_aligned_narrow_fragment(self):
        body = [_r(100, 100, 300, 600)]
        frag = [_r(420, 110, 50, 200)]
        assert _boxes(absorb_narrow_fragments([body, frag], W, H)) == {(100, 100, 470, 700)}

    def test_keeps_fragment_with_far_top(self):
        # 欄外注釈: 上端が本文より大きく低い断片は吸収しない
        body = [_r(100, 100, 300, 600)]
        note = [_r(420, 300, 50, 200)]
        assert _boxes(absorb_narrow_fragments([body, note], W, H)) == {(100, 100, 400, 700), (420, 300, 470, 500)}

    def test_keeps_wide_cluster(self):
        # 図版上の短列群: 幅が閾値超のクラスタは断片ではない
        body = [_r(100, 100, 300, 600)]
        wide = [_r(420, 110, 150, 300)]
        assert len(absorb_narrow_fragments([body, wide], W, H)) == 2

    def test_keeps_fragment_beyond_gap(self):
        body = [_r(100, 100, 300, 600)]
        frag = [_r(500, 110, 50, 200)]
        assert len(absorb_narrow_fragments([body, frag], W, H)) == 2

    def test_absorbs_into_nearest_neighbor(self):
        # 左右両方が吸収条件を満たす（間隔 30 と 70、共に上限 80 以内）とき、近い左を選ぶ
        left = [_r(100, 100, 200, 600)]
        right = [_r(440, 100, 200, 600)]
        frag = [_r(330, 105, 40, 200)]
        assert _boxes(absorb_narrow_fragments([left, right, frag], W, H)) == {
            (100, 100, 370, 700),
            (440, 100, 640, 700),
        }

    def test_lone_narrow_cluster_stays(self):
        assert _boxes(absorb_narrow_fragments([[_r(50, 300, 60, 400)]], W, H)) == {(50, 300, 110, 700)}

    def test_keeps_medium_height_fragment_from_full_height_host(self):
        # 図版上の中高列: 宿主の 50% を超える高さの断片は吸収しない（p035 型）
        full = [_r(300, 100, 80, 700)]
        mid = [_r(200, 105, 50, 400)]  # 400 > 700 * 0.50
        assert len(absorb_narrow_fragments([full, mid], W, H)) == 2

    def test_prefers_taller_host_on_equal_gap(self):
        # gap 同点ならより高い宿主へ吸収する
        left = [_r(100, 100, 150, 300)]  # right=250, h=300
        right = [_r(400, 100, 150, 700)]  # left=400, h=700
        frag = [_r(310, 105, 30, 120)]  # gap left=60, gap right=60
        out = _boxes(absorb_narrow_fragments([left, right, frag], W, H))
        assert (100, 100, 250, 400) in out  # 低い left は単独
        assert (310, 100, 550, 800) in out  # 高い right が frag を吸収

    def test_empty_input_returns_empty(self):
        assert absorb_narrow_fragments([], W, H) == []


class TestMergeByYProfile:
    def test_merges_adjacent_same_profile(self):
        a = [_r(100, 100, 200, 700)]
        b = [_r(350, 110, 200, 695)]
        assert _boxes(merge_by_y_profile([a, b], W, H)) == {(100, 100, 550, 805)}

    def test_keeps_shorter_neighbor(self):
        # 図版上の短列群: 下端が大きく異なる隣は統合しない
        a = [_r(100, 100, 200, 700)]
        b = [_r(350, 105, 200, 400)]
        assert len(merge_by_y_profile([a, b], W, H)) == 2

    def test_keeps_lower_top_neighbor(self):
        # 欄外注釈: 上端が大きく異なる隣は統合しない
        a = [_r(100, 100, 200, 700)]
        b = [_r(350, 300, 200, 500)]
        assert len(merge_by_y_profile([a, b], W, H)) == 2

    def test_chain_merges_across_middle_cluster(self):
        a = [_r(100, 100, 150, 700)]
        b = [_r(300, 100, 150, 700)]
        c = [_r(500, 100, 150, 700)]
        assert _boxes(merge_by_y_profile([a, b, c], W, H)) == {(100, 100, 650, 800)}

    def test_no_merge_beyond_max_gap(self):
        a = [_r(0, 100, 100, 700)]
        b = [_r(400, 100, 100, 700)]
        assert len(merge_by_y_profile([a, b], W, H)) == 2

    def test_merges_similar_height_top_aligned_within_sim_gap(self):
        # 下端はずれるが高さ比 ≥ 0.88 かつ近接 → 類似統合（p067 型）
        a = [_r(100, 100, 150, 700)]
        b = [_r(280, 105, 150, 650)]  # 高さ比 650/700≈0.93、gap=30 ≤ 80
        assert _boxes(merge_by_y_profile([a, b], W, H)) == {(100, 100, 430, 800)}

    def test_keeps_similar_height_beyond_sim_gap(self):
        # 高さは類似でも間隔が類似統合上限超かつ下端不一致 → 統合しない
        a = [_r(100, 100, 100, 700)]
        b = [_r(300, 105, 100, 650)]  # gap=100 > 80, bottom 差あり
        assert len(merge_by_y_profile([a, b], W, H)) == 2

    def test_empty_input_returns_empty(self):
        assert merge_by_y_profile([], W, H) == []


class TestComputeHorizontalBlocks:
    def test_empty_input_returns_empty(self):
        assert compute_horizontal_blocks(W, H, []) == []
        assert compute_horizontal_blocks(0, 0, [_r(10, 10, 100, 100)]) == []

    def test_splits_bands_at_common_horizontal_gap(self):
        # p006 型: 全列共通の縦空白で上下バンドへ分割し、バンド内は 1 ブロックへ統合
        top = [_r(100, 100, 300, 250), _r(450, 110, 300, 240)]
        bottom = [_r(100, 500, 300, 300), _r(450, 505, 300, 295)]
        blocks = compute_horizontal_blocks(W, H, top + bottom)
        assert len(blocks) == 2
        assert blocks[0].y < blocks[1].y

    def test_orders_blocks_right_to_left_within_band(self):
        # 縦書き読み順: 右領域 → 図版上の短列群 → 欄外注釈
        main = _r(600, 100, 300, 700)
        short = _r(300, 100, 250, 400)  # 下端が異なる → 別ブロック
        note = _r(50, 300, 100, 500)  # 上端が異なる → 別ブロック
        blocks = compute_horizontal_blocks(W, H, [note, short, main])
        assert len(blocks) == 3
        assert blocks[0].x > blocks[1].x > blocks[2].x

    def test_merges_same_profile_columns_into_one_block(self):
        a = _r(100, 100, 250, 700)
        b = _r(400, 105, 250, 700)
        c = _r(700, 100, 200, 705)
        blocks = compute_horizontal_blocks(W, H, [a, b, c])
        assert len(blocks) == 1
        blk = blocks[0]
        assert blk.left <= 100 and blk.right >= 900
        assert blk.top <= 100 and blk.bottom >= 805

    def test_returns_normalized_rects_when_body_empty(self):
        # 下端外周帯の孤立ノンブルのみ → 本文 0 件 → 正規化済み矩形を返す
        page_no = _r(480, 960, 40, 25)
        assert compute_horizontal_blocks(W, H, [page_no]) == [page_no]
