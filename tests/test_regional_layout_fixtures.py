"""ゴールデン fixture の妥当性検証。実 Vision API は呼ばない（スペック 11.1）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "regional_layout"

# スペック 5 の正解データ表
EXPECTED_COUNTS = {
    "ANGEL_GEAR2_p022": 6,
    "ANGEL_GEAR2_p023": 3,
    "ANGEL_GEAR2_p203": 9,
    "ANGEL_GEAR2_p249": 9,
    "ANGEL_GEAR2_p251": 5,
    "ANGEL_GEAR2_p259": 7,
}


@pytest.mark.parametrize(("page", "count"), sorted(EXPECTED_COUNTS.items()))
def test_fixture_exists_and_matches_spec_table(page: str, count: int) -> None:
    path = FIXTURE_DIR / f"{page}.json"
    assert path.exists(), f"fixture 未採取: scripts/capture_layout_fixtures.py を実行すること ({path})"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["image_name"] == f"{page}_00.png"
    assert data["image_width"] > 0 and data["image_height"] > 0
    assert len(data["expected_blocks"]) == count, "正解ブロック数がスペック 5 の表と一致しない"
    assert len(data["paragraph_blocks"]) > 0
    for rect in data["paragraph_blocks"] + data["expected_blocks"]:
        assert rect["x"] >= 0 and rect["y"] >= 0
        assert rect["width"] >= 1 and rect["height"] >= 1
        assert rect["x"] + rect["width"] <= data["image_width"]
        assert rect["y"] + rect["height"] <= data["image_height"]
