"""pytest 共通フィクスチャ・スタブ定義。

FakeVisionClient と _FakeResponse は test_regional_ocr_client.py と
test_regional_routes.py の両方から共有される（AC-C-26）。
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any


class _FakeResponse:
    """Vision API レスポンスのスタブ。"""

    def __init__(self, *, text: str = "", error_message: str = "") -> None:
        self.full_text_annotation = SimpleNamespace(text=text)
        self.error = SimpleNamespace(message=error_message)


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

    def text_detection(self, *, image: Any, image_context: Any) -> _FakeResponse:
        """text_detection 呼び出しを記録し、キューから応答を返す。"""
        self.calls.append({"image": image, "image_context": image_context})
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
