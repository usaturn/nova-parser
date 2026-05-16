"""nova_parser.structured の _build_agent / extract_structured に対する単体テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from nova_parser import gemini_backend, structured
from nova_parser.models import PageExtraction
from nova_parser.ocr import MODEL
from nova_parser.structured import STRUCTURED_PROMPT
from tests.conftest import FakePydanticAgent


@pytest.fixture
def fake_pydantic_ai(monkeypatch):
    """structured.py の Agent / GoogleModel / gemini_backend.get_provider をスタブ化。"""

    record: dict = {
        "google_model_calls": [],
        "agent_calls": [],
        "providers": [],
    }

    class _FakeGoogleModel:
        def __init__(self, model_name, *, provider=None):
            record["google_model_calls"].append({"model": model_name, "provider": provider})
            self.model_name = model_name
            self.provider = provider

    class _FakeAgent:
        def __init__(self, model, *, output_type=None, instructions=None):
            record["agent_calls"].append(
                {
                    "model": model,
                    "output_type": output_type,
                    "instructions": instructions,
                }
            )
            self.model = model
            self.output_type = output_type
            self.instructions = instructions

        def run_sync(self, contents):  # pragma: no cover - _build_agent 単体では呼ばれない
            raise AssertionError("FakeAgent.run_sync should be replaced for extract_structured tests")

    def fake_get_provider():
        provider = object()
        record["providers"].append(provider)
        return provider

    monkeypatch.setattr(structured, "GoogleModel", _FakeGoogleModel)
    monkeypatch.setattr(structured, "Agent", _FakeAgent)
    monkeypatch.setattr(gemini_backend, "get_provider", fake_get_provider)
    return record


def _empty_page_extraction(source: str = "") -> PageExtraction:
    return PageExtraction(
        source_file=source,
        organizations=[],
        skills=[],
        equipment=[],
        rules=[],
    )


# AC S-01
def test_build_agent_passes_provider_into_google_model(fake_pydantic_ai):
    structured._build_agent()

    assert len(fake_pydantic_ai["google_model_calls"]) == 1
    assert len(fake_pydantic_ai["providers"]) == 1
    assert fake_pydantic_ai["google_model_calls"][0]["provider"] is fake_pydantic_ai["providers"][0]


# AC S-02
def test_build_agent_uses_ocr_module_model_constant(fake_pydantic_ai):
    structured._build_agent()

    assert fake_pydantic_ai["google_model_calls"][0]["model"] == MODEL


# AC S-03
def test_build_agent_constructs_agent_with_page_extraction_and_prompt(fake_pydantic_ai):
    agent = structured._build_agent()

    assert len(fake_pydantic_ai["agent_calls"]) == 1
    call = fake_pydantic_ai["agent_calls"][0]
    assert call["output_type"] is PageExtraction
    assert call["instructions"] == STRUCTURED_PROMPT
    # Agent に渡された model は GoogleModel インスタンス
    assert call["model"] is agent.model


# AC S-04
def test_build_agent_calls_get_provider_each_invocation(fake_pydantic_ai):
    structured._build_agent()
    structured._build_agent()

    assert len(fake_pydantic_ai["providers"]) == 2
    # 2 回目に渡された provider は 1 回目と別オブジェクト
    assert fake_pydantic_ai["providers"][0] is not fake_pydantic_ai["providers"][1]
    assert len(fake_pydantic_ai["google_model_calls"]) == 2
    assert fake_pydantic_ai["google_model_calls"][0]["provider"] is fake_pydantic_ai["providers"][0]
    assert fake_pydantic_ai["google_model_calls"][1]["provider"] is fake_pydantic_ai["providers"][1]


# AC S-05
def test_extract_structured_sets_source_file_on_output(monkeypatch, tmp_path: Path):
    image_path = tmp_path / "page-001.png"
    image_path.write_bytes(b"\x89PNG fake")

    fake_agent = FakePydanticAgent(responses=[_empty_page_extraction()])
    monkeypatch.setattr(structured, "_build_agent", lambda: fake_agent)
    monkeypatch.setattr(
        gemini_backend,
        "call_with_backend_fallback",
        lambda fn: fn(),
    )

    result = structured.extract_structured(image_path)

    assert isinstance(result, PageExtraction)
    assert result.source_file == "page-001.png"


# AC S-06
def test_extract_structured_passes_binary_content_to_run_sync(monkeypatch, tmp_path: Path):
    image_bytes = b"\x89PNG\r\n\x1a\nbinary-test"
    image_path = tmp_path / "page.png"
    image_path.write_bytes(image_bytes)

    fake_agent = FakePydanticAgent(responses=[_empty_page_extraction()])
    monkeypatch.setattr(structured, "_build_agent", lambda: fake_agent)
    monkeypatch.setattr(
        gemini_backend,
        "call_with_backend_fallback",
        lambda fn: fn(),
    )

    structured.extract_structured(image_path)

    assert len(fake_agent.calls) == 1
    contents = fake_agent.calls[0]["contents"]
    assert contents[0] == "この画像からゲームデータを構造化抽出してください。"
    binary = contents[1]
    assert isinstance(binary, structured.BinaryContent)
    assert binary.media_type == "image/png"
    assert binary.data == image_bytes


# AC S-07
@pytest.mark.parametrize(
    ("suffix", "expected_mime"),
    [
        (".png", "image/png"),
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".webp", "image/webp"),
    ],
)
def test_extract_structured_resolves_mime_from_suffix(monkeypatch, tmp_path: Path, suffix: str, expected_mime: str):
    image_path = tmp_path / f"page{suffix}"
    image_path.write_bytes(b"fake-bytes")

    fake_agent = FakePydanticAgent(responses=[_empty_page_extraction()])
    monkeypatch.setattr(structured, "_build_agent", lambda: fake_agent)
    monkeypatch.setattr(
        gemini_backend,
        "call_with_backend_fallback",
        lambda fn: fn(),
    )

    structured.extract_structured(image_path)

    binary = fake_agent.calls[0]["contents"][1]
    assert binary.media_type == expected_mime


# AC S-08
def test_extract_structured_returns_call_with_backend_fallback_output(monkeypatch, tmp_path: Path):
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake")

    expected_output = _empty_page_extraction(source="placeholder")
    fake_agent = FakePydanticAgent(responses=[expected_output])
    monkeypatch.setattr(structured, "_build_agent", lambda: fake_agent)

    sentinel_calls: list = []

    def fake_call(fn):
        sentinel_calls.append("called")
        return fn()

    monkeypatch.setattr(gemini_backend, "call_with_backend_fallback", fake_call)

    result = structured.extract_structured(image_path)

    assert sentinel_calls == ["called"]
    assert result is expected_output
    # source_file は extract_structured によって画像名で上書きされる
    assert result.source_file == "page.png"
