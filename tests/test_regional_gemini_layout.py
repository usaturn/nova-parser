from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import types
from PIL import Image

import nova_parser.regional_ocr.gemini_layout as gemini_layout
from nova_parser.regional_ocr.gemini_layout import (
    GeminiLayoutError,
    classify_layout,
    generate_vertical_blocks,
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


def test_example_bank_families_match_paragraph_density_contract() -> None:
    """bank の family は paragraph_blocks 長による classify_layout と一致する。"""
    fixture_dir = Path("tests/fixtures/regional_layout_test")
    bank = build_example_bank(fixture_dir)
    expected_families = {
        "WaresBrade_P034": "portrait",
        "WaresBrade_P040": "portrait",
        "WaresBrade_P053": "portrait",
        "warse_rule_p18": "landscape_sparse",
        "warse_rule_p42": "landscape_sparse",
        "warse_start_p20": "landscape_dense",
        "warse_start_p42": "landscape_dense",
    }
    assert {item["stem"]: item["family"] for item in bank["examples"]} == expected_families
    for item in bank["examples"]:
        fixture = json.loads((fixture_dir / f"{item['stem']}.json").read_text(encoding="utf-8"))
        assert item["family"] == classify_layout(
            int(fixture["image_width"]),
            int(fixture["image_height"]),
            len(fixture["paragraph_blocks"]),
        )


class FakeModels:
    def __init__(self, owner: "FakeGenaiClient", response_text: str) -> None:
        self.owner = owner
        self.response_text = response_text

    def generate_content(self, *, model: str, contents: list[types.Content], config: types.GenerateContentConfig):
        self.owner.calls.append({"model": model, "contents": contents, "config": config})
        text, finish_reason = self.owner.next_response()
        return SimpleNamespace(
            text=text,
            candidates=[SimpleNamespace(finish_reason=finish_reason)],
        )


class FakeGenaiClient:
    def __init__(
        self,
        response_text: str,
        *,
        finish_reason: object = types.FinishReason.STOP,
        responses: list[tuple[str, object]] | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self._response_text = response_text
        self._finish_reason = finish_reason
        self._responses = list(responses) if responses is not None else None
        self.models = FakeModels(self, response_text)

    def next_response(self) -> tuple[str, object]:
        if self._responses is not None:
            return self._responses.pop(0)
        return self._response_text, self._finish_reason


def test_generate_vertical_blocks_sends_image_candidates_and_minimal_thinking(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (100, 200), "white").save(image_path)
    fake = FakeGenaiClient('{"groups":[{"candidate_ids":[0,1]}]}')
    candidates = [
        BlockRect(x=10, y=10, width=30, height=40),
        BlockRect(x=10, y=60, width=30, height=40),
    ]

    result = generate_vertical_blocks(image_path, candidates, client_factory=lambda: fake)

    assert result == [BlockRect(x=10, y=10, width=30, height=90)]
    call = fake.calls[0]
    assert call["model"] == "gemini-3.5-flash-lite"
    assert call["config"].temperature == 0
    assert call["config"].thinking_config.thinking_level == types.ThinkingLevel.MINIMAL
    assert call["config"].max_output_tokens == 2048
    assert "candidate_ids" in json.dumps(call["config"].response_json_schema)


def _two_candidates() -> list[BlockRect]:
    return [
        BlockRect(x=10, y=10, width=30, height=40),
        BlockRect(x=10, y=60, width=30, height=40),
    ]


def _write_rgb(tmp_path: Path, name: str, size: tuple[int, int]) -> Path:
    image_path = tmp_path / name
    Image.new("RGB", size, "white").save(image_path)
    return image_path


def test_generate_vertical_blocks_retries_only_when_json_is_truncated_by_max_tokens(tmp_path: Path) -> None:
    image_path = _write_rgb(tmp_path, "page.png", (100, 200))
    fake = FakeGenaiClient(
        "",
        responses=[
            ('{"groups":[{"candidate_ids":[0,1]', types.FinishReason.MAX_TOKENS),
            ('{"groups":[{"candidate_ids":[0,1]}]}', types.FinishReason.STOP),
        ],
    )

    result = generate_vertical_blocks(image_path, _two_candidates(), client_factory=lambda: fake)

    assert result == [BlockRect(x=10, y=10, width=30, height=90)]
    assert [call["config"].max_output_tokens for call in fake.calls] == [2048, 8192]


def test_generate_vertical_blocks_does_not_retry_valid_json_truncated_finish_reason(tmp_path: Path) -> None:
    image_path = _write_rgb(tmp_path, "page.png", (100, 200))
    fake = FakeGenaiClient(
        '{"groups":[{"candidate_ids":[0,1]}]}',
        finish_reason=types.FinishReason.MAX_TOKENS,
    )

    result = generate_vertical_blocks(image_path, _two_candidates(), client_factory=lambda: fake)

    assert result == [BlockRect(x=10, y=10, width=30, height=90)]
    assert [call["config"].max_output_tokens for call in fake.calls] == [2048]


def test_generate_vertical_blocks_rejects_invalid_json_on_stop_without_retry(tmp_path: Path) -> None:
    image_path = _write_rgb(tmp_path, "page.png", (100, 200))
    fake = FakeGenaiClient("{not-json")

    with pytest.raises(GeminiLayoutError, match="Gemini vertical layout generation failed") as exc_info:
        generate_vertical_blocks(image_path, _two_candidates(), client_factory=lambda: fake)

    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)
    assert [call["config"].max_output_tokens for call in fake.calls] == [2048]


def test_generate_vertical_blocks_uses_source_block_count_for_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_path = _write_rgb(tmp_path, "page.png", (200, 100))
    seen: list[str] = []
    original = gemini_layout.load_examples

    def spy(family: str) -> list[object]:
        seen.append(family)
        return original(family)

    monkeypatch.setattr(gemini_layout, "load_examples", spy)
    fake = FakeGenaiClient('{"groups":[{"candidate_ids":[0]}]}')
    candidates = [BlockRect(x=10, y=10, width=30, height=40)]

    generate_vertical_blocks(image_path, candidates, client_factory=lambda: fake, source_block_count=80)
    generate_vertical_blocks(image_path, candidates, client_factory=lambda: fake, source_block_count=79)

    assert seen == ["landscape_dense", "landscape_sparse"]


def test_generate_vertical_blocks_uses_text_few_shot_and_attaches_only_target_image(tmp_path: Path) -> None:
    image_path = _write_rgb(tmp_path, "page.png", (100, 200))
    fake = FakeGenaiClient('{"groups":[{"candidate_ids":[0,1]}]}')

    generate_vertical_blocks(image_path, _two_candidates(), client_factory=lambda: fake)

    contents = fake.calls[0]["contents"]
    examples = load_examples("portrait")
    assert len(contents) == 2 * len(examples) + 1
    for index, content in enumerate(contents[:-1]):
        assert content.role == ("user" if index % 2 == 0 else "model")
        assert all(getattr(part, "inline_data", None) is None for part in content.parts)
    last = contents[-1]
    assert last.role == "user"
    image_parts = [part for part in last.parts if getattr(part, "inline_data", None) is not None]
    assert len(image_parts) == 1
    assert image_parts[0].inline_data.mime_type == "image/png"


def test_generate_vertical_blocks_rejects_unknown_image_type(tmp_path: Path) -> None:
    image_path = tmp_path / "page.gif"
    Image.new("RGB", (100, 200), "white").save(image_path, format="GIF")
    fake = FakeGenaiClient('{"groups":[{"candidate_ids":[0,1]}]}')

    with pytest.raises(GeminiLayoutError, match="Gemini vertical layout generation failed") as exc_info:
        generate_vertical_blocks(image_path, _two_candidates(), client_factory=lambda: fake)

    assert isinstance(exc_info.value.__cause__, KeyError)
    assert fake.calls == []


def test_generate_vertical_blocks_wraps_invalid_groups(tmp_path: Path) -> None:
    image_path = _write_rgb(tmp_path, "page.png", (100, 200))
    fake = FakeGenaiClient('{"groups":[{"candidate_ids":[9]}]}')

    with pytest.raises(GeminiLayoutError, match="Gemini vertical layout generation failed") as exc_info:
        generate_vertical_blocks(image_path, _two_candidates(), client_factory=lambda: fake)

    assert isinstance(exc_info.value.__cause__, ValueError)


def test_generate_vertical_blocks_wraps_sdk_errors(tmp_path: Path) -> None:
    image_path = _write_rgb(tmp_path, "page.png", (100, 200))

    class BoomModels:
        def generate_content(self, **kwargs: object) -> object:
            raise RuntimeError("sdk down")

    class BoomClient:
        models = BoomModels()

    with pytest.raises(GeminiLayoutError, match="Gemini vertical layout generation failed") as exc_info:
        generate_vertical_blocks(image_path, _two_candidates(), client_factory=lambda: BoomClient())

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert str(exc_info.value.__cause__) == "sdk down"


def test_generate_vertical_blocks_calls_backend_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = _write_rgb(tmp_path, "page.png", (100, 200))
    fake = FakeGenaiClient('{"groups":[{"candidate_ids":[0,1]}]}')
    calls: list[bool] = []
    original = gemini_layout.gemini_backend.call_with_backend_fallback

    def spy(fn: object) -> object:
        calls.append(True)
        return original(fn)

    monkeypatch.setattr(gemini_layout.gemini_backend, "call_with_backend_fallback", spy)

    generate_vertical_blocks(image_path, _two_candidates(), client_factory=lambda: fake)

    assert calls == [True]
