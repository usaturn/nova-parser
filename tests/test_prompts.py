"""prompts モジュールの定数テスト。"""

from __future__ import annotations

import json
import re
import string

import pytest

from nova_parser.prompts import (
    CARD_DETECT_PROMPT,
    DOCAI_EXTRACT_PROMPT,
    GAMEDATA_PROMPT,
    SCHEMA_DISCOVER_PROMPT,
    SCHEMA_EXTRACT_PROMPT,
)

# ---------------------------------------------------------------------------
# 同一性: 全プロンプトが str かつ非空
# ---------------------------------------------------------------------------

ALL_PROMPTS: dict[str, str] = {
    "CARD_DETECT_PROMPT": CARD_DETECT_PROMPT,
    "DOCAI_EXTRACT_PROMPT": DOCAI_EXTRACT_PROMPT,
    "SCHEMA_EXTRACT_PROMPT": SCHEMA_EXTRACT_PROMPT,
    "GAMEDATA_PROMPT": GAMEDATA_PROMPT,
    "SCHEMA_DISCOVER_PROMPT": SCHEMA_DISCOVER_PROMPT,
}


@pytest.mark.parametrize(
    "prompt",
    list(ALL_PROMPTS.values()),
    ids=list(ALL_PROMPTS.keys()),
)
def test_prompt_constants_are_non_empty_strings(prompt: str) -> None:
    """全プロンプト定数が str かつ空白のみでない。"""
    assert isinstance(prompt, str)
    assert prompt.strip()


# ---------------------------------------------------------------------------
# SCHEMA_EXTRACT_PROMPT の .format 整合性
# ---------------------------------------------------------------------------


def test_schema_extract_prompt_formats_with_required_placeholders() -> None:
    """SCHEMA_EXTRACT_PROMPT.format で schema_section と ocr_text が結果に展開される。"""
    result = SCHEMA_EXTRACT_PROMPT.format(
        schema_section="SCHEMA_SECTION_TOKEN",
        ocr_text="OCR_TEXT_TOKEN",
    )
    assert "SCHEMA_SECTION_TOKEN" in result
    assert "OCR_TEXT_TOKEN" in result


def test_schema_extract_prompt_placeholder_set_is_known() -> None:
    """SCHEMA_EXTRACT_PROMPT の named placeholder が想定通り {schema_section, ocr_text}。"""
    names = {field_name for _, field_name, _, _ in string.Formatter().parse(SCHEMA_EXTRACT_PROMPT) if field_name}
    assert names == {"schema_section", "ocr_text"}


def test_schema_extract_prompt_escaped_braces_survive_format() -> None:
    """SCHEMA_EXTRACT_PROMPT を format した後、JSON 例の `{"matched_types": ...}` がリテラルとして残る。"""
    result = SCHEMA_EXTRACT_PROMPT.format(schema_section="", ocr_text="")
    assert '{"matched_types"' in result
    assert '"unmatched_types"' in result


# ---------------------------------------------------------------------------
# 各プロンプトの JSON 例にスキーマ・キーが含まれていること
# （LLM 応答スキーマの契約部分。誤って削除されたら検出する）
# ---------------------------------------------------------------------------

PROMPT_REQUIRED_KEYS: dict[str, list[str]] = {
    "CARD_DETECT_PROMPT": ['"cards"', '"left"', '"top"', '"right"', '"bottom"', '"label"'],
    "DOCAI_EXTRACT_PROMPT": ['"types"', '"type_name"', '"items"'],
    "GAMEDATA_PROMPT": ['"types"', '"type_name"', '"items"'],
    "SCHEMA_DISCOVER_PROMPT": ['"types"', '"type_name"', '"fields"'],
    "SCHEMA_EXTRACT_PROMPT": ['"matched_types"', '"unmatched_types"', '"type_name"', '"items"'],
}


@pytest.mark.parametrize(
    ("prompt", "required_keys"),
    [(ALL_PROMPTS[name], keys) for name, keys in PROMPT_REQUIRED_KEYS.items()],
    ids=list(PROMPT_REQUIRED_KEYS.keys()),
)
def test_prompt_contains_required_json_keys(prompt: str, required_keys: list[str]) -> None:
    """各プロンプトの JSON 例に LLM 応答スキーマで使うキーが含まれている。"""
    for key in required_keys:
        assert key in prompt, f"必須キー {key} がプロンプトに見つからない"


# ---------------------------------------------------------------------------
# JSON 例の parse 可能性（`...` を含まない CARD_DETECT / SCHEMA_DISCOVER のみ対象）
# ---------------------------------------------------------------------------


def _extract_first_json_blob(text: str) -> str:
    """テキスト中の最初の `{` から最後の `}` までを greedy に抽出する。"""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    assert match is not None, "JSON 例が見つからない"
    return match.group(0)


def test_card_detect_prompt_json_example_is_parseable_json() -> None:
    """CARD_DETECT_PROMPT 内の JSON 例が json.loads で parse 可能で、cards キーを持つ。"""
    blob = _extract_first_json_blob(CARD_DETECT_PROMPT)
    parsed = json.loads(blob)
    assert "cards" in parsed
    assert isinstance(parsed["cards"], list)


def test_schema_discover_prompt_json_example_is_parseable_json() -> None:
    """SCHEMA_DISCOVER_PROMPT 内の JSON 例が json.loads で parse 可能で、types キーを持つ。"""
    blob = _extract_first_json_blob(SCHEMA_DISCOVER_PROMPT)
    parsed = json.loads(blob)
    assert "types" in parsed
    assert isinstance(parsed["types"], list)
