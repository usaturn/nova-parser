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

from nova_parser.regional_ocr.layout import (
    _bbox,
    _cluster_by_x,
    _segment_by_y_gaps,
    drop_noise_rects,
    drop_perimeter_rects,
    finalize_blocks,
    normalize_rects,
)
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


# --- 7.5 Y プロファイル統合 ---------------------------------------------------


def merge_by_y_profile(
    clusters: list[list[BlockRect]],
    image_width: int,
    image_height: int,
) -> list[list[BlockRect]]:
    """上端・下端が共に揃う X 隣接クラスタを横方向へ統合する（スペック 7.5）。

    統合は連鎖する（統合後の外接矩形で次の隣と比較する）。図版上の短列群・
    欄外注釈は端が揃わないため統合されない。X 間隔が H_MERGE_MAX_GAP_RATIO を
    超える統合は安全弁として行わない。
    """
    edge_tol = image_height * H_PROFILE_EDGE_TOL_RATIO
    gap_max = image_width * H_MERGE_MAX_GAP_RATIO
    result = [list(c) for c in clusters if c]
    changed = True
    while changed:
        changed = False
        boxes = [_bbox(c) for c in result]
        for i in range(len(result)):
            for j in range(i + 1, len(result)):
                bi, bj = boxes[i], boxes[j]
                if _x_gap(bi, bj) > gap_max:
                    continue
                if abs(bi.top - bj.top) > edge_tol or abs(bi.bottom - bj.bottom) > edge_tol:
                    continue
                result[i].extend(result[j])
                del result[j]
                changed = True
                break
            if changed:
                break
    return result


# --- 公開エントリポイント -----------------------------------------------------


def compute_horizontal_blocks(image_width: int, image_height: int, blocks: list[BlockRect]) -> list[BlockRect]:
    """段落矩形一覧から横ブロック矩形一覧をローカル生成する（スペック 6.1）。

    出力順は (バンド上→下, バンド内右→左) の縦書き読み順。判定が不確実な場合は
    誤結合より未結合を優先し、余剰候補として残す（スペック 8）。
    本文矩形が 0 件なら正規化済み矩形を返し、入力 0 件・画像サイズ不正は 0 件を返す。
    想定外の例外は握り潰さず呼び出し元へ伝播する。
    """
    if image_width <= 0 or image_height <= 0 or not blocks:
        return []
    rects = normalize_rects(blocks, image_width, image_height)
    if not rects:
        return []
    body = drop_perimeter_rects(rects, image_width, image_height)
    body = drop_noise_rects(body, image_width, image_height)
    if not body:
        return rects
    gap_min = image_height * H_BAND_GAP_MIN_RATIO
    ordered: list[list[BlockRect]] = []
    for band in _segment_by_y_gaps(body, gap_min):
        clusters = _cluster_by_x(band, image_width)
        clusters = absorb_narrow_fragments(clusters, image_width, image_height)
        clusters = merge_by_y_profile(clusters, image_width, image_height)
        # バンド内は右→左（縦書き読み順）
        clusters.sort(key=lambda c: -_bbox(c).right)
        ordered.extend(clusters)
    return finalize_blocks(ordered, image_width, image_height)
