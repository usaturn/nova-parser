"""横ブロック生成のゴールデンテスト（スペック 11.3）。実 Vision API は呼ばない。

余剰許容方式: 期待ブロックが全て IoU 閾値以上で 1 対 1 検出されることのみ要求し、
図版内テキスト等に由来する余剰候補ブロックは許容する（検出件数の厳密一致は要求しない）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nova_parser.regional_ocr.layout_horizontal import compute_horizontal_blocks
from nova_parser.regional_ocr.models import BlockRect
from tests.test_regional_layout_golden import COVER_RATIO, _cover, _greedy_match, _iou_threshold

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "regional_layout"

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
    page_area = data["image_width"] * data["image_height"]
    assert len(expected) == expected_count
    matches = _greedy_match(detected, expected)
    by_expected = {j: (iou, i) for iou, i, j in matches}
    for j, exp in enumerate(expected):
        assert j in by_expected, f"{page}: expected[{j}] に対応する検出がない"
        iou, i = by_expected[j]
        thr = _iou_threshold(exp, page_area)
        assert iou >= thr, (
            f"{page}: IoU {iou:.3f} < {thr} (detected[{i}] vs expected[{j}], area={exp['width'] * exp['height']})"
        )
    # 読み順: 期待ブロックへ対応する検出が、検出列内でも同じ順に並ぶ（余剰の混在は許す）
    order = [by_expected[j][1] for j in range(len(expected))]
    assert order == sorted(order), f"{page}: 読み順が期待と一致しない: {order}"
    for i, d in enumerate(detected):
        covered = sum(1 for e in expected if _cover(d, e) >= COVER_RATIO)
        assert covered <= 1, f"{page}: detected[{i}] が複数の正解ブロックをまたいでいる"
