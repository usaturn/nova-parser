"""段落矩形から縦ブロックを生成する純粋レイアウト処理モジュール。

Vision SDK・FastAPI・ファイル I/O へ依存しない（スペック 6.1）。
閾値はすべて本モジュール冒頭の名前付き定数へ集約する。定数の変更は
6 ページのゴールデンテスト（tests/test_regional_layout_golden.py）全通過を条件とする。

パイプライン（compute_vertical_blocks）:
normalize_rects → drop_perimeter_rects → drop_noise_rects
→ split_bands → split_columns → split_vertical → cancel_overmerged
→ merge_narrow_column_groups → merge_columns_across_spanning_headings
→ finalize_blocks
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

BAND_GAP_MIN_RATIO = 0.016
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

PAD_X_RATIO = 0.006
"""出力矩形の左右余白（画像幅比）。0.6%。

スペック 7.5 の初期値は 0.4% だったが、ゴールデンチューニング後に 0.006 へ更新。
"""

PAD_Y_RATIO = 0.006
"""出力矩形の上下余白（画像高さ比）。0.6%。

スペック 7.5 の初期値は 0.3% だったが、ゴールデンチューニング後に 0.006 へ更新。
"""

# --- Task 9 判定強化用の閾値 --------------------------------------------------

NOISE_MICRO_HEIGHT_FACTOR = 0.35
"""極小ノイズ高さ = PERIMETER_MAX_HEIGHT_RATIO * この係数（≈ 画像高さの 1.4%）。"""

NOISE_DECORATION_ASPECT_RATIO = 8.0
"""装飾候補とみなす最小アスペクト比（幅 / 高さ）。"""

SPANNING_HEADING_WIDTH_RATIO = 0.35
"""横断帯見出しとみなす最小幅（画像幅比）。drop_noise / 列再結合の双方で使用。"""

NOISE_CARD_HEADING_WIDTH_RATIO = 0.25
"""カード行見出しとして残す最小幅（画像幅比）。水平ピアがある場合のみ。"""

NOISE_PEER_MIN_WIDTH_RATIO = 0.12
"""カード見出し判定の水平ピアとみなす最小幅（画像幅比）。"""

NOISE_PEER_Y_TOLERANCE_RATIO = 0.03
"""カード見出しと同 Y 帯の水平ピアとみなす中心 Y 差（画像高さ比）。"""

NOISE_NEAR_COLUMN_V_GAP_RATIO = 0.08
"""装飾除外を抑止する「直下/直上の本文列」との最大縦間隔（画像高さ比）。"""

CLUSTER_CENTER_TOL_FACTOR = 3
"""列クラスタの中心近接許容 = COLUMN_EDGE_TOLERANCE * この係数。"""

CLUSTER_FULLY_INSIDE_WIDTH_FACTOR = 1.05
"""列コア幅に対し「完全に内側」とみなす最大幅倍率。"""

SHARED_ROW_GAP_FILL_RATIO = 0.25
"""隣接本文列がギャップ区間を埋めているとみなす最小縦重なり率（ギャップ高比）。"""

NARROW_MERGE_MAX_Y_OVERLAP_RATIO = 0.15
"""欄外注釈グループ統合を拒否する最小 Y 重なり率（狭い方の高さ比）。"""

SPAN_MERGE_EDGE_TOL_FACTOR = 2
"""横断見出し挟みの列再結合で許容する左端差 = COLUMN_EDGE_TOLERANCE * この係数。"""

SPAN_MERGE_MIN_COL_HEIGHT_RATIO = 0.08
"""列再結合の対象とする最小列高さ（画像高さ比）。"""

SPAN_MERGE_WIDTH_DIFF_RATIO = 0.25
"""列再結合で許す上下列の最大幅差率。"""

SPAN_MERGE_X_OVERLAP_RATIO = 0.6
"""列再結合に要する最小 X 重なり率（狭い方の幅比）。"""

SPAN_MERGE_HEADING_MAX_HEIGHT_RATIO = 0.05
"""横断見出しとみなす最大高さ（画像高さ比）。"""

SPAN_MERGE_BLOCK_X_OVERLAP_RATIO = 0.2
"""中間の非見出しブロックが列再結合を阻害する最小 X 重なり率（上列幅比）。"""

SPAN_MERGE_SOFT_EDGE_PX = 2
"""上列下端〜下列上端の間に入る中間矩形を拾うソフト端（ピクセル）。"""


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


def _covers_column_x(heading: _Box, col: _Box) -> bool:
    """heading が col の幅の SPAN_COVER_RATIO 以上を X 方向に覆うか。"""
    if col.width <= 0:
        return False
    return _x_overlap(heading, col) / col.width >= SPAN_COVER_RATIO


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


def drop_noise_rects(rects: list[BlockRect], image_width: int, image_height: int) -> list[BlockRect]:
    """OCR 誤検出の装飾・極小ラベルを除外する。

    - 画像高さの約 1.4% 未満の極小矩形（例: 独立したサブタイトル断片）
    - 本文列に属さない幅広薄型の装飾（例: 丸印グラフィックの誤認識）
    次は装飾扱いにしない:
    - ページ幅 35% 以上の横断帯見出し
    - 同 Y 帯に水平ピアがあるカード見出し行（幅 25% 以上）
    """
    kept: list[BlockRect] = []
    micro_h = image_height * PERIMETER_MAX_HEIGHT_RATIO * NOISE_MICRO_HEIGHT_FACTOR
    deco_h = image_height * PERIMETER_MAX_HEIGHT_RATIO
    edge_tol = image_width * COLUMN_EDGE_TOLERANCE_RATIO * CLUSTER_CENTER_TOL_FACTOR
    y_peer_tol = image_height * NOISE_PEER_Y_TOLERANCE_RATIO
    for r in rects:
        if r.height < micro_h:
            continue
        aspect = r.width / max(r.height, 1)
        if r.height < deco_h and aspect >= NOISE_DECORATION_ASPECT_RATIO:
            frac = r.width / image_width
            # 横断帯見出し
            if frac >= SPANNING_HEADING_WIDTH_RATIO:
                kept.append(r)
                continue
            # カード行の見出し: 同 Y に水平ピアがある
            peers = [
                o
                for o in rects
                if o is not r
                and abs((o.top + o.bottom) / 2 - (r.top + r.bottom) / 2) <= y_peer_tol
                and _x_overlap(r, o) <= 0
                and o.width >= image_width * NOISE_PEER_MIN_WIDTH_RATIO
            ]
            if peers and frac >= NOISE_CARD_HEADING_WIDTH_RATIO:
                kept.append(r)
                continue
            near_col = any(
                o.height >= deco_h
                and abs(o.left - r.left) <= edge_tol
                and _v_gap(r, o) < image_height * NOISE_NEAR_COLUMN_V_GAP_RATIO
                for o in rects
                if o is not r
            )
            if not near_col:
                continue
        kept.append(r)
    return kept


# --- 7.2 横方向レイアウト領域（バンド） ---------------------------------------


def _cluster_by_x(rects: list[BlockRect], image_width: int) -> list[list[BlockRect]]:
    """X 範囲の近さで矩形を列クラスタへまとめる（スペック 7.3 の同一列判定）。

    左端・右端が近い、または X 重なりが大きい矩形を同一クラスタとする。
    連鎖結合を抑えるため、クラスタ代表はメンバの左右端中央値とし、
    重なり率は max(幅) 基準、中心が離れた矩形は端が近くない限り結合しない。
    戻り値は左から右（同左端なら上から下）の順。
    """
    edge_tol = image_width * COLUMN_EDGE_TOLERANCE_RATIO
    center_tol = edge_tol * CLUSTER_CENTER_TOL_FACTOR
    clusters: list[list[BlockRect]] = []
    for r in sorted(rects, key=lambda r: (r.left, r.top)):
        target = None
        rc = (r.left + r.right) / 2
        for c in clusters:
            lefts = sorted(x.left for x in c)
            rights = sorted(x.right for x in c)
            ml = lefts[len(lefts) // 2]
            mr = rights[len(rights) // 2]
            core_w = mr - ml
            if core_w <= 0:
                continue
            ov = min(r.right, mr) - max(r.left, ml)
            max_w = max(r.width, core_w)
            left_close = abs(r.left - ml) <= edge_tol
            right_close = abs(r.right - mr) <= edge_tol
            center_close = abs(rc - (ml + mr) / 2) <= center_tol
            fully_inside = (
                r.left >= ml - edge_tol
                and r.right <= mr + edge_tol
                and r.width <= core_w * CLUSTER_FULLY_INSIDE_WIDTH_FACTOR
            )
            if left_close or right_close or fully_inside:
                if ov > 0 or left_close or right_close:
                    target = c
                    break
            elif ov > 0 and max_w > 0 and ov / max_w >= COLUMN_X_OVERLAP_RATIO and center_close:
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


# --- 7.4 縦方向統合 -----------------------------------------------------------


def _has_shared_row_boundary(
    gap_top: float,
    gap_bottom: float,
    neighbors: list[BlockRect],
    tol: float,
    image_width: int,
) -> bool:
    """隣接の本文列にも同じ行境界があるか（スペック 7.4: カード状の行）。

    欄外注釈など狭い列の段落境界は偶然揃いやすいため、本文幅を超える隣接クラスタだけを
    対象にする。隣接クラスタがギャップ区間を本文で埋めている場合も共有境界としない。
    """
    if not neighbors:
        return False
    clusters = _cluster_by_x(neighbors, image_width)
    min_body = image_width * NARROW_COLUMN_MAX_WIDTH_RATIO
    gap_h = max(gap_bottom - gap_top, 1.0)
    for cluster in clusters:
        cb = _bbox(cluster)
        if cb.width <= min_body:
            continue
        fills = any(
            (min(n.bottom, gap_bottom) - max(n.top, gap_top)) > gap_h * SHARED_ROW_GAP_FILL_RATIO for n in cluster
        )
        if fills:
            continue
        has_below = any(abs(n.top - gap_bottom) <= tol for n in cluster)
        has_above = any(abs(n.bottom - gap_top) <= tol for n in cluster)
        if has_below and has_above:
            return True
    return False


def _is_heading_break(group: list[BlockRect], cur: BlockRect) -> bool:
    """直前グループと次矩形の幅・中心位置が大きく異なるか（見出し境界、スペック 7.4）。

    直前が単一矩形（見出しそのもの）のときだけ適用する。複数段落を統合した本文中の
    短い行・部分幅行では分割しない。
    """
    if len(group) != 1:
        return False
    gb = _bbox(group)
    max_w = max(gb.width, cur.width)
    if max_w <= 0:
        return False
    width_diff = abs(gb.width - cur.width) / max_w
    center_diff = abs((gb.left + gb.right) / 2 - (cur.left + cur.right) / 2) / max_w
    return width_diff >= HEADING_WIDTH_DIFF_RATIO or center_diff >= HEADING_CENTER_DIFF_RATIO


def split_vertical(
    column: list[BlockRect],
    band: list[BlockRect],
    image_width: int,
    image_height: int,
) -> list[list[BlockRect]]:
    """同一列内の段落矩形を縦方向に統合し、根拠のある位置でのみ分割する（スペック 7.4）。

    band には同一バンドの全矩形（自列を含む）を渡す。隣接列の行境界判定に使う。
    欄外注釈候補（幅が画像幅の 25% 以下）は大きな縦空白を挟んでも統合する。
    """
    ordered = sorted(column, key=lambda r: (r.top, r.left))
    if len(ordered) <= 1:
        return [ordered] if ordered else []
    col_box = _bbox(ordered)
    is_narrow = col_box.width <= image_width * NARROW_COLUMN_MAX_WIDTH_RATIO
    gap_min = image_height * VERTICAL_SPLIT_GAP_RATIO
    align_tol = image_height * ROW_ALIGN_TOLERANCE_RATIO
    column_ids = {id(r) for r in column}
    neighbors = [r for r in band if id(r) not in column_ids]
    groups: list[list[BlockRect]] = [[ordered[0]]]
    for cur in ordered[1:]:
        group_bottom = max(r.bottom for r in groups[-1])
        gap = cur.top - group_bottom
        split = False
        if gap >= gap_min and not is_narrow:
            if _has_shared_row_boundary(group_bottom, cur.top, neighbors, align_tol, image_width):
                split = True
            elif _is_heading_break(groups[-1], cur):
                split = True
        if split:
            groups.append([cur])
        else:
            groups[-1].append(cur)
    return groups


# --- 8 過結合の取り消し -------------------------------------------------------


def _spans_boxes(box: _Box, others: list[_Box]) -> int:
    """box が横方向に覆っている他グループ数（Y 重なりがあるものだけ数える）。"""
    count = 0
    for o in others:
        if o.width > 0 and _y_overlap(box, o) > 0 and _x_overlap(box, o) / o.width >= SPAN_COVER_RATIO:
            count += 1
    return count


def cancel_overmerged(band_groups: list[list[BlockRect]], image_width: int) -> list[list[BlockRect]]:
    """統合の結果、複数の推定列をまたぐ巨大矩形になったグループを解体する（スペック 8）。

    解体したグループの元段落は単独ブロックとして残す（未結合を優先）。
    """
    boxes = [_bbox(g) for g in band_groups]
    result: list[list[BlockRect]] = []
    for i, group in enumerate(band_groups):
        others = [b for j, b in enumerate(boxes) if j != i]
        if len(group) >= 2 and _spans_boxes(boxes[i], others) >= 2:
            result.extend([r] for r in group)
        else:
            result.append(group)
    return result


def merge_narrow_column_groups(groups: list[list[BlockRect]], image_width: int) -> list[list[BlockRect]]:
    """欄外注釈候補（狭い列）の縦積みグループをバンド跨ぎで統合する（スペック 7.3）。

    左端または右端が近く、X 重なりが大きく、Y 方向に並んだ狭いグループを 1 つにまとめる。
    本文列（幅が NARROW 超）は対象外。
    """
    if len(groups) <= 1:
        return groups
    edge_tol = image_width * COLUMN_EDGE_TOLERANCE_RATIO
    boxes = [_bbox(g) for g in groups]
    used = [False] * len(groups)
    result: list[list[BlockRect]] = []
    order = sorted(range(len(groups)), key=lambda i: (boxes[i].left, boxes[i].top))
    for i in order:
        if used[i]:
            continue
        bi = boxes[i]
        if bi.width > image_width * NARROW_COLUMN_MAX_WIDTH_RATIO:
            result.append(groups[i])
            used[i] = True
            continue
        merged = list(groups[i])
        mb = bi
        used[i] = True
        changed = True
        while changed:
            changed = False
            for j in order:
                if used[j]:
                    continue
                bj = boxes[j]
                if bj.width > image_width * NARROW_COLUMN_MAX_WIDTH_RATIO:
                    continue
                if abs(mb.left - bj.left) > edge_tol and abs(mb.right - bj.right) > edge_tol:
                    continue
                ov = _x_overlap(mb, bj)
                min_w = min(mb.width, bj.width)
                if min_w <= 0 or ov / min_w < COLUMN_X_OVERLAP_RATIO:
                    continue
                if _y_overlap(mb, bj) > min(mb.height, bj.height) * NARROW_MERGE_MAX_Y_OVERLAP_RATIO:
                    continue
                merged.extend(groups[j])
                mb = _bbox(merged)
                used[j] = True
                changed = True
        result.append(merged)
    result.sort(key=lambda g: (_bbox(g).top, _bbox(g).left))
    return result


def merge_columns_across_spanning_headings(
    groups: list[list[BlockRect]],
    image_width: int,
    image_height: int,
) -> list[list[BlockRect]]:
    """帯見出しだけを挟んで上下に分断された同一本文列を再結合する。

    中間にページ幅 35% 以上・高さ 5% 以下の横断見出しがある場合のみ結合する。
    カード行のように空ギャップだけで並ぶ本文列は結合しない（未結合優先）。
    """
    if len(groups) <= 1:
        return groups
    boxes = [_bbox(g) for g in groups]
    body_min = image_width * NARROW_COLUMN_MAX_WIDTH_RATIO
    edge_tol = image_width * COLUMN_EDGE_TOLERANCE_RATIO * SPAN_MERGE_EDGE_TOL_FACTOR
    min_col_h = image_height * SPAN_MERGE_MIN_COL_HEIGHT_RATIO
    span_w = image_width * SPANNING_HEADING_WIDTH_RATIO
    span_h = image_height * SPAN_MERGE_HEADING_MAX_HEIGHT_RATIO
    soft = SPAN_MERGE_SOFT_EDGE_PX
    parent = list(range(len(groups)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, bi in enumerate(boxes):
        if bi.width < body_min or bi.height < min_col_h:
            continue
        for j in range(i + 1, len(groups)):
            bj = boxes[j]
            if bj.width < body_min or bj.height < min_col_h:
                continue
            if abs(bi.width - bj.width) / max(bi.width, bj.width) > SPAN_MERGE_WIDTH_DIFF_RATIO:
                continue
            if abs(bi.left - bj.left) > edge_tol:
                continue
            ov = min(bi.right, bj.right) - max(bi.left, bj.left)
            if ov < min(bi.width, bj.width) * SPAN_MERGE_X_OVERLAP_RATIO:
                continue
            if bi.bottom <= bj.top:
                upper, lower = bi, bj
            elif bj.bottom <= bi.top:
                upper, lower = bj, bi
            else:
                continue
            interveners = [
                bk
                for k, bk in enumerate(boxes)
                if k not in (i, j)
                and (
                    (bk.top < lower.top and bk.bottom > upper.bottom)
                    or (bk.top >= upper.bottom - soft and bk.bottom <= lower.top + soft)
                )
            ]
            spans = [
                bk
                for bk in interveners
                if bk.width >= span_w
                and bk.height <= span_h
                and _covers_column_x(bk, upper)
                and _covers_column_x(bk, lower)
            ]
            if not spans:
                continue
            blocked = False
            for bk in interveners:
                is_span = (
                    bk.width >= span_w
                    and bk.height <= span_h
                    and _covers_column_x(bk, upper)
                    and _covers_column_x(bk, lower)
                )
                if is_span:
                    continue
                xov = min(upper.right, bk.right) - max(upper.left, bk.left)
                if xov > upper.width * SPAN_MERGE_BLOCK_X_OVERLAP_RATIO:
                    blocked = True
                    break
            if not blocked:
                union(i, j)

    buckets: dict[int, list[int]] = {}
    for i in range(len(groups)):
        buckets.setdefault(find(i), []).append(i)
    result: list[list[BlockRect]] = []
    for ids in buckets.values():
        merged: list[BlockRect] = []
        for i in ids:
            merged.extend(groups[i])
        result.append(merged)
    result.sort(key=lambda g: (_bbox(g).top, _bbox(g).left))
    return result


# --- 7.5 出力整形 -------------------------------------------------------------


def finalize_blocks(groups: list[list[BlockRect]], image_width: int, image_height: int) -> list[BlockRect]:
    """各グループの外接矩形へ余白を付け、隣接との空白中点・画像境界でクランプする（スペック 7.5）。

    出力順は入力グループ順のまま（並び順はパイプライン側で決定済み）。
    """
    boxes = [_bbox(g) for g in groups]
    pad_x = image_width * PAD_X_RATIO
    pad_y = image_height * PAD_Y_RATIO
    blocks: list[BlockRect] = []
    for i, b in enumerate(boxes):
        left = b.left - pad_x
        top = b.top - pad_y
        right = b.right + pad_x
        bottom = b.bottom + pad_y
        for j, o in enumerate(boxes):
            if i == j:
                continue
            if _y_overlap(b, o) > 0:
                if o.right <= b.left:
                    left = max(left, (o.right + b.left) / 2)
                if o.left >= b.right:
                    right = min(right, (b.right + o.left) / 2)
            if _x_overlap(b, o) > 0:
                if o.bottom <= b.top:
                    top = max(top, (o.bottom + b.top) / 2)
                if o.top >= b.bottom:
                    bottom = min(bottom, (b.bottom + o.top) / 2)
        x = max(0, round(left))
        y = max(0, round(top))
        x2 = min(image_width, round(right))
        y2 = min(image_height, round(bottom))
        blocks.append(BlockRect(x=x, y=y, width=max(1, x2 - x), height=max(1, y2 - y)))
    return blocks


# --- 公開エントリポイント -----------------------------------------------------


def compute_vertical_blocks(image_width: int, image_height: int, blocks: list[BlockRect]) -> list[BlockRect]:
    """段落矩形一覧から縦ブロック矩形一覧をローカル生成する（スペック 6.1）。

    判定が不確実な場合は誤った巨大矩形へ結合せず、妥当な元段落を返す（スペック 8）。
    元段落が 0 件なら 0 件を返す。想定外の例外は握り潰さず呼び出し元へ伝播する。
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
    groups: list[list[BlockRect]] = []
    for band in split_bands(body, image_width, image_height):
        band_groups: list[list[BlockRect]] = []
        for column in split_columns(band, image_width):
            band_groups.extend(split_vertical(column, band, image_width, image_height))
        groups.extend(cancel_overmerged(band_groups, image_width))
    groups = merge_narrow_column_groups(groups, image_width)
    groups = merge_columns_across_spanning_headings(groups, image_width, image_height)
    if not groups:
        return body
    return finalize_blocks(groups, image_width, image_height)
