"""Gemini JSON ガードレールのテスト。"""

from __future__ import annotations

import json

import pytest

import nova_parser.documentai as documentai_mod
import nova_parser.gamedata as gamedata_mod
import nova_parser.ocr as ocr_mod


class _FakeResponse:
    def __init__(self, *, text: str, parsed=None):
        self.text = text
        self.parsed = parsed


class _FakeModels:
    def __init__(self, responses: _FakeResponse | list[_FakeResponse]):
        if isinstance(responses, list):
            self._responses = list(responses)
        else:
            self._responses = [responses]
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses[min(len(self.calls), len(self._responses)) - 1]


class _FakeClient:
    def __init__(self, responses: _FakeResponse | list[_FakeResponse]):
        self.models = _FakeModels(responses)


def test_generate_json_uses_parsed_result_and_passes_response_schema(monkeypatch):
    response = _FakeResponse(text="{invalid json", parsed={"types": []})
    client = _FakeClient(response)
    validated: list[dict | list] = []

    monkeypatch.setattr(ocr_mod, "get_client", lambda: client)

    result = ocr_mod.generate_json(
        ["prompt"],
        response_json_schema={"type": "object"},
        result_validator=lambda result: validated.append(result),
    )

    assert result == {"types": []}
    assert validated == [{"types": []}]
    assert client.models.calls[0]["config"].response_json_schema == {"type": "object"}


def test_generate_json_retries_json_decode_error_and_returns_second_result(monkeypatch, tmp_path, capsys):
    client = _FakeClient(
        [
            _FakeResponse(text='{"broken": }', parsed=None),
            _FakeResponse(text='{"types": []}', parsed=None),
        ]
    )
    artifact_path = tmp_path / "alpha.extract.gemini_json_error.json"
    sleep_calls: list[float] = []
    validated: list[dict | list] = []

    monkeypatch.setattr(ocr_mod, "get_client", lambda: client)
    monkeypatch.setattr(ocr_mod.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    result = ocr_mod.generate_json(
        ["prompt"],
        response_json_schema={"type": "object"},
        result_validator=lambda result: validated.append(result),
        failure_artifact=ocr_mod.JSONFailureArtifact(
            output_path=artifact_path,
            mode="extract",
            source_path=tmp_path / "alpha.png",
            prompt="prompt",
            ocr_text="ocr body",
        ),
    )

    captured = capsys.readouterr().out
    assert result == {"types": []}
    assert validated == [{"types": []}]
    assert len(client.models.calls) == 2
    assert sleep_calls == [1.0]
    assert "alpha.png: JSONDecodeError のため 1.0秒後に再試行 (1/2)" in captured
    assert not artifact_path.exists()


def test_generate_json_writes_failure_artifact_after_json_retry_exhausted(monkeypatch, tmp_path):
    client = _FakeClient(
        [
            _FakeResponse(text='{"broken": }', parsed=None),
            _FakeResponse(text='{"broken": }', parsed=None),
        ]
    )
    artifact_path = tmp_path / "alpha.extract.gemini_json_error.json"
    sleep_calls: list[float] = []

    monkeypatch.setattr(ocr_mod, "get_client", lambda: client)
    monkeypatch.setattr(ocr_mod.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    with pytest.raises(ocr_mod.GeminiJSONError, match=str(artifact_path)):
        ocr_mod.generate_json(
            ["prompt"],
            response_json_schema={"type": "object"},
            failure_artifact=ocr_mod.JSONFailureArtifact(
                output_path=artifact_path,
                mode="extract",
                source_path=tmp_path / "alpha.png",
                prompt="prompt",
                ocr_text="ocr body",
            ),
        )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert len(client.models.calls) == 2
    assert sleep_calls == [1.0]
    assert payload["mode"] == "extract"
    assert payload["error_type"] == "JSONDecodeError"
    assert payload["response_text"] == '{"broken": }'
    assert payload["prompt"] == "prompt"
    assert payload["ocr_text"] == "ocr body"


def test_generate_json_writes_failure_artifact_for_validator_error(monkeypatch, tmp_path):
    response = _FakeResponse(text='{"types": {}}', parsed={"types": {}})
    client = _FakeClient(response)
    artifact_path = tmp_path / "alpha.docai.gemini_json_error.json"
    sleep_calls: list[float] = []

    monkeypatch.setattr(ocr_mod, "get_client", lambda: client)
    monkeypatch.setattr(ocr_mod.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    with pytest.raises(ocr_mod.GeminiJSONError, match="shape mismatch"):
        ocr_mod.generate_json(
            ["prompt"],
            response_json_schema={"type": "object"},
            result_validator=lambda result: (_ for _ in ()).throw(ValueError("shape mismatch")),
            failure_artifact=ocr_mod.JSONFailureArtifact(
                output_path=artifact_path,
                mode="docai",
                source_path=tmp_path / "alpha.png",
                prompt="prompt",
            ),
        )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert len(client.models.calls) == 1
    assert sleep_calls == []
    assert payload["mode"] == "docai"
    assert payload["error_type"] == "ValueError"
    assert payload["error_message"] == "shape mismatch"
    assert payload["ocr_text"] is None


def test_extract_with_schema_passes_extract_schema_and_failure_artifact(monkeypatch, tmp_path):
    image_path = tmp_path / "alpha.png"
    image_path.write_bytes(b"dummy")
    schema = {"types": [{"type_name": "Card", "fields": ["name", "power"]}]}
    captured: dict[str, object] = {}

    monkeypatch.setattr(documentai_mod, "ocr_with_documentai", lambda image_path, show_progress=True: "OCR BODY")

    def fake_generate_json(contents, **kwargs):
        captured["contents"] = contents
        captured["kwargs"] = kwargs
        return {"matched_types": [], "unmatched_types": []}

    monkeypatch.setattr(documentai_mod, "generate_json", fake_generate_json)

    result = documentai_mod.extract_with_schema(image_path, schema, output_dir=tmp_path)

    kwargs = captured["kwargs"]
    assert result == {"matched_types": [], "unmatched_types": []}
    assert captured["contents"] == [kwargs["failure_artifact"].prompt]
    assert kwargs["response_json_schema"]["required"] == ["matched_types", "unmatched_types"]
    artifact = kwargs["failure_artifact"]
    assert artifact.output_path == tmp_path / "alpha.extract.gemini_json_error.json"
    assert artifact.mode == "extract"
    assert artifact.ocr_text == "OCR BODY"
    assert "OCR BODY" in artifact.prompt


def test_extract_docai_passes_generic_schema_and_failure_artifact(monkeypatch, tmp_path):
    image_path = tmp_path / "beta.png"
    image_path.write_bytes(b"dummy")
    captured: dict[str, object] = {}

    monkeypatch.setattr(documentai_mod, "ocr_with_documentai", lambda image_path, show_progress=True: "OCR TEXT")

    def fake_generate_json(contents, **kwargs):
        captured["contents"] = contents
        captured["kwargs"] = kwargs
        return {"types": []}

    monkeypatch.setattr(documentai_mod, "generate_json", fake_generate_json)

    result = documentai_mod.extract_docai(image_path, output_dir=tmp_path)

    kwargs = captured["kwargs"]
    assert result == {"types": [], "source_file": "beta.png"}
    assert kwargs["response_json_schema"]["required"] == ["types"]
    artifact = kwargs["failure_artifact"]
    assert artifact.output_path == tmp_path / "beta.docai.gemini_json_error.json"
    assert artifact.mode == "docai"
    assert artifact.ocr_text == "OCR TEXT"


def test_extract_gamedata_passes_generic_schema_and_failure_artifact(monkeypatch, tmp_path):
    image_path = tmp_path / "gamma.png"
    image_path.write_bytes(b"dummy")
    captured: dict[str, object] = {}

    def fake_generate_json(contents, **kwargs):
        captured["contents"] = contents
        captured["kwargs"] = kwargs
        return {"types": []}

    monkeypatch.setattr(gamedata_mod, "generate_json", fake_generate_json)

    result = gamedata_mod.extract_gamedata(image_path, output_dir=tmp_path)

    kwargs = captured["kwargs"]
    assert result == {"types": [], "source_file": "gamma.png"}
    assert captured["contents"][0] == gamedata_mod.GAMEDATA_PROMPT
    assert kwargs["response_json_schema"]["required"] == ["types"]
    artifact = kwargs["failure_artifact"]
    assert artifact.output_path == tmp_path / "gamma.gamedata.gemini_json_error.json"
    assert artifact.mode == "gamedata"
    assert artifact.ocr_text is None
