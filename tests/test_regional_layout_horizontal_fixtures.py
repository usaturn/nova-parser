"""横ブロックゴールデン fixture の妥当性検証。実 Vision API は呼ばない（スペック 11.1）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from scripts.capture_layout_fixtures import locate_crop

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "regional_layout"
ROOT = Path(__file__).resolve().parents[1]  # リポジトリルート（tests/ の親）
SAMPLE_DIR = ROOT / "Images" / "EG_Silver_Wing" / "sample"

# スペック 5 の正解データ表
EXPECTED_COUNTS = {
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


@pytest.mark.parametrize(("page", "count"), sorted(EXPECTED_COUNTS.items()))
def test_fixture_exists_and_matches_spec_table(page: str, count: int) -> None:
    path = FIXTURE_DIR / f"{page}.json"
    assert path.exists(), f"fixture 未採取: scripts/capture_horizontal_layout_fixtures.py を実行すること ({path})"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["image_name"] == f"{page}_00.png"
    assert data["image_width"] > 0 and data["image_height"] > 0
    assert len(data["expected_horizontal_blocks"]) == count, "正解ブロック数がスペック 5 の表と一致しない"
    assert len(data["paragraph_blocks"]) > 0
    for rect in data["paragraph_blocks"] + data["expected_horizontal_blocks"]:
        assert rect["x"] >= 0 and rect["y"] >= 0
        assert rect["width"] >= 1 and rect["height"] >= 1
        assert rect["x"] + rect["width"] <= data["image_width"]
        assert rect["y"] + rect["height"] <= data["image_height"]


@pytest.mark.parametrize("page", sorted(EXPECTED_COUNTS))
def test_expected_blocks_match_locate_crop_when_samples_exist(page: str) -> None:
    original_path = SAMPLE_DIR / f"{page}_00.png"
    if not original_path.is_file():
        pytest.skip(f"sample images not present: {original_path}")
    data = json.loads((FIXTURE_DIR / f"{page}.json").read_text(encoding="utf-8"))
    original = Image.open(original_path).convert("RGB")
    crops: list[dict[str, int]] = []
    for crop_path in sorted(SAMPLE_DIR.glob(f"{page}_*.png")):
        if crop_path.name == original_path.name:
            continue
        crop = Image.open(crop_path).convert("RGB")
        x, y = locate_crop(original, crop)
        crops.append({"x": x, "y": y, "width": crop.width, "height": crop.height})
    assert len(crops) == len(data["expected_horizontal_blocks"])
    for i, (got, exp) in enumerate(zip(crops, data["expected_horizontal_blocks"], strict=True)):
        assert {k: exp[k] for k in ("x", "y", "width", "height")} == got, f"{page} expected[{i}]"
