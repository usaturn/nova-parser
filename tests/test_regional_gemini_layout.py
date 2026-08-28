from __future__ import annotations

import json
from pathlib import Path

import pytest

from nova_parser.regional_ocr.gemini_layout import (
    classify_layout,
    groups_from_expected,
    load_examples,
    merge_candidate_groups,
    validate_candidate_groups,
)
from nova_parser.regional_ocr.models import BlockRect
from scripts.build_gemini_vertical_examples import build_example_bank


def test_classify_layout_uses_orientation_and_candidate_density() -> None:
    assert classify_layout(1000, 1500, 20) == "portrait"
    assert classify_layout(1500, 1000, 79) == "landscape_sparse"
    assert classify_layout(1500, 1000, 80) == "landscape_dense"


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"groups": []}, "at least one group"),
        ({"groups": [{"candidate_ids": []}]}, "empty group"),
        ({"groups": [{"candidate_ids": [2]}]}, "out of range"),
        ({"groups": [{"candidate_ids": [0]}, {"candidate_ids": [0]}]}, "duplicate"),
        ({"groups": [{"candidate_ids": ["0"]}]}, "integer"),
    ],
)
def test_validate_candidate_groups_rejects_invalid_payload(payload: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_candidate_groups(payload, candidate_count=2)


def test_merge_candidate_groups_returns_bounding_rectangles() -> None:
    candidates = [
        BlockRect(x=10, y=20, width=30, height=40),
        BlockRect(x=8, y=80, width=35, height=20),
        BlockRect(x=200, y=10, width=50, height=60),
    ]
    assert merge_candidate_groups(candidates, [[0, 1], [2]]) == [
        BlockRect(x=8, y=20, width=35, height=80),
        BlockRect(x=200, y=10, width=50, height=60),
    ]


def test_build_example_bank_contains_fixed_text_only_references() -> None:
    bank = build_example_bank(Path("tests/fixtures/regional_layout_test"))
    assert {item["family"] for item in bank["examples"]} == {
        "portrait",
        "landscape_sparse",
        "landscape_dense",
    }
    assert [item["stem"] for item in bank["examples"]] == [
        "WaresBrade_P034",
        "WaresBrade_P040",
        "WaresBrade_P053",
        "warse_rule_p18",
        "warse_rule_p42",
        "warse_start_p20",
        "warse_start_p42",
    ]
    serialized = json.dumps(bank, ensure_ascii=False)
    assert "image_bytes" not in serialized
    assert "Images/TEST" not in serialized


def test_groups_from_expected_assigns_each_candidate_at_most_once_by_center() -> None:
    candidates = [
        BlockRect(x=10, y=10, width=30, height=30),
        BlockRect(x=10, y=60, width=30, height=30),
        BlockRect(x=200, y=10, width=20, height=20),
    ]
    expected = [
        BlockRect(x=0, y=0, width=100, height=100),
        BlockRect(x=0, y=0, width=300, height=100),
    ]
    assert groups_from_expected(candidates, expected) == [[0, 1], [2]]


def test_load_examples_filters_by_family() -> None:
    portrait = load_examples("portrait")
    assert [example.stem for example in portrait] == [
        "WaresBrade_P034",
        "WaresBrade_P040",
        "WaresBrade_P053",
    ]
    dense = load_examples("landscape_dense")
    assert [example.stem for example in dense] == ["warse_start_p20", "warse_start_p42"]
    assert all(example.candidates and example.groups for example in portrait + dense)
