from __future__ import annotations

import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "regional_layout_test"

EXPECTED_COUNTS = {
    "WaresBrade_P034": 5,
    "WaresBrade_P035": 2,
    "WaresBrade_P040": 2,
    "WaresBrade_P041": 2,
    "WaresBrade_P042": 2,
    "WaresBrade_P043": 2,
    "WaresBrade_P050": 2,
    "WaresBrade_P051": 2,
    "WaresBrade_P053": 3,
    "WaresBrade_P054": 2,
    "WaresBrade_P055": 2,
    "WaresBrade_P074": 3,
    "WaresBrade_P075": 3,
    "WaresBrade_P082": 3,
    "WaresBrade_P118": 2,
    "WaresBrade_P156": 2,
    "WaresBrade_P260": 3,
    "WaresBrade_P261": 2,
    "warse_rule_p18": 8,
    "warse_rule_p26": 7,
    "warse_rule_p42": 6,
    "warse_start_p20": 8,
    "warse_start_p24": 6,
    "warse_start_p42": 6,
}


def test_test_layout_fixtures_are_complete_and_in_bounds() -> None:
    assert sum(EXPECTED_COUNTS.values()) == 85
    for stem, expected_count in EXPECTED_COUNTS.items():
        fixture = json.loads((FIXTURE_DIR / f"{stem}.json").read_text(encoding="utf-8"))
        assert len(fixture["paragraph_blocks"]) > 0
        assert len(fixture["expected_blocks"]) == expected_count
        for rect in fixture["paragraph_blocks"] + fixture["expected_blocks"]:
            assert rect["x"] >= 0 and rect["y"] >= 0
            assert rect["width"] >= 1 and rect["height"] >= 1
            assert rect["x"] + rect["width"] <= fixture["image_width"]
            assert rect["y"] + rect["height"] <= fixture["image_height"]


def test_warse_start_p24_preserves_intentional_full_page_sample() -> None:
    fixture = json.loads((FIXTURE_DIR / "warse_start_p24.json").read_text(encoding="utf-8"))

    assert {
        "x": 0,
        "y": 0,
        "width": fixture["image_width"],
        "height": fixture["image_height"],
    } in fixture["expected_blocks"]
