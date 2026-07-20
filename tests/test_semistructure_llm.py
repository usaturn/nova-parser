"""LLM構造推定を参照選択に限定する契約テスト。"""

from __future__ import annotations

from typing import Any

import pytest

from nova_parser.semistructure.llm import (
    PROMPT_CONTRACT_VERSION,
    GeminiStructureClassifier,
    build_structure_response_schema,
    build_structure_windows,
)
from nova_parser.semistructure.models import Audience, StructureProposal
from nova_parser.semistructure.prompts import STRUCTURE_CLASSIFICATION_RULES
from tests.semistructure_factories import make_block, make_manifest, make_window


class FakeGenerateJSON:
    """呼び出し内容を記録して固定結果を返す偽generate_json。"""

    def __init__(self, *results: dict[str, Any] | BaseException) -> None:
        self.results = list(results)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, contents: list[Any], **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"contents": contents, **kwargs})
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        validator = kwargs.get("result_validator")
        if validator is not None:
            validator(result)
        return result


def valid_result(block_ids: list[str] | None = None, **overrides: Any) -> dict[str, Any]:
    """有効な分類レスポンスを作る。"""
    segment = {
        "block_ids": block_ids or ["b1"],
        "section_path": ["ルール"],
        "content_type": "rule.explanation",
        "audience": "shared",
        "entities": [],
    }
    segment.update(overrides)
    return {"segments": [segment]}


def test_structure_schema_contains_block_references_but_no_generated_text() -> None:
    schema = build_structure_response_schema()
    segment_properties = schema["properties"]["segments"]["items"]["properties"]

    assert "block_ids" in segment_properties
    assert "normalized_text" not in segment_properties
    assert "summary" not in segment_properties
    assert segment_properties["entities"]["items"]["minLength"] == 1


def test_prompt_contains_all_reference_selection_prohibitions_verbatim() -> None:
    assert "- 本文、要約、訂正文を生成しない。" in STRUCTURE_CLASSIFICATION_RULES
    assert "- 出力できる block_id は入力に存在するものだけとする。" in STRUCTURE_CLASSIFICATION_RULES
    assert "- block_id の順序を変更しない。" in STRUCTURE_CLASSIFICATION_RULES
    assert (
        "- GMを継承した範囲を player/shared に変更したい場合も audience は gm のままとし、\n"
        "  review_reasons に audience_downgrade_candidate を追加する。"
    ) in STRUCTURE_CLASSIFICATION_RULES
    assert "- entities は入力本文に完全一致する文字列だけを返す。" in STRUCTURE_CLASSIFICATION_RULES


def test_classifier_rejects_unknown_block_id() -> None:
    fake = FakeGenerateJSON(valid_result(["missing"]))
    classifier = GeminiStructureClassifier(generate_json=fake)

    with pytest.raises(ValueError, match="未知の block_id"):
        classifier.classify(make_window(block_ids=["b1"]))


def test_classifier_rejects_reordered_or_repeated_block_ids() -> None:
    fake = FakeGenerateJSON(valid_result(["b2", "b1"]))
    classifier = GeminiStructureClassifier(generate_json=fake)

    with pytest.raises(ValueError, match="順序"):
        classifier.classify(make_window(block_ids=["b1", "b2"]))


def test_classifier_rejects_entity_not_present_verbatim_in_selected_blocks() -> None:
    fake = FakeGenerateJSON(valid_result(entities=["存在しない語"]))
    classifier = GeminiStructureClassifier(generate_json=fake)

    with pytest.raises(ValueError, match="原文に完全一致"):
        classifier.classify(make_window(blocks=[make_block(text="実在する本文")]))


def test_classifier_rejects_entity_spanning_two_source_blocks() -> None:
    fake = FakeGenerateJSON(valid_result(["b1", "b2"], entities=["前後"]))
    classifier = GeminiStructureClassifier(generate_json=fake)

    with pytest.raises(ValueError, match="原文に完全一致"):
        classifier.classify(
            make_window(
                blocks=[
                    make_block("b1", text="前"),
                    make_block("b2", text="後"),
                ]
            )
        )


def test_classifier_sends_unchanged_raw_text_for_entity_selection() -> None:
    fake = FakeGenerateJSON(valid_result(entities=["原 文"]))
    classifier = GeminiStructureClassifier(generate_json=fake)
    block = make_block(raw_text="原 文", normalized_text="原文")

    result = classifier.classify(make_window(blocks=[block]))

    assert result.segments[0].entities == ["原 文"]
    sent = str(fake.calls[0]["contents"])
    assert "原 文" in sent
    assert block.raw_text == "原 文"


def test_classifier_keeps_inherited_gm_and_marks_downgrade_for_review() -> None:
    fake = FakeGenerateJSON(valid_result(audience="player"))
    classifier = GeminiStructureClassifier(generate_json=fake)

    result = classifier.classify(make_window(blocks=[make_block(inherited_audience=Audience.GM)]))

    assert result.segments[0].audience == Audience.GM
    assert "audience_downgrade_candidate" in result.segments[0].review_reasons


def test_classifier_uses_existing_generate_json_contract() -> None:
    fake = FakeGenerateJSON(valid_result())
    classifier = GeminiStructureClassifier(generate_json=fake, model="test-model")

    result = classifier.classify(make_window())

    assert isinstance(result, StructureProposal)
    assert fake.calls[0]["temperature"] == 0.0
    assert fake.calls[0]["model"] == "test-model"
    assert fake.calls[0]["response_json_schema"] == build_structure_response_schema()
    assert callable(fake.calls[0]["result_validator"])
    assert fake.calls[0]["failure_artifact"].mode == "semistructure_classify"
    assert result.classifier_id == classifier.classifier_id
    assert result.prompt_contract_version == PROMPT_CONTRACT_VERSION
    assert result.input_sha256.startswith("sha256:")
    assert len(result.input_sha256) == 71


def test_outline_sends_only_compact_block_samples_and_is_inferred_once() -> None:
    raw = "秘密の原文"
    long_text = "章タイトル\n" + ("あ" * 150) + raw
    fake = FakeGenerateJSON(
        {
            "sections": [
                {
                    "title": "第一章",
                    "start_page": 22,
                    "end_page": 23,
                    "default_content_type": "rule.explanation",
                }
            ]
        }
    )
    classifier = GeminiStructureClassifier(generate_json=fake)
    blocks = [
        make_block("b1", text=long_text, page=22),
        make_block("b2", text="次章", page=23),
    ]

    first = classifier.infer_outline(blocks)
    second = classifier.infer_outline(blocks)

    assert first == second
    assert len(fake.calls) == 1
    sent = str(fake.calls[0]["contents"])
    assert raw not in sent
    assert "あ" * 114 in sent
    assert "あ" * 115 not in sent


def test_outline_failure_falls_back_deterministically_to_unknown_manifest_range() -> None:
    fake = FakeGenerateJSON(RuntimeError("backend unavailable"))
    classifier = GeminiStructureClassifier(
        manifest=make_manifest(),
        generate_json=fake,
    )
    blocks = [make_block("b1", page=20), make_block("b2", page=24)]

    outline = classifier.infer_outline(blocks)

    assert outline.book_id == "eg-test"
    assert len(outline.sections) == 1
    assert outline.sections[0].title == "unknown"
    assert outline.sections[0].start_page == 20
    assert outline.sections[0].end_page == 24
    assert outline.sections[0].default_content_type == "unknown"


def test_classify_window_exposes_only_center_page_ids_to_validator() -> None:
    fake = FakeGenerateJSON(valid_result(["prev"]))
    classifier = GeminiStructureClassifier(generate_json=fake)
    window = make_window(
        blocks=[
            make_block("prev", page=21),
            make_block("center", page=22),
            make_block("next", page=23),
        ],
        center_page=22,
    )

    with pytest.raises(ValueError, match="中心ページ"):
        classifier.classify(window)


def test_classify_window_may_use_context_but_returns_center_blocks_only() -> None:
    fake = FakeGenerateJSON(valid_result(["center"], entities=["中心"]))
    classifier = GeminiStructureClassifier(generate_json=fake)
    window = make_window(
        blocks=[
            make_block("prev", text="前文", page=21),
            make_block("center", text="中心本文", page=22),
            make_block("next", text="後文", page=23),
        ],
        center_page=22,
    )

    result = classifier.classify(window)

    assert result.segments[0].block_ids == ["center"]
    sent = str(fake.calls[0]["contents"])
    assert "前文" in sent
    assert "中心本文" in sent
    assert "後文" in sent


def test_build_windows_adds_adjacent_context_and_unique_center_ownership() -> None:
    blocks = [
        make_block("p21", page=21),
        make_block("p22", page=22),
        make_block("p23", page=23),
    ]

    windows = build_structure_windows(blocks)

    assert [window.center_page for window in windows] == [21, 22, 23]
    assert [[block.block_id for block in window.context_blocks] for window in windows] == [
        ["p21", "p22"],
        ["p21", "p22", "p23"],
        ["p22", "p23"],
    ]
    center_ids = [
        block.block_id for window in windows for block in window.context_blocks if block.page == window.center_page
    ]
    assert center_ids == ["p21", "p22", "p23"]
