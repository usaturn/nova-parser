"""nova_parser.gamedata の extract_schema / extract_gamedata に対する単体テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from nova_parser import gamedata
from nova_parser.json_contracts import (
    build_gamedata_result_schema,
    validate_gamedata_result,
)
from nova_parser.ocr import JSONFailureArtifact
from nova_parser.prompts import GAMEDATA_PROMPT, SCHEMA_DISCOVER_PROMPT
from tests.conftest import replace_generate_json


@pytest.fixture
def png_image(tmp_path: Path) -> Path:
    image_path = tmp_path / "page-001.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return image_path


@pytest.fixture
def jpg_image(tmp_path: Path) -> Path:
    image_path = tmp_path / "page-002.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\xe0fake")
    return image_path


@pytest.fixture
def pdf_image(tmp_path: Path) -> Path:
    image_path = tmp_path / "page-003.pdf"
    image_path.write_bytes(b"%PDF-1.4 fake")
    return image_path


# AC G-01
def test_extract_schema_returns_dict_as_is(monkeypatch, png_image: Path):
    expected = {"types": [{"type_name": "白兵武器", "fields": ["名称"]}]}
    replace_generate_json(monkeypatch, [expected])

    result = gamedata.extract_schema(png_image)

    assert result == expected


# AC G-02
def test_extract_schema_wraps_list_into_types(monkeypatch, png_image: Path):
    raw_list = [{"type_name": "白兵武器", "fields": ["名称"]}]
    replace_generate_json(monkeypatch, [raw_list])

    result = gamedata.extract_schema(png_image)

    assert result == {"types": raw_list}


# AC G-03
@pytest.mark.parametrize(
    ("image_fixture", "expected_mime"),
    [
        ("png_image", "image/png"),
        ("jpg_image", "image/jpeg"),
        ("pdf_image", "application/pdf"),
    ],
)
def test_extract_schema_passes_correct_mime_to_genai(monkeypatch, request, image_fixture: str, expected_mime: str):
    image_path: Path = request.getfixturevalue(image_fixture)
    calls = replace_generate_json(monkeypatch, [{"types": []}])

    gamedata.extract_schema(image_path)

    assert len(calls) == 1
    contents = calls[0]["contents"]
    # contents は [prompt, Part]。Part は google.genai.types.Part で mime_type 属性を持つ。
    assert contents[0] == SCHEMA_DISCOVER_PROMPT
    inline_part = contents[1]
    # Part は .inline_data.mime_type または .file_data.mime_type を持つ。
    # Part.from_bytes は inline_data 経路。
    mime = getattr(getattr(inline_part, "inline_data", None), "mime_type", None)
    assert mime == expected_mime


# AC G-04
def test_extract_schema_passes_schema_discover_prompt(monkeypatch, png_image: Path):
    calls = replace_generate_json(monkeypatch, [{"types": []}])

    gamedata.extract_schema(png_image)

    assert calls[0]["contents"][0] == SCHEMA_DISCOVER_PROMPT


# AC G-05
def test_extract_gamedata_attaches_source_file_to_result(monkeypatch, png_image: Path):
    backend_result = {"types": [{"type_name": "白兵武器", "items": []}]}
    replace_generate_json(monkeypatch, [backend_result])

    result = gamedata.extract_gamedata(png_image, output_dir=Path("ignored"))

    assert result["source_file"] == png_image.name
    assert result["types"] == backend_result["types"]


# AC G-06
def test_extract_gamedata_raises_value_error_when_result_is_not_dict(monkeypatch, png_image: Path):
    replace_generate_json(monkeypatch, [["not", "a", "dict"]])

    with pytest.raises(ValueError, match="トップレベル"):
        gamedata.extract_gamedata(png_image, output_dir=Path("ignored"))


# AC G-07
def test_extract_gamedata_passes_schema_validator_and_failure_artifact(monkeypatch, tmp_path: Path, png_image: Path):
    output_dir = tmp_path / "out"
    calls = replace_generate_json(monkeypatch, [{"types": []}])

    gamedata.extract_gamedata(png_image, output_dir=output_dir)

    assert len(calls) == 1
    call = calls[0]
    assert call["response_json_schema"] == build_gamedata_result_schema()
    assert call["result_validator"] is validate_gamedata_result

    artifact = call["failure_artifact"]
    assert isinstance(artifact, JSONFailureArtifact)
    assert artifact.mode == "gamedata"
    assert artifact.source_path == png_image
    assert artifact.prompt == GAMEDATA_PROMPT


# AC G-08
def test_extract_gamedata_failure_artifact_output_path(monkeypatch, tmp_path: Path, png_image: Path):
    output_dir = tmp_path / "out"
    calls = replace_generate_json(monkeypatch, [{"types": []}])

    gamedata.extract_gamedata(png_image, output_dir=output_dir)

    artifact: JSONFailureArtifact = calls[0]["failure_artifact"]
    expected = output_dir / f"{png_image.stem}.gamedata.gemini_json_error.json"
    assert artifact.output_path == expected


# AC G-09
def test_extract_gamedata_defaults_output_dir_to_output(monkeypatch, png_image: Path):
    calls = replace_generate_json(monkeypatch, [{"types": []}])

    gamedata.extract_gamedata(png_image)

    artifact: JSONFailureArtifact = calls[0]["failure_artifact"]
    assert artifact.output_path == Path("Output") / f"{png_image.stem}.gamedata.gemini_json_error.json"


# AC G-10
def test_extract_gamedata_uses_gamedata_prompt(monkeypatch, png_image: Path):
    calls = replace_generate_json(monkeypatch, [{"types": []}])

    gamedata.extract_gamedata(png_image, output_dir=Path("ignored"))

    contents = calls[0]["contents"]
    assert contents[0] == GAMEDATA_PROMPT
