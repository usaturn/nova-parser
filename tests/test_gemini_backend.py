"""gemini_backend モジュールの単体テスト。"""

from __future__ import annotations

import pytest
from google.genai.errors import ClientError
from pydantic_ai.exceptions import ModelHTTPError

import nova_parser.gemini_backend as backend_mod
from nova_parser.gemini_backend import (
    Backend,
    BackendUnavailableError,
    call_with_backend_fallback,
    current_backend,
    force_vertex,
    is_rate_limit_error,
)


@pytest.fixture(autouse=True)
def _reset_backend(monkeypatch):
    """各テストの前後で gemini_backend のモジュール状態をリセットする。"""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("VERTEX_AI_API_KEY", raising=False)
    backend_mod.reset_for_tests()
    yield
    backend_mod.reset_for_tests()


def _rate_limit_client_error() -> ClientError:
    return ClientError(429, "rate limit")


def _rate_limit_model_http_error() -> ModelHTTPError:
    return ModelHTTPError(status_code=429, model_name="gemini", body=None)


def test_initial_backend_prefers_ai_studio_when_gemini_key_set(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "ai-studio-key")
    monkeypatch.setenv("VERTEX_AI_API_KEY", "vertex-key")
    assert current_backend() == Backend.AI_STUDIO


def test_initial_backend_falls_back_to_vertex_when_only_vertex_set(monkeypatch):
    monkeypatch.setenv("VERTEX_AI_API_KEY", "vertex-key")
    assert current_backend() == Backend.VERTEX


def test_initial_backend_raises_when_no_keys_set():
    with pytest.raises(BackendUnavailableError):
        current_backend()


def test_force_vertex_is_sticky_and_invalidates_clients(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "ai-studio-key")
    monkeypatch.setenv("VERTEX_AI_API_KEY", "vertex-key")
    build_calls: list[Backend] = []

    def fake_build_client(b: Backend):
        build_calls.append(b)
        return object()

    monkeypatch.setattr(backend_mod, "_build_client", fake_build_client)

    first = backend_mod.get_client()
    assert build_calls == [Backend.AI_STUDIO]

    assert force_vertex(reason="test") is True
    assert current_backend() == Backend.VERTEX

    second = backend_mod.get_client()
    assert build_calls == [Backend.AI_STUDIO, Backend.VERTEX]
    assert first is not second

    # 2 度目の force_vertex は no-op で再ビルドしない。
    assert force_vertex(reason="test-again") is False
    third = backend_mod.get_client()
    assert third is second
    assert build_calls == [Backend.AI_STUDIO, Backend.VERTEX]


def test_force_vertex_raises_when_vertex_key_missing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "ai-studio-key")
    assert current_backend() == Backend.AI_STUDIO
    with pytest.raises(BackendUnavailableError):
        force_vertex(reason="test")


def test_call_with_backend_fallback_returns_directly_on_success(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "ai-studio-key")
    monkeypatch.setenv("VERTEX_AI_API_KEY", "vertex-key")
    calls = 0

    def fn() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    assert call_with_backend_fallback(fn) == "ok"
    assert calls == 1
    assert current_backend() == Backend.AI_STUDIO


def test_call_with_backend_fallback_switches_on_429_and_retries_once(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "ai-studio-key")
    monkeypatch.setenv("VERTEX_AI_API_KEY", "vertex-key")
    monkeypatch.setattr(backend_mod, "_build_client", lambda b: object())
    backends_seen: list[Backend] = []

    def fn() -> str:
        backends_seen.append(current_backend())
        if current_backend() == Backend.AI_STUDIO:
            raise _rate_limit_client_error()
        return "vertex-ok"

    assert call_with_backend_fallback(fn) == "vertex-ok"
    assert backends_seen == [Backend.AI_STUDIO, Backend.VERTEX]
    assert current_backend() == Backend.VERTEX


def test_call_with_backend_fallback_propagates_429_when_already_on_vertex(monkeypatch):
    monkeypatch.setenv("VERTEX_AI_API_KEY", "vertex-key")
    monkeypatch.setattr(backend_mod, "_build_client", lambda b: object())

    def fn() -> str:
        raise _rate_limit_client_error()

    with pytest.raises(ClientError):
        call_with_backend_fallback(fn)
    assert current_backend() == Backend.VERTEX


def test_call_with_backend_fallback_propagates_non_rate_limit_errors(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "ai-studio-key")
    monkeypatch.setenv("VERTEX_AI_API_KEY", "vertex-key")
    monkeypatch.setattr(backend_mod, "_build_client", lambda b: object())

    def fn() -> str:
        raise ValueError("not a rate limit")

    with pytest.raises(ValueError):
        call_with_backend_fallback(fn)
    assert current_backend() == Backend.AI_STUDIO


def test_call_with_backend_fallback_preserves_429_when_vertex_unavailable(monkeypatch):
    """Vertex キー未設定時は 429 を握り潰さず、元例外を外側に伝播する。"""
    monkeypatch.setenv("GEMINI_API_KEY", "ai-studio-key")
    monkeypatch.delenv("VERTEX_AI_API_KEY", raising=False)
    calls = 0

    def fn() -> str:
        nonlocal calls
        calls += 1
        raise _rate_limit_client_error()

    with pytest.raises(ClientError) as excinfo:
        call_with_backend_fallback(fn)

    assert excinfo.value.code == 429
    assert not isinstance(excinfo.value, BackendUnavailableError)
    assert calls == 1
    assert current_backend() == Backend.AI_STUDIO


def test_get_provider_is_sticky_after_force_vertex(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "ai-studio-key")
    monkeypatch.setenv("VERTEX_AI_API_KEY", "vertex-key")
    build_calls: list[Backend] = []

    def fake_build_provider(b: Backend):
        build_calls.append(b)
        return object()

    monkeypatch.setattr(backend_mod, "_build_provider", fake_build_provider)

    first = backend_mod.get_provider()
    assert build_calls == [Backend.AI_STUDIO]

    assert force_vertex(reason="test") is True

    second = backend_mod.get_provider()
    assert build_calls == [Backend.AI_STUDIO, Backend.VERTEX]
    assert first is not second


def test_is_rate_limit_error_detects_genai_client_error_429():
    assert is_rate_limit_error(_rate_limit_client_error()) is True


def test_is_rate_limit_error_detects_pydantic_ai_429():
    assert is_rate_limit_error(_rate_limit_model_http_error()) is True


def test_is_rate_limit_error_returns_false_for_other_errors():
    assert is_rate_limit_error(ValueError("nope")) is False
    assert is_rate_limit_error(RuntimeError("boom")) is False
