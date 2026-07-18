"""縦ブロック生成のゴールデンテスト（スペック 11.3）。実 Vision API は呼ばない。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nova_parser.regional_ocr.layout import compute_vertical_blocks
from nova_parser.regional_ocr.models import BlockRect

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "regional_layout"

# スペック 5 の正解データ表
PAGES = {
    "ANGEL_GEAR2_p022": 6,
    "ANGEL_GEAR2_p023": 3,
    "ANGEL_GEAR2_p203": 9,
    "ANGEL_GEAR2_p249": 9,
    "ANGEL_GEAR2_p251": 5,
    "ANGEL_GEAR2_p259": 7,
}

IOU_MIN = 0.80
COVER_RATIO = 0.5  # 検出矩形が正解ブロックを「覆っている」とみなす正解面積比


def _iou(a: dict, b: dict) -> float:
    ix = max(0, min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"]))
    iy = max(0, min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"]))
    inter = ix * iy
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union else 0.0


def _cover(detected: dict, expected: dict) -> float:
    ix = max(
        0,
        min(detected["x"] + detected["width"], expected["x"] + expected["width"]) - max(detected["x"], expected["x"]),
    )
    iy = max(
        0,
        min(detected["y"] + detected["height"], expected["y"] + expected["height"])
        - max(detected["y"], expected["y"]),
    )
    return (ix * iy) / (expected["width"] * expected["height"])


def _greedy_match(detected: list[dict], expected: list[dict]) -> list[tuple[float, int, int]]:
    """IoU 降順の貪欲法による 1 対 1 対応付け。"""
    pairs = sorted(
        ((_iou(d, e), i, j) for i, d in enumerate(detected) for j, e in enumerate(expected)),
        key=lambda t: t[0],
        reverse=True,
    )
    used_d: set[int] = set()
    used_e: set[int] = set()
    matches: list[tuple[float, int, int]] = []
    for iou, i, j in pairs:
        if iou <= 0 or i in used_d or j in used_e:
            continue
        used_d.add(i)
        used_e.add(j)
        matches.append((iou, i, j))
    return matches


@pytest.mark.parametrize(("page", "expected_count"), sorted(PAGES.items()))
def test_golden_vertical_blocks(page: str, expected_count: int) -> None:
    data = json.loads((FIXTURE_DIR / f"{page}.json").read_text(encoding="utf-8"))
    detected = [
        b.model_dump()
        for b in compute_vertical_blocks(
            data["image_width"],
            data["image_height"],
            [BlockRect(**p) for p in data["paragraph_blocks"]],
        )
    ]
    expected = data["expected_blocks"]
    assert len(expected) == expected_count
    assert len(detected) == expected_count, f"{page}: 検出 {len(detected)} 件 / 期待 {expected_count} 件"
    matches = _greedy_match(detected, expected)
    assert len(matches) == expected_count, f"{page}: 検出と正解を 1 対 1 対応付けできない"
    for iou, i, j in matches:
        assert iou >= IOU_MIN, f"{page}: IoU {iou:.3f} < {IOU_MIN} (detected[{i}] vs expected[{j}])"
    for i, d in enumerate(detected):
        covered = sum(1 for e in expected if _cover(d, e) >= COVER_RATIO)
        assert covered <= 1, f"{page}: detected[{i}] が複数の正解ブロックをまたいでいる"
