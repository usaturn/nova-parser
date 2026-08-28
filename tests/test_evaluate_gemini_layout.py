from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import types

import nova_parser.regional_ocr.gemini_layout as gemini_layout
from nova_parser.regional_ocr.gemini_layout import PROMPT_CONTRACT_VERSION
from nova_parser.regional_ocr.models import BlockRect
from scripts.evaluate_gemini_layout import (
    _PROMPT_CONTRACT_VERSION,
    _image_part,
    denormalize_boxes,
    evaluation_cache_fingerprint,
    generate_boxes_with_token_retry,
    generate_json_with_token_retry,
    generate_vertical_blocks,
    groups_from_expected,
    main,
    merge_candidate_groups,
    parse_args,
    production_evaluation_cache_fingerprint,
    score_detections,
)


def _fixture(image_name: str = "page.webp") -> dict[str, object]:
    return {
        "image_name": image_name,
        "image_width": 100,
        "image_height": 200,
        "paragraph_blocks": [{"x": 1, "y": 2, "width": 3, "height": 4}],
        "expected_blocks": [{"x": 0, "y": 0, "width": 10, "height": 20}],
    }


def test_evaluation_cache_fingerprint_covers_model_images_fixtures_and_examples(tmp_path: Path) -> None:
    target_path = tmp_path / "page.webp"
    example_path = tmp_path / "example.webp"
    target_path.write_bytes(b"target-v1")
    example_path.write_bytes(b"example-v1")
    fixture = _fixture()
    examples = [("example", _fixture("example.webp"), example_path)]

    original = evaluation_cache_fingerprint(
        method="gemini-group-fewshot",
        model="model-a",
        fixture=fixture,
        image_path=target_path,
        examples=examples,
    )

    assert original == evaluation_cache_fingerprint(
        method="gemini-group-fewshot",
        model="model-a",
        fixture=fixture,
        image_path=target_path,
        examples=examples,
    )
    assert original != evaluation_cache_fingerprint(
        method="gemini-group-fewshot",
        model="model-b",
        fixture=fixture,
        image_path=target_path,
        examples=examples,
    )
    example_path.write_bytes(b"example-v2")
    assert original != evaluation_cache_fingerprint(
        method="gemini-group-fewshot",
        model="model-a",
        fixture=fixture,
        image_path=target_path,
        examples=examples,
    )
    example_path.write_bytes(b"example-v1")
    target_path.write_bytes(b"target-v2")
    assert original != evaluation_cache_fingerprint(
        method="gemini-group-fewshot",
        model="model-a",
        fixture=fixture,
        image_path=target_path,
        examples=examples,
    )
    target_path.write_bytes(b"target-v1")
    assert original != evaluation_cache_fingerprint(
        method="gemini-group-fewshot",
        model="model-a",
        fixture={**fixture, "image_width": 101},
        image_path=target_path,
        examples=examples,
    )


def test_image_part_uses_jpeg_mime_type(tmp_path: Path) -> None:
    path = tmp_path / "page.jpg"
    path.write_bytes(b"jpeg")

    part = _image_part(path)

    assert part.inline_data is not None
    assert part.inline_data.mime_type == "image/jpeg"


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


def test_score_detections_maximizes_matches_above_threshold() -> None:
    expected = [
        {"x": 0, "y": 0, "width": 10, "height": 10},
        {"x": 3, "y": 0, "width": 10, "height": 10},
    ]
    detected = [
        {"x": 0, "y": 0, "width": 10, "height": 10},
        {"x": 0, "y": 0, "width": 7, "height": 10},
    ]

    score = score_detections(detected, expected, threshold=0.5)

    # IoU降順の貪欲法では完全一致を先に選んでTP=1になるが、
    # D0→E1 (0.5385), D1→E0 (0.7) なら2件とも閾値を満たす。
    assert score["matched"] == 2
    assert score["true_positive"] == 2
    assert score["mean_iou"] == 0.6192
    assert score["precision"] == 1.0
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

    boxes, responses = generate_boxes_with_token_retry(generate)

    assert boxes == [[0, 0, 1000, 1000]]
    assert limits == [2048, 8192]
    assert len(responses) == 2


def test_generate_json_with_token_retry_supports_group_responses() -> None:
    limits: list[int] = []

    def generate(max_output_tokens: int) -> SimpleNamespace:
        limits.append(max_output_tokens)
        if len(limits) == 1:
            return SimpleNamespace(
                text='{"groups": [{"candidate_ids": [0, 1]',
                candidates=[SimpleNamespace(finish_reason=types.FinishReason.MAX_TOKENS)],
            )
        return SimpleNamespace(
            text='{"groups": [{"candidate_ids": [0, 1]}]}',
            candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)],
        )

    parsed, responses = generate_json_with_token_retry(generate)

    assert parsed == {"groups": [{"candidate_ids": [0, 1]}]}
    assert limits == [2048, 8192]
    assert len(responses) == 2


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


def test_parse_args_accepts_gemini_production() -> None:
    args = parse_args(["Images/TEST", "--method", "gemini-production"])

    assert args.method == "gemini-production"
    assert args.sample_dir == Path("Images/TEST")
    assert args.iou_threshold == 0.5


@pytest.mark.parametrize(
    "method",
    ("local", "gemini-zero", "gemini-one", "gemini-group-fewshot"),
)
def test_parse_args_keeps_comparison_methods(method: str) -> None:
    args = parse_args(["Images/TEST", "--method", method])

    assert args.method == method


def test_gemini_production_binds_production_generate_vertical_blocks() -> None:
    assert generate_vertical_blocks is gemini_layout.generate_vertical_blocks


def test_production_evaluation_cache_fingerprint_includes_contract_and_example_bank(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.evaluate_gemini_layout as evaluator

    image_path = tmp_path / "page.webp"
    image_path.write_bytes(b"target-v1")
    fixture = _fixture()
    candidates = [BlockRect(x=1, y=2, width=3, height=4)]
    kwargs = {
        "method": "gemini-production",
        "model": "gemini-3.5-flash-lite",
        "fixture": fixture,
        "image_path": image_path,
        "candidates": candidates,
    }

    original = production_evaluation_cache_fingerprint(**kwargs)
    eval_fingerprint = evaluation_cache_fingerprint(
        method="gemini-production",
        model="gemini-3.5-flash-lite",
        fixture=fixture,
        image_path=image_path,
        examples=[],
    )

    assert original == production_evaluation_cache_fingerprint(**kwargs)
    assert original != eval_fingerprint
    assert PROMPT_CONTRACT_VERSION == "regional-vertical-groups-v1"
    assert PROMPT_CONTRACT_VERSION != _PROMPT_CONTRACT_VERSION

    monkeypatch.setattr(evaluator, "example_bank_sha256", lambda: "bank-changed")
    bank_changed = production_evaluation_cache_fingerprint(**kwargs)
    assert original != bank_changed
    monkeypatch.setattr(evaluator, "PROMPT_CONTRACT_VERSION", "regional-layout-eval-v1")
    assert bank_changed != production_evaluation_cache_fingerprint(**kwargs)


def test_gemini_production_uses_generate_vertical_blocks_and_scores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.evaluate_gemini_layout as evaluator

    fixture_dir = tmp_path / "fixtures"
    sample_dir = tmp_path / "images"
    output_dir = tmp_path / "out"
    fixture_dir.mkdir()
    sample_dir.mkdir()
    image_path = sample_dir / "page.webp"
    image_path.write_bytes(b"webp-bytes")
    fixture = {
        "image_name": "page.webp",
        "image_width": 100,
        "image_height": 200,
        "paragraph_blocks": [{"x": 10, "y": 20, "width": 30, "height": 40}],
        "expected_blocks": [{"x": 5, "y": 5, "width": 50, "height": 80}],
    }
    (fixture_dir / "page.json").write_text(json.dumps(fixture), encoding="utf-8")
    expected_candidates = [BlockRect(**block) for block in evaluator._local_candidates(fixture)]
    returned = [BlockRect(x=5, y=5, width=50, height=80)]
    calls: list[dict[str, object]] = []

    def fake_generate(
        image_path_arg: Path,
        candidates: object,
        **kwargs: object,
    ) -> list[BlockRect]:
        calls.append(
            {
                "image_path": image_path_arg,
                "candidates": list(candidates),  # type: ignore[arg-type]
                "source_block_count": kwargs.get("source_block_count"),
            }
        )
        return returned

    def reject_eval_rebuild(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("gemini-production must not rebuild evaluator prompts or merge")

    monkeypatch.setattr(evaluator, "generate_vertical_blocks", fake_generate)
    monkeypatch.setattr(evaluator, "_predict", reject_eval_rebuild)
    monkeypatch.setattr(evaluator, "_predict_groups", reject_eval_rebuild)
    monkeypatch.setattr(evaluator, "_instructions", reject_eval_rebuild)
    monkeypatch.setattr(evaluator, "_group_instructions", reject_eval_rebuild)
    monkeypatch.setattr(evaluator, "merge_candidate_groups", reject_eval_rebuild)

    main(
        [
            str(sample_dir),
            "--method",
            "gemini-production",
            "--fixture-dir",
            str(fixture_dir),
            "--output-dir",
            str(output_dir),
            "--iou-threshold",
            "0.5",
        ]
    )

    assert calls == [
        {
            "image_path": image_path,
            "candidates": expected_candidates,
            "source_block_count": len(fixture["paragraph_blocks"]),
        }
    ]
    result = json.loads((output_dir / "gemini-production" / "page.json").read_text(encoding="utf-8"))
    assert result["detected_blocks"] == [block.model_dump() for block in returned]
    assert result["true_positive"] == 1
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["metadata"]["prompt_contract_version"] == PROMPT_CONTRACT_VERSION
    assert result["metadata"]["prompt_contract_version"] != _PROMPT_CONTRACT_VERSION
    summary = json.loads((output_dir / "gemini-production" / "summary.json").read_text(encoding="utf-8"))
    assert summary["pages"] == 1
    assert summary["true_positive"] == 1
