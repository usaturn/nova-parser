from __future__ import annotations

from types import SimpleNamespace

from google.genai import types

from scripts.evaluate_gemini_layout import (
    denormalize_boxes,
    generate_boxes_with_token_retry,
    groups_from_expected,
    merge_candidate_groups,
    score_detections,
)


def test_denormalize_boxes_converts_yxyx_and_clamps_to_image() -> None:
    boxes = denormalize_boxes(
        [[100, 200, 500, 600], [-10, 900, 1010, 1200]],
        image_width=1000,
        image_height=2000,
    )

    assert boxes == [
        {"x": 200, "y": 200, "width": 400, "height": 800},
        {"x": 900, "y": 0, "width": 100, "height": 2000},
    ]


def test_denormalize_boxes_drops_degenerate_rectangles() -> None:
    boxes = denormalize_boxes([[500, 500, 500, 700], [800, 900, 700, 950]], 1000, 1000)

    assert boxes == []


def test_score_detections_reports_one_to_one_iou_precision_and_recall() -> None:
    expected = [
        {"x": 0, "y": 0, "width": 100, "height": 100},
        {"x": 200, "y": 0, "width": 100, "height": 100},
    ]
    detected = [
        {"x": 0, "y": 0, "width": 100, "height": 100},
        {"x": 210, "y": 0, "width": 100, "height": 100},
        {"x": 500, "y": 500, "width": 20, "height": 20},
    ]

    score = score_detections(detected, expected, threshold=0.5)

    assert score["detected"] == 3
    assert score["expected"] == 2
    assert score["true_positive"] == 2
    assert score["mean_iou"] == 0.9091
    assert score["precision"] == 0.6667
    assert score["recall"] == 1.0


def test_generate_boxes_with_token_retry_retries_only_truncated_json() -> None:
    limits: list[int] = []

    def generate(max_output_tokens: int) -> SimpleNamespace:
        limits.append(max_output_tokens)
        if len(limits) == 1:
            return SimpleNamespace(
                text='{"blocks": [{"box_2d": [0, 0',
                candidates=[SimpleNamespace(finish_reason=types.FinishReason.MAX_TOKENS)],
            )
        return SimpleNamespace(
            text='{"blocks": [{"box_2d": [0, 0, 1000, 1000]}]}',
            candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)],
        )

    boxes, _ = generate_boxes_with_token_retry(generate)

    assert boxes == [[0, 0, 1000, 1000]]
    assert limits == [2048, 8192]


def test_groups_from_expected_assigns_each_candidate_at_most_once_by_center() -> None:
    candidates = [
        {"x": 10, "y": 10, "width": 30, "height": 30},
        {"x": 10, "y": 60, "width": 30, "height": 30},
        {"x": 200, "y": 10, "width": 20, "height": 20},
    ]
    expected = [
        {"x": 0, "y": 0, "width": 100, "height": 100},
        {"x": 0, "y": 0, "width": 300, "height": 100},
    ]

    groups = groups_from_expected(candidates, expected)

    assert groups == [{"candidate_ids": [0, 1]}, {"candidate_ids": [2]}]


def test_merge_candidate_groups_returns_group_bounding_boxes() -> None:
    candidates = [
        {"x": 10, "y": 20, "width": 30, "height": 40},
        {"x": 8, "y": 80, "width": 35, "height": 20},
        {"x": 200, "y": 10, "width": 50, "height": 60},
    ]

    merged = merge_candidate_groups(candidates, [{"candidate_ids": [0, 1]}, {"candidate_ids": [2]}])

    assert merged == [
        {"x": 8, "y": 20, "width": 35, "height": 80},
        {"x": 200, "y": 10, "width": 50, "height": 60},
    ]
