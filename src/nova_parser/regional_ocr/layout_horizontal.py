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

H_FRAG_MAX_WIDTH_RATIO = 0.10
"""見出し断片とみなす最大クラスタ幅（画像幅比 ≈ 本文 1〜2 列分）。スペック 7.4。"""

H_FRAG_GAP_RATIO = 0.08
"""断片を吸収できる X 隣接間隔の上限（画像幅比）。スペック 7.4。"""

H_TOP_ALIGN_TOL_RATIO = 0.03
"""断片吸収で「上端が揃う」とみなす Y 差の許容（画像高さ比）。欄外注釈の誤吸収を防ぐ。"""

H_FRAG_HOST_HEIGHT_RATIO = 0.50
"""断片の高さが宿主のこの比率以下のときのみ吸収する。図版上の中高列が全高列へ
誤吸収されるのを防ぎつつ、見出し級の短列は取り込む。"""

H_PROFILE_EDGE_TOL_RATIO = 0.03
"""Y プロファイル統合で上端・下端が「揃う」とみなす Y 差の許容（画像高さ比）。スペック 7.5。"""

H_MERGE_MAX_GAP_RATIO = 0.25
"""Y プロファイル統合（上下端一致）を許す X 間隔の上限（画像幅比）。安全弁。"""

H_PROFILE_HEIGHT_SIM_RATIO = 0.88
"""上端が揃い、高さ比がこの値以上の隣接クラスタを統合する（下端不一致でも可）。
Vision が列ごとに下端をわずかにずらすケース向け。誤結合を避けるため間隔は
H_PROFILE_SIM_MAX_GAP_RATIO で厳しく制限する。"""

H_PROFILE_SIM_MAX_GAP_RATIO = 0.08
"""高さ類似統合を許す X 間隔の上限（画像幅比）。広めの間隔での横断結合を防ぐ。"""


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

    吸収条件:
    - 断片幅 ≤ H_FRAG_MAX_WIDTH_RATIO
    - X 間隔 ≤ H_FRAG_GAP_RATIO
    - 上端差 ≤ H_TOP_ALIGN_TOL_RATIO
    - 断片高さ ≤ 宿主高さ × H_FRAG_HOST_HEIGHT_RATIO（真の見出し断片のみ）

    候補が複数ある場合は X 間隔が最小の隣を選び、同間隔ならより高い宿主を優先する。
    欄外注釈は上端が本文より大きく低いため吸収されない。
    """
    max_w = image_width * H_FRAG_MAX_WIDTH_RATIO
    gap_max = image_width * H_FRAG_GAP_RATIO
    top_tol = image_height * H_TOP_ALIGN_TOL_RATIO
    edge_tol = image_height * H_PROFILE_EDGE_TOL_RATIO
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
            best_host_h = -1.0
            for j, bj in enumerate(boxes):
                if i == j:
                    continue
                gap = _x_gap(bi, bj)
                if gap > gap_max:
                    continue
                if abs(bi.top - bj.top) > top_tol:
                    continue
                # 宿主より実質的に高い断片は吸収しない
                if bi.height > bj.height + edge_tol:
                    continue
                # 見出し級の短列のみ（中高の図版列が全高列へ混ざるのを防ぐ）
                if bi.height > bj.height * H_FRAG_HOST_HEIGHT_RATIO:
                    continue
                if best is None or gap < best_gap - 1e-6 or (abs(gap - best_gap) <= 1e-6 and bj.height > best_host_h):
                    best, best_gap, best_host_h = j, gap, bj.height
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

    加えて、上端が揃い高さが十分類似（H_PROFILE_HEIGHT_SIM_RATIO 以上）で
    X 間隔が H_PROFILE_SIM_MAX_GAP_RATIO 以下の隣接クラスタも統合する。
    これは Vision が列下端をわずかにずらすケース向けの緩和であり、
    広い間隔での横断結合は行わない（未結合優先、スペック 8）。

    統合は連鎖する。図版上の短列群・欄外注釈は端も高さも揃わないため統合されない。
    """
    edge_tol = image_height * H_PROFILE_EDGE_TOL_RATIO
    gap_max = image_width * H_MERGE_MAX_GAP_RATIO
    sim_gap_max = image_width * H_PROFILE_SIM_MAX_GAP_RATIO
    result = [list(c) for c in clusters if c]
    changed = True
    while changed:
        changed = False
        boxes = [_bbox(c) for c in result]
        for i in range(len(result)):
            for j in range(i + 1, len(result)):
                bi, bj = boxes[i], boxes[j]
                gap = _x_gap(bi, bj)
                if abs(bi.top - bj.top) > edge_tol:
                    continue
                bot_ok = abs(bi.bottom - bj.bottom) <= edge_tol
                if bot_ok and gap <= gap_max:
                    ok = True
                elif gap <= sim_gap_max:
                    shorter = min(bi.height, bj.height)
                    taller = max(bi.height, bj.height)
                    ok = taller > 0 and shorter / taller >= H_PROFILE_HEIGHT_SIM_RATIO
                else:
                    ok = False
                if not ok:
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
