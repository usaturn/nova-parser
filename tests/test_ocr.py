"""nova_parser.ocr モジュールのユニットテスト。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import nova_parser.gemini_backend as gemini_backend_mod
import nova_parser.ocr as ocr_mod
import nova_parser.perf as perf_mod
from nova_parser.ocr import (
    GeminiJSONError,
    JSONFailureArtifact,
    _atomic_write_text,
    _coerce_json_result,
    generate_json,
    get_client,
    ocr_image,
)

# Fake クラスは tests/conftest.py から共有
from tests.conftest import FakeGeminiClient, FakeGeminiResponse


@pytest.fixture(autouse=True)
def _reset_perf_tracker():
    """ocr.ocr_image が tracker.timer を呼ぶため、各テスト前後でグローバル状態をリセット。"""
    perf_mod.tracker.reset()
    yield
    perf_mod.tracker.reset()


# ---------------------------------------------------------------------------
# get_client
# ---------------------------------------------------------------------------


def test_get_client_delegates_to_gemini_backend(monkeypatch, reset_gemini_backend):
    sentinel = object()
    monkeypatch.setattr(gemini_backend_mod, "get_client", lambda: sentinel)

    assert get_client() is sentinel


# ---------------------------------------------------------------------------
# _atomic_write_text
# ---------------------------------------------------------------------------


def test_atomic_write_text_creates_parent_dir_and_writes(tmp_path: Path):
    target = tmp_path / "missing_dir" / "out.json"

    _atomic_write_text(target, "hello")

    assert target.read_text(encoding="utf-8") == "hello"


def test_atomic_write_text_overwrites_existing_file(tmp_path: Path):
    target = tmp_path / "out.txt"
    target.write_text("old", encoding="utf-8")

    _atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".out.txt.")]
    assert leftovers == []


def test_atomic_write_text_cleans_up_tmp_on_failure(monkeypatch, tmp_path: Path):
    target = tmp_path / "out.json"

    original_replace = Path.replace

    def fail_replace(self: Path, target_path: Any) -> Path:
        if self.name.startswith(".out.json."):
            raise OSError("simulated replace failure")
        return original_replace(self, target_path)

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        _atomic_write_text(target, "data")

    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".out.json.")]
    assert leftovers == []


# ---------------------------------------------------------------------------
# _coerce_json_result
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [{"a": 1}, [1, 2, 3], {}, []])
def test_coerce_json_result_passes_through_dict_and_list(value):
    assert _coerce_json_result(value) is value


def test_coerce_json_result_uses_pydantic_model_dump():
    class FakePydantic:
        def model_dump(self, *, mode: str) -> dict:
            assert mode == "json"
            return {"k": "v"}

    assert _coerce_json_result(FakePydantic()) == {"k": "v"}


@pytest.mark.parametrize("value", [42, "string", object()])
def test_coerce_json_result_raises_for_unsupported_type(value):
    with pytest.raises(ValueError, match="想定外"):
        _coerce_json_result(value)


# ---------------------------------------------------------------------------
# generate_json
# ---------------------------------------------------------------------------


def _install_fake_gemini(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[FakeGeminiResponse | BaseException],
) -> FakeGeminiClient:
    """ocr.get_client を FakeGeminiClient に差し替え、そのインスタンスを返す。

    `call_with_backend_fallback` も透過版で差し替えることで、`generate_json`
    の内部実装が将来モジュール参照ではなくローカルキャプチャ等に変わっても
    モック境界が崩れないようにする。
    """

    client = FakeGeminiClient(responses)
    monkeypatch.setattr(ocr_mod, "get_client", lambda: client)
    monkeypatch.setattr(ocr_mod.gemini_backend, "call_with_backend_fallback", lambda fn: fn())
    return client


def test_generate_json_returns_parsed_when_response_parsed_present(monkeypatch, reset_gemini_backend):
    payload = {"types": []}
    _install_fake_gemini(monkeypatch, [FakeGeminiResponse(text="{}", parsed=payload)])

    result = generate_json(["prompt"])

    assert result == payload


def test_generate_json_falls_back_to_text_json_when_parsed_none(monkeypatch, reset_gemini_backend):
    _install_fake_gemini(monkeypatch, [FakeGeminiResponse(text='{"k": 1}', parsed=None)])

    result = generate_json(["prompt"])

    assert result == {"k": 1}


def test_generate_json_retries_once_on_decode_error_then_succeeds(monkeypatch, reset_gemini_backend):
    sleep_calls: list[float] = []
    monkeypatch.setattr(ocr_mod.time, "sleep", lambda s: sleep_calls.append(s))
    client = _install_fake_gemini(
        monkeypatch,
        [
            FakeGeminiResponse(text="not json", parsed=None),
            FakeGeminiResponse(text='{"ok": true}', parsed=None),
        ],
    )

    result = generate_json(["prompt"])

    assert result == {"ok": True}
    assert len(client.calls) == 2
    assert sleep_calls == [ocr_mod.JSON_DECODE_RETRY_WAIT_SECONDS]


def test_generate_json_writes_failure_artifact_on_repeated_decode_error(
    monkeypatch, reset_gemini_backend, tmp_path: Path
):
    monkeypatch.setattr(ocr_mod.time, "sleep", lambda s: None)
    _install_fake_gemini(
        monkeypatch,
        [
            FakeGeminiResponse(text="garbage-1", parsed=None),
            FakeGeminiResponse(text="garbage-2", parsed=None),
        ],
    )

    artifact_path = tmp_path / "fail.json"
    artifact = JSONFailureArtifact(
        output_path=artifact_path,
        mode="docai",
        source_path=Path("/img/foo.png"),
        prompt="my-prompt",
        ocr_text="ocr-text",
    )

    with pytest.raises(GeminiJSONError) as excinfo:
        generate_json(["prompt"], failure_artifact=artifact)

    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "docai"
    assert payload["source_path"] == str(Path("/img/foo.png"))
    assert payload["model"] == ocr_mod.FLASH_MODEL
    assert payload["error_type"] == "JSONDecodeError"
    assert payload["error_message"]
    assert payload["response_text"] == "garbage-2"
    assert payload["prompt"] == "my-prompt"
    assert payload["ocr_text"] == "ocr-text"
    assert str(artifact_path) in str(excinfo.value)


def test_generate_json_validator_failure_writes_artifact_and_raises(monkeypatch, reset_gemini_backend, tmp_path: Path):
    _install_fake_gemini(
        monkeypatch,
        [FakeGeminiResponse(text='{"ok": true}', parsed={"ok": True})],
    )

    artifact_path = tmp_path / "validator-fail.json"
    artifact = JSONFailureArtifact(
        output_path=artifact_path,
        mode="extract",
        source_path=Path("/img/bar.png"),
        prompt="p",
    )

    def validator(_value: dict | list) -> None:
        msg = "schema mismatch"
        raise ValueError(msg)

    with pytest.raises(GeminiJSONError, match="schema mismatch"):
        generate_json(["prompt"], result_validator=validator, failure_artifact=artifact)

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["error_type"] == "ValueError"
    assert payload["mode"] == "extract"
    assert payload["ocr_text"] is None


def test_generate_json_validator_failure_without_artifact_skips_write(monkeypatch, reset_gemini_backend):
    _install_fake_gemini(
        monkeypatch,
        [FakeGeminiResponse(text='{"ok": true}', parsed={"ok": True})],
    )

    def validator(_value: dict | list) -> None:
        msg = "boom"
        raise ValueError(msg)

    with pytest.raises(GeminiJSONError) as excinfo:
        generate_json(["prompt"], result_validator=validator)

    assert "(詳細:" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# ocr_image
# ---------------------------------------------------------------------------


def test_ocr_image_calls_gemini_with_correct_mime_and_returns_text(monkeypatch, reset_gemini_backend, tmp_path: Path):
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    client = _install_fake_gemini(monkeypatch, [FakeGeminiResponse(text="抽出テキスト")])

    result = ocr_image(image_path)

    assert result == "抽出テキスト"
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["model"] == ocr_mod.MODEL
    contents = call["contents"]
    assert contents[0] == ocr_mod.OCR_PROMPT
    # contents[1] は types.Part.from_bytes が返すオブジェクト。MIME と内容を間接的に確認する
    part = contents[1]
    inline = getattr(part, "inline_data", None)
    assert inline is not None
    assert inline.mime_type == "image/png"
