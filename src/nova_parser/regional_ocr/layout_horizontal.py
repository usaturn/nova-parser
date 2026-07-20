"""段落矩形から横ブロック（縦書きページ向け）を生成する純粋レイアウト処理モジュール。

Vision SDK・FastAPI・ファイル I/O へ依存しない（スペック 6.1）。
閾値はすべて本モジュール冒頭の名前付き定数へ集約する。定数の変更は
10 ページのゴールデンテスト（tests/test_regional_layout_horizontal_golden.py）
全通過を条件とする。layout.py の定数・規則は変更しない。

パイプライン（compute_horizontal_blocks）:
normalize_rects → drop_perimeter_rects → drop_noise_rects
→ Y バンド分割 → X 区間クラスタリング → 見出し断片の吸収
→ Y プロファイル統合 → (バンド上→下, バンド内右→左) 整列 → finalize_blocks
"""

from __future__ import annotations

from nova_parser.regional_ocr.layout import _bbox
from nova_parser.regional_ocr.models import BlockRect

# --- 名前付き閾値定数 ---------------------------------------------------------

H_BAND_GAP_MIN_RATIO = 0.02
"""上下バンドの境界とみなす、全矩形共通の縦空白の最小高さ（画像高さ比）。スペック 7.2。"""

H_FRAG_MAX_WIDTH_RATIO = 0.08
"""見出し断片とみなす最大クラスタ幅（画像幅比 ≈ 本文 1〜2 列分）。スペック 7.4。"""

H_FRAG_GAP_RATIO = 0.08
"""断片を吸収できる X 隣接間隔の上限（画像幅比）。スペック 7.4。"""

H_TOP_ALIGN_TOL_RATIO = 0.03
"""断片吸収で「上端が揃う」とみなす Y 差の許容（画像高さ比）。欄外注釈の誤吸収を防ぐ。"""

H_PROFILE_EDGE_TOL_RATIO = 0.03
"""Y プロファイル統合で上端・下端が「揃う」とみなす Y 差の許容（画像高さ比）。スペック 7.5。"""

H_MERGE_MAX_GAP_RATIO = 0.25
"""Y プロファイル統合を許す X 間隔の上限（画像幅比）。安全弁。"""


# --- 内部ヘルパー -------------------------------------------------------------


def _x_gap(a, b) -> float:
    """X 方向の間隔。X が重なる場合は 0。"""
    return max(a.left - b.right, b.left - a.right, 0)


# --- 7.4 見出し断片の吸収 -----------------------------------------------------


def absorb_narrow_fragments(
    clusters: list[list[BlockRect]],
    image_width: int,
    image_height: int,
) -> list[list[BlockRect]]:
    """狭い見出し断片クラスタを、上端が揃う X 隣接クラスタへ吸収する（スペック 7.4）。

    吸収候補が複数ある場合は X 間隔が最小の隣を選ぶ。欄外注釈は上端が本文より
    大きく低いため吸収されない。吸収で幅が閾値を超えたクラスタは断片扱いを外れる。
    """
    max_w = image_width * H_FRAG_MAX_WIDTH_RATIO
    gap_max = image_width * H_FRAG_GAP_RATIO
    top_tol = image_height * H_TOP_ALIGN_TOL_RATIO
    result = [list(c) for c in clusters if c]
    changed = True
    while changed:
        changed = False
        boxes = [_bbox(c) for c in result]
        for i, bi in enumerate(boxes):
            if bi.width > max_w:
                continue
            best: int | None = None
            best_gap = 0.0
            for j, bj in enumerate(boxes):
                if i == j:
                    continue
                gap = _x_gap(bi, bj)
                if gap > gap_max:
                    continue
                if abs(bi.top - bj.top) > top_tol:
                    continue
                if best is None or gap < best_gap:
                    best, best_gap = j, gap
            if best is not None:
                result[best].extend(result[i])
                del result[i]
                changed = True
                break
    return result
