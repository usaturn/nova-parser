"""pytest 共通フィクスチャ・スタブ定義。

FakeVisionClient と _FakeResponse は test_regional_ocr_client.py と
test_regional_routes.py の両方から共有される（AC-C-26）。
FakeGeminiClient / FakeDocAIClient は test_ocr.py / test_documentai.py で
ocr.py と documentai.py の外部 API 呼び出しを差し替えるために使う。
FakePydanticAgent と replace_generate_json は test_structured.py /
test_gamedata.py で外部 SDK 呼び出しを差し替えるために使う。
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

import nova_parser.gemini_backend as _gemini_backend


class _FakeResponse:
    """Vision API レスポンスのスタブ。

    blocks は document_text_detection のブロック検出結果を表し、
    1 ブロックあたり頂点 (x, y) タプルのリストで指定する。
    """

    def __init__(
        self,
        *,
        text: str = "",
        error_message: str = "",
        blocks: "list[list[tuple[int, int]]] | None" = None,
    ) -> None:
        self.full_text_annotation = SimpleNamespace(text=text, pages=_make_pages(blocks or []))
        self.error = SimpleNamespace(message=error_message)


def _make_pages(blocks: "list[list[tuple[int, int]]]") -> list[SimpleNamespace]:
    """頂点リスト群から full_text_annotation.pages 相当の構造を組み立てる。"""
    if not blocks:
        return []
    page_blocks = [
        SimpleNamespace(
            bounding_box=SimpleNamespace(vertices=[SimpleNamespace(x=x, y=y) for x, y in vertices]),
        )
        for vertices in blocks
    ]
    return [SimpleNamespace(blocks=page_blocks)]


class FakeVisionClient:
    """Vision API クライアントのフェイク。複数レスポンスをキューとして保持する。

    既存コード（test_regional_ocr_client.py）との互換性のため、
    単一 _FakeResponse / list[_FakeResponse] / None の 3 形式を受け付ける。
    """

    def __init__(self, response_or_responses: "_FakeResponse | list[_FakeResponse] | None" = None) -> None:
        if response_or_responses is None:
            self._responses = [_FakeResponse(text="")]
        elif isinstance(response_or_responses, list):
            self._responses = list(response_or_responses) if response_or_responses else [_FakeResponse(text="")]
        else:
            # 単一 _FakeResponse（既存テストとの互換）
            self._responses = [response_or_responses]
        self.calls: list[dict[str, Any]] = []
        self.document_calls: list[dict[str, Any]] = []

    def text_detection(self, *, image: Any, image_context: Any) -> _FakeResponse:
        """text_detection 呼び出しを記録し、キューから応答を返す。"""
        self.calls.append({"image": image, "image_context": image_context})
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]

    def document_text_detection(self, *, image: Any, image_context: Any) -> _FakeResponse:
        """document_text_detection 呼び出しを記録し、text_detection と同じキューから応答を返す。"""
        self.document_calls.append({"image": image, "image_context": image_context})
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


def make_fake_factory(client: FakeVisionClient) -> Callable[[], FakeVisionClient]:
    """vision_client_factory として渡せる callable を返す。呼び出し回数を `calls` で記録する。"""

    state = {"calls": 0}

    def _factory() -> FakeVisionClient:
        state["calls"] += 1
        return client

    _factory.calls = state  # type: ignore[attr-defined]
    return _factory


class FakeGeminiResponse:
    """Gemini SDK の generate_content レスポンスのフェイク。"""

    def __init__(self, *, text: str = "", parsed: Any | None = None) -> None:
        self.text = text
        self.parsed = parsed


class _FakeGeminiModels:
    def __init__(self, owner: "FakeGeminiClient") -> None:
        self._owner = owner

    def generate_content(self, *, model: str, contents: Any, config: Any = None) -> FakeGeminiResponse:
        self._owner.calls.append({"model": model, "contents": contents, "config": config})
        if not self._owner._responses:
            raise RuntimeError("FakeGeminiClient: 応答キューが空です")
        next_item = self._owner._responses.pop(0)
        if isinstance(next_item, BaseException):
            raise next_item
        return next_item


class FakeGeminiClient:
    """Gemini SDK クライアントのフェイク。応答 / 例外をキュー順に返す。"""

    def __init__(self, responses: list[FakeGeminiResponse | BaseException] | None = None) -> None:
        self._responses: list[FakeGeminiResponse | BaseException] = list(responses) if responses else []
        self.calls: list[dict[str, Any]] = []
        self.models = _FakeGeminiModels(self)


class FakeDocAIDocument:
    """Document AI Document のフェイク。`.text` 属性のみを持つ。"""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeDocAIResult:
    def __init__(self, document: FakeDocAIDocument) -> None:
        self.document = document


class FakeDocAIClient:
    """Document AI クライアントのフェイク。process_document をキューで返す。"""

    def __init__(self, documents: list[FakeDocAIDocument | BaseException] | None = None) -> None:
        self._documents: list[FakeDocAIDocument | BaseException] = list(documents) if documents else []
        self.calls: list[dict[str, Any]] = []

    def process_document(self, *, request: Any) -> _FakeDocAIResult:
        self.calls.append({"request": request})
        if not self._documents:
            raise RuntimeError("FakeDocAIClient: ドキュメントキューが空です")
        next_item = self._documents.pop(0)
        if isinstance(next_item, BaseException):
            raise next_item
        return _FakeDocAIResult(next_item)


class FakePydanticAgentResult:
    """pydantic_ai Agent.run_sync の戻り値スタブ。`.output` 属性のみ持つ。"""

    def __init__(self, output: Any) -> None:
        self.output = output


class FakePydanticAgent:
    """pydantic_ai Agent のフェイク。run_sync 応答 / 例外をキュー順に返す。"""

    def __init__(self, responses: list[Any] | None = None) -> None:
        self._responses: list[Any] = list(responses) if responses else []
        self.calls: list[dict[str, Any]] = []

    def run_sync(self, contents: Any) -> FakePydanticAgentResult:
        self.calls.append({"contents": contents})
        if not self._responses:
            raise RuntimeError("FakePydanticAgent: 応答キューが空です")
        next_item = self._responses.pop(0)
        if isinstance(next_item, BaseException):
            raise next_item
        return FakePydanticAgentResult(output=next_item)


def replace_generate_json(
    monkeypatch: pytest.MonkeyPatch,
    results: list[Any],
) -> list[dict[str, Any]]:
    """nova_parser.gamedata.generate_json を結果キューに差し替えるヘルパー。

    戻り値: 呼び出し履歴を蓄積する list。各要素は generate_json に渡された
    引数の dict（contents / response_json_schema / result_validator / failure_artifact）。
    キュー要素が BaseException の場合は raise する。
    """
    queue: list[Any] = list(results)
    calls: list[dict[str, Any]] = []

    def fake_generate_json(
        contents: Any,
        *,
        response_json_schema: Any = None,
        result_validator: Any = None,
        failure_artifact: Any = None,
        **kwargs: Any,
    ) -> Any:
        calls.append(
            {
                "contents": contents,
                "response_json_schema": response_json_schema,
                "result_validator": result_validator,
                "failure_artifact": failure_artifact,
                "extra": kwargs,
            }
        )
        if not queue:
            raise RuntimeError("replace_generate_json: 応答キューが空です")
        next_item = queue.pop(0)
        if isinstance(next_item, BaseException):
            raise next_item
        return next_item

    monkeypatch.setattr("nova_parser.gamedata.generate_json", fake_generate_json)
    return calls


@pytest.fixture
def reset_gemini_backend(monkeypatch):
    """gemini_backend モジュールの状態を初期化し、AI Studio キーのみセットする。

    test_ocr.py / test_documentai.py 用。`call_with_backend_fallback` が
    バックエンド判定で env を読むため、テスト毎に既知の状態に揃える。
    """

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("VERTEX_AI_API_KEY", raising=False)
    _gemini_backend.reset_for_tests()
    yield
    _gemini_backend.reset_for_tests()
