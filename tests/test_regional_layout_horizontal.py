"""layout_horizontal.py 純粋関数のユニットテスト。座標は 1000x1000 画像を前提とする。

閾値（W=H=1000 のとき）: 断片幅 80 / 吸収間隔 80 / 上端揃え 30 / プロファイル端 30 / 統合間隔 250
"""

from __future__ import annotations

from nova_parser.regional_ocr.layout_horizontal import absorb_narrow_fragments, merge_by_y_profile
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

    def test_empty_input_returns_empty(self):
        assert merge_by_y_profile([], W, H) == []
