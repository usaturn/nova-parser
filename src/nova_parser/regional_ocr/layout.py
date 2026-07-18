"""段落矩形から縦ブロックを生成する純粋レイアウト処理モジュール。

Vision SDK・FastAPI・ファイル I/O へ依存しない（スペック 6.1）。
閾値はすべて本モジュール冒頭の名前付き定数へ集約する。定数の変更は
6 ページのゴールデンテスト（tests/test_regional_layout_golden.py）全通過を条件とする。
"""

from __future__ import annotations

from dataclasses import dataclass

from nova_parser.regional_ocr.models import BlockRect

# --- 名前付き閾値定数 ---------------------------------------------------------

PERIMETER_BAND_RATIO = 0.07
"""上端・下端の外周帯の高さ（画像高さ比）。スペック 7.1。"""

PERIMETER_MAX_HEIGHT_RATIO = 0.04
"""外周帯の「小矩形」とみなす最大高さ（画像高さ比）。"""

PERIMETER_ISOLATION_GAP_RATIO = 0.02
"""外周矩形が本文と連続しているとみなす最大縦間隔（画像高さ比）。"""

DUPLICATE_CONTAINMENT_RATIO = 0.90
"""重複整理: 交差面積 / 小さい方の面積 がこの値以上なら同一内容とみなす。"""

BAND_GAP_MIN_RATIO = 0.012
"""横方向レイアウト領域の境界とみなす、全列共通の縦空白の最小高さ（画像高さ比）。"""

BAND_HEADING_SPAN_COLUMNS = 2
"""帯見出しとみなすために横断すべき暫定列数。スペック 7.2。"""

WIDE_RECT_BAND_WIDTH_RATIO = 0.6
"""バンド内で「幅広矩形」（横断候補）とみなす最小幅（バンド本文幅比）。"""

SPAN_COVER_RATIO = 0.5
"""列を「横断している」とみなすための、列幅に対する X 重なり率。"""

COLUMN_X_OVERLAP_RATIO = 0.35
"""同一列とみなす X 方向の重なり率（狭い方の幅に対する比）。スペック 7.3。"""

COLUMN_EDGE_TOLERANCE_RATIO = 0.015
"""左端または右端が「近い」とみなす許容差（画像幅比）。スペック 7.3。"""

NARROW_COLUMN_MAX_WIDTH_RATIO = 0.25
"""欄外注釈候補とみなす最大列幅（画像幅比）。スペック 7.3。"""

VERTICAL_SPLIT_GAP_RATIO = 0.02
"""列内の縦分割を検討する最小空白高さ（画像高さ比）。スペック 7.4。"""

ROW_ALIGN_TOLERANCE_RATIO = 0.012
"""隣接列と「同じ行境界」とみなす Y 位置の許容差（画像高さ比）。スペック 7.4。"""

HEADING_WIDTH_DIFF_RATIO = 0.45
"""見出しと後続内容の幅が「大きく異なる」とみなす幅差率。スペック 7.4。"""

HEADING_CENTER_DIFF_RATIO = 0.25
"""見出しと後続内容の中心位置が「大きく異なる」とみなす中心差率（最大幅比）。"""

PAD_X_RATIO = 0.004
"""出力矩形の左右余白（画像幅比）。スペック 7.5。"""

PAD_Y_RATIO = 0.003
"""出力矩形の上下余白（画像高さ比）。スペック 7.5。"""


# --- 内部ヘルパー -------------------------------------------------------------


@dataclass(frozen=True)
class _Box:
    """浮動小数の外接矩形。BlockRect と同じ left/top/right/bottom を持つ。"""

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


def _bbox(rects) -> _Box:
    """矩形群の外接矩形。rects は BlockRect / _Box の混在を許す。"""
    return _Box(
        left=min(r.left for r in rects),
        top=min(r.top for r in rects),
        right=max(r.right for r in rects),
        bottom=max(r.bottom for r in rects),
    )


def _x_overlap(a, b) -> float:
    """X 方向の重なり幅。重ならない場合は負値。"""
    return min(a.right, b.right) - max(a.left, b.left)


def _y_overlap(a, b) -> float:
    """Y 方向の重なり幅。重ならない場合は負値。"""
    return min(a.bottom, b.bottom) - max(a.top, b.top)


def _v_gap(a, b) -> float:
    """縦方向の間隔。Y が重なる場合は 0。"""
    return max(a.top - b.bottom, b.top - a.bottom, 0)


# --- 7.1 正規化 ---------------------------------------------------------------


def normalize_rects(rects: list[BlockRect], image_width: int, image_height: int) -> list[BlockRect]:
    """画像境界へクランプし、退化矩形と重複・包含矩形を除去する（スペック 7.1）。

    重複整理では本文範囲を最も包含する（面積最大の）矩形を残す。
    単に一部が交差するだけの矩形は削除しない。出力は (y, x) 昇順。
    """
    clamped: list[BlockRect] = []
    for r in rects:
        left = max(0, min(r.x, image_width))
        top = max(0, min(r.y, image_height))
        right = max(0, min(r.x + r.width, image_width))
        bottom = max(0, min(r.y + r.height, image_height))
        if right - left < 1 or bottom - top < 1:
            continue
        clamped.append(BlockRect(x=left, y=top, width=right - left, height=bottom - top))

    kept: list[BlockRect] = []
    for r in sorted(clamped, key=lambda r: r.width * r.height, reverse=True):
        area = r.width * r.height
        covered = False
        for k in kept:
            ix = _x_overlap(r, k)
            iy = _y_overlap(r, k)
            if ix > 0 and iy > 0 and (ix * iy) / area >= DUPLICATE_CONTAINMENT_RATIO:
                covered = True
                break
        if not covered:
            kept.append(r)
    kept.sort(key=lambda r: (r.y, r.x))
    return kept


# --- 7.1 ページ外周要素の除外 -------------------------------------------------


def drop_perimeter_rects(rects: list[BlockRect], image_width: int, image_height: int) -> list[BlockRect]:
    """上下の外周帯に完全に収まり、本文から孤立した小矩形を除外する（スペック 7.1）。

    ヘッダー・フッター・ページ番号候補が対象。外周帯をまたいで本文側へ
    伸びる矩形、および本文と縦に連続する矩形は除外しない。
    """
    band = image_height * PERIMETER_BAND_RATIO
    max_height = image_height * PERIMETER_MAX_HEIGHT_RATIO
    gap_max = image_height * PERIMETER_ISOLATION_GAP_RATIO
    body = [r for r in rects if not (r.bottom <= band or r.top >= image_height - band)]
    kept: list[BlockRect] = []
    for r in rects:
        inside_band = r.bottom <= band or r.top >= image_height - band
        if not inside_band or r.height > max_height:
            kept.append(r)
            continue
        connected = any(_x_overlap(r, b) > 0 and _v_gap(r, b) <= gap_max for b in body)
        if connected:
            kept.append(r)
    return kept


# --- 7.2 横方向レイアウト領域（バンド） ---------------------------------------


def _cluster_by_x(rects: list[BlockRect], image_width: int) -> list[list[BlockRect]]:
    """X 範囲の近さで矩形を列クラスタへまとめる（スペック 7.3 の同一列判定）。

    左端・右端が近い、または X 重なりが大きい矩形を同一クラスタとする。
    戻り値は左から右（同左端なら上から下）の順。
    """
    edge_tol = image_width * COLUMN_EDGE_TOLERANCE_RATIO
    clusters: list[list[BlockRect]] = []
    for r in sorted(rects, key=lambda r: (r.left, r.top)):
        target = None
        for c in clusters:
            cb = _bbox(c)
            min_w = min(r.width, cb.width)
            if min_w <= 0:
                continue
            if (
                _x_overlap(r, cb) / min_w >= COLUMN_X_OVERLAP_RATIO
                or abs(r.left - cb.left) <= edge_tol
                or abs(r.right - cb.right) <= edge_tol
            ):
                target = c
                break
        if target is None:
            clusters.append([r])
        else:
            target.append(r)
    clusters.sort(key=lambda c: (_bbox(c).left, _bbox(c).top))
    return clusters


def _spanned_count(rect, columns: list[list[BlockRect]]) -> int:
    """rect が横断している列数。列幅の SPAN_COVER_RATIO 以上を覆う列を数える。"""
    count = 0
    for c in columns:
        cb = _bbox(c)
        if cb.width > 0 and _x_overlap(rect, cb) / cb.width >= SPAN_COVER_RATIO:
            count += 1
    return count


def _segment_by_y_gaps(rects: list[BlockRect], gap_min: float) -> list[list[BlockRect]]:
    """全矩形の Y 射影が gap_min 以上途切れる位置でセグメントへ分割する。"""
    ordered = sorted(rects, key=lambda r: (r.top, r.left))
    segments: list[list[BlockRect]] = [[ordered[0]]]
    covered_bottom = ordered[0].bottom
    for r in ordered[1:]:
        if r.top - covered_bottom >= gap_min:
            segments.append([r])
        else:
            segments[-1].append(r)
        covered_bottom = max(covered_bottom, r.bottom)
    return segments


def _split_by_spanning_rects(seg: list[BlockRect], image_width: int) -> list[list[BlockRect]]:
    """複数の暫定列を横断する帯見出しを単独バンドへ切り出し、上下を別バンドにする。"""
    ordered = sorted(seg, key=lambda r: (r.top, r.left))
    if len(ordered) <= 1:
        return [ordered]
    content = _bbox(ordered)
    wide_min = content.width * WIDE_RECT_BAND_WIDTH_RATIO
    narrow = [r for r in ordered if r.width < wide_min]
    columns = _cluster_by_x(narrow, image_width)
    spanning = [r for r in ordered if r.width >= wide_min and _spanned_count(r, columns) >= BAND_HEADING_SPAN_COLUMNS]
    if not spanning:
        return [ordered]
    spanning.sort(key=lambda r: r.top)
    span_ids = {id(r) for r in spanning}
    buckets: list[list[BlockRect]] = [[] for _ in range(len(spanning) + 1)]
    for r in ordered:
        if id(r) in span_ids:
            continue
        center = r.top + r.height / 2
        idx = sum(1 for s in spanning if (s.top + s.height / 2) <= center)
        buckets[idx].append(r)
    bands: list[list[BlockRect]] = []
    for i, s in enumerate(spanning):
        if buckets[i]:
            bands.append(buckets[i])
        bands.append([s])
    if buckets[-1]:
        bands.append(buckets[-1])
    return bands


def split_bands(rects: list[BlockRect], image_width: int, image_height: int) -> list[list[BlockRect]]:
    """本文矩形を横方向レイアウト領域（バンド）へ上から順に分割する（スペック 7.2）。

    複数の暫定列があるページでのみ、全列に共通する縦空白で一次分割する
    （単一の狭い列内の空白だけでは分割しない）。その後、各セグメント内の
    帯見出し（複数列を横断する幅広矩形）を単独バンドへ切り出す。
    """
    if not rects:
        return []
    content = _bbox(rects)
    wide_min = content.width * WIDE_RECT_BAND_WIDTH_RATIO
    provisional = _cluster_by_x([r for r in rects if r.width < wide_min], image_width)
    gap_min = image_height * BAND_GAP_MIN_RATIO
    if len(provisional) >= 2:
        segments = _segment_by_y_gaps(rects, gap_min)
    else:
        segments = [sorted(rects, key=lambda r: (r.top, r.left))]
    bands: list[list[BlockRect]] = []
    for seg in segments:
        bands.extend(_split_by_spanning_rects(seg, image_width))
    return bands


# --- 7.3 領域内の列推定 -------------------------------------------------------


def split_columns(band: list[BlockRect], image_width: int) -> list[list[BlockRect]]:
    """バンド内の矩形を列（または独立ブロック）へ左から順に分割する（スペック 7.3）。

    複数列を横断する幅広矩形は、いずれか 1 列へ吸収せず独立ブロックとして返す。
    暫定列が 2 未満のバンドでは横断判定が成立しないため、全体を通常クラスタリングする。
    """
    if len(band) <= 1:
        return [list(band)] if band else []
    content = _bbox(band)
    wide_min = content.width * WIDE_RECT_BAND_WIDTH_RATIO
    narrow = [r for r in band if r.width < wide_min]
    wide = [r for r in band if r.width >= wide_min]
    clusters = _cluster_by_x(narrow, image_width)
    if len(clusters) < 2:
        return _cluster_by_x(band, image_width)
    groups: list[list[BlockRect]] = list(clusters)
    for r in wide:
        if _spanned_count(r, clusters) >= 2:
            groups.append([r])
            continue
        best: list[BlockRect] | None = None
        best_overlap = 0.0
        for c in clusters:
            overlap = _x_overlap(r, _bbox(c))
            if overlap > best_overlap:
                best, best_overlap = c, overlap
        if best is None:
            groups.append([r])
        else:
            best.append(r)
    groups.sort(key=lambda c: (_bbox(c).left, _bbox(c).top))
    return groups
