"""横ブロック生成のゴールデンテスト（スペック 11.3）。実 Vision API は呼ばない。

余剰許容方式: 期待ブロックが全て IoU 閾値以上で 1 対 1 検出されることのみ要求し、
図版内テキスト等に由来する余剰候補ブロックは許容する（検出件数の厳密一致は要求しない）。

## IoU 閾値の緩和（ユーザ option 1）

縦ブロックの `_iou_threshold`（面積ベース IOU_MIN=0.80 / IOU_MIN_SMALL=0.60）は使わず、
横ブロック専用の閾値を用いる。

背景:
- 欄外注釈の sample crop は Vision 段落より明らかに広い（pad 後でも max IoU ≈ 0.55〜0.75）
- p014 / p067 は Vision 段落矩形が期待領域境界を貫通し、結合のみでは max IoU ≈ 0.53
- 段落分割なし・layout.py 非改変の制約下では 0.80 全ページ通過は構造的に不可能

閾値:
- 細幅ブロック（width / image_width ≤ 0.12）: **0.50**（欄外注釈クラス）
- その他の横ブロック: **0.50**（Vision 幾何と sample crop の系統的ずれを吸収する横専用フロア）

0.70 を横デフォルトとする案も検討したが、構造的天井（p014 e1≈0.53 / p067 e0≈0.53）が
それを下回るため、option 1 では 0.50 を横ブロック共通の成功基準とする。
到達可能なページはアルゴリズム側で 0.70〜0.95 を目指す。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nova_parser.regional_ocr.layout_horizontal import compute_horizontal_blocks
from nova_parser.regional_ocr.models import BlockRect
from tests.test_regional_layout_golden import COVER_RATIO, _cover, _greedy_match

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "regional_layout"

# 横ブロック専用 IoU 閾値（ユーザ option 1: 成功基準の緩和）
H_IOU_MIN = 0.50
"""横ブロック共通の IoU 下限。Vision 幾何と sample crop のずれ・貫通矩形を吸収する。"""

H_IOU_NARROW = 0.50
"""細幅（欄外注釈など）の IoU 下限。縦の IOU_MIN_SMALL=0.60 より緩和。"""

H_NARROW_WIDTH_RATIO = 0.12
"""細幅とみなす期待ブロック幅の画像幅比。"""

# スペック 5 の正解データ表
PAGES = {
    "AG2_SILVER_WINGED_SAVIOR_p006": 2,
    "AG2_SILVER_WINGED_SAVIOR_p012": 1,
    "AG2_SILVER_WINGED_SAVIOR_p014": 2,
    "AG2_SILVER_WINGED_SAVIOR_p015": 2,
    "AG2_SILVER_WINGED_SAVIOR_p019": 2,
    "AG2_SILVER_WINGED_SAVIOR_p021": 2,
    "AG2_SILVER_WINGED_SAVIOR_p029": 3,
    "AG2_SILVER_WINGED_SAVIOR_p035": 3,
    "AG2_SILVER_WINGED_SAVIOR_p067": 3,
    "AG2_SILVER_WINGED_SAVIOR_p123": 3,
}


def _horizontal_iou_threshold(expected: dict, image_width: int) -> float:
    """横ブロック用 IoU 閾値。細幅は H_IOU_NARROW、それ以外は H_IOU_MIN。"""
    if image_width > 0 and expected["width"] / image_width <= H_NARROW_WIDTH_RATIO:
        return H_IOU_NARROW
    return H_IOU_MIN


@pytest.mark.parametrize(("page", "expected_count"), sorted(PAGES.items()))
def test_golden_horizontal_blocks(page: str, expected_count: int) -> None:
    data = json.loads((FIXTURE_DIR / f"{page}.json").read_text(encoding="utf-8"))
    detected = [
        b.model_dump()
        for b in compute_horizontal_blocks(
            data["image_width"],
            data["image_height"],
            [BlockRect(**p) for p in data["paragraph_blocks"]],
        )
    ]
    expected = data["expected_horizontal_blocks"]
    image_width = data["image_width"]
    assert len(expected) == expected_count
    matches = _greedy_match(detected, expected)
    by_expected = {j: (iou, i) for iou, i, j in matches}
    for j, exp in enumerate(expected):
        assert j in by_expected, f"{page}: expected[{j}] に対応する検出がない"
        iou, i = by_expected[j]
        thr = _horizontal_iou_threshold(exp, image_width)
        assert iou >= thr, (
            f"{page}: IoU {iou:.3f} < {thr} (detected[{i}] vs expected[{j}], "
            f"area={exp['width'] * exp['height']}, w/W={exp['width'] / image_width:.3f})"
        )
    # 読み順: 期待ブロックへ対応する検出が、検出列内でも同じ順に並ぶ（余剰の混在は許す）
    order = [by_expected[j][1] for j in range(len(expected))]
    assert order == sorted(order), f"{page}: 読み順が期待と一致しない: {order}"
    for i, d in enumerate(detected):
        covered = sum(1 for e in expected if _cover(d, e) >= COVER_RATIO)
        assert covered <= 1, f"{page}: detected[{i}] が複数の正解ブロックをまたいでいる"
