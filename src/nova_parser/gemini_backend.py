"""Gemini バックエンド（Google AI Studio / Vertex AI）の選択とフォールバック制御。

Google AI Studio の API キー（``GEMINI_API_KEY``）が設定されていればそちらを優先し、
レート制限（HTTP 429）を観測した時点で同一プロセス内 sticky に Vertex AI
（``VERTEX_AI_API_KEY``）へ切り替える。一度切り替わったら同プロセスでは
AI Studio へ戻らない。
"""

from __future__ import annotations

import os
import threading
from enum import Enum
from typing import Callable, TypeVar

from google import genai

T = TypeVar("T")

GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
VERTEX_API_KEY_ENV = "VERTEX_AI_API_KEY"


class Backend(str, Enum):
    """利用中の Gemini バックエンド。"""

    AI_STUDIO = "ai_studio"
    VERTEX = "vertex"


class BackendUnavailableError(RuntimeError):
    """利用可能なバックエンドが存在しない場合に送出される。"""


_lock = threading.Lock()
_active_backend: Backend | None = None
_genai_client: genai.Client | None = None
_provider: object | None = None  # pydantic_ai.providers.google.GoogleProvider


def _detect_initial_backend() -> Backend:
    """環境変数から初期バックエンドを決定する。"""
    if os.environ.get(GEMINI_API_KEY_ENV):
        return Backend.AI_STUDIO
    if os.environ.get(VERTEX_API_KEY_ENV):
        return Backend.VERTEX
    msg = (
        f"Gemini バックエンド用の API キーが設定されていません。"
        f"{GEMINI_API_KEY_ENV} または {VERTEX_API_KEY_ENV} を設定してください。"
    )
    raise BackendUnavailableError(msg)


def _current_backend_locked() -> Backend:
    """ロック保持中の前提で現在のバックエンドを返す。"""
    global _active_backend
    if _active_backend is None:
        _active_backend = _detect_initial_backend()
    return _active_backend


def current_backend() -> Backend:
    """現在のバックエンドを返す（未初期化なら初期化する）。"""
    with _lock:
        return _current_backend_locked()


def vertex_available() -> bool:
    """Vertex AI キーが環境に設定されているか。"""
    return bool(os.environ.get(VERTEX_API_KEY_ENV))


def reset_for_tests() -> None:
    """テスト用: モジュール状態を未初期化に戻す。"""
    global _active_backend, _genai_client, _provider
    with _lock:
        _active_backend = None
        _genai_client = None
        _provider = None


def force_vertex(reason: str) -> bool:
    """sticky に Vertex AI へ切り替える。既に Vertex なら何もしない。

    返り値は実際に切替が発生したかどうか。Vertex キーが未設定なら例外を送出する。
    """
    global _active_backend, _genai_client, _provider
    with _lock:
        if _current_backend_locked() == Backend.VERTEX:
            return False
        if not os.environ.get(VERTEX_API_KEY_ENV):
            msg = (
                f"AI Studio で 429 を検知したが {VERTEX_API_KEY_ENV} が未設定のため"
                f" Vertex AI にフォールバックできません: {reason}"
            )
            raise BackendUnavailableError(msg)
        _active_backend = Backend.VERTEX
        _genai_client = None
        _provider = None
        print(
            f"[gemini_backend] AI Studio から Vertex AI に切替: {reason}",
            flush=True,
        )
        return True


def _build_client(backend: Backend) -> genai.Client:
    if backend == Backend.AI_STUDIO:
        return genai.Client(
            vertexai=False,
            api_key=os.environ.get(GEMINI_API_KEY_ENV),
        )
    return genai.Client(
        vertexai=True,
        api_key=os.environ.get(VERTEX_API_KEY_ENV),
    )


def _build_provider(backend: Backend):
    from pydantic_ai.providers.google import GoogleProvider

    if backend == Backend.AI_STUDIO:
        return GoogleProvider(
            vertexai=False,
            api_key=os.environ.get(GEMINI_API_KEY_ENV),
        )
    return GoogleProvider(
        vertexai=True,
        api_key=os.environ.get(VERTEX_API_KEY_ENV),
    )


def get_client() -> genai.Client:
    """現在のバックエンドに対応する genai.Client を返す（キャッシュあり）。

    バックエンド読み取りとキャッシュ判定／構築を同一ロック内で行うため、
    並列実行中に :func:`force_vertex` が割り込んでも stale なキャッシュが
    残らない。
    """
    global _genai_client
    with _lock:
        backend = _current_backend_locked()
        if _genai_client is None:
            _genai_client = _build_client(backend)
        return _genai_client


def get_provider():
    """現在のバックエンドに対応する pydantic_ai GoogleProvider を返す（キャッシュあり）。"""
    global _provider
    with _lock:
        backend = _current_backend_locked()
        if _provider is None:
            _provider = _build_provider(backend)
        return _provider


def is_rate_limit_error(exc: BaseException) -> bool:
    """例外が 429 レート制限エラーかどうか判定する。"""
    from google.genai.errors import ClientError
    from pydantic_ai.exceptions import ModelHTTPError

    if isinstance(exc, ClientError) and getattr(exc, "code", None) == 429:
        return True
    if isinstance(exc, ModelHTTPError) and getattr(exc, "status_code", None) == 429:
        return True
    return False


def call_with_backend_fallback(fn: Callable[[], T]) -> T:
    """fn を実行し、AI Studio で 429 を観測した場合のみ Vertex で 1 度だけ再試行する。

    ``fn`` は呼び出される度に最新のバックエンド状態を参照すること。
    切替後の Vertex AI で再度 429 が出た場合はそのまま例外を伝播させ、外側の
    リトライ機構（``main._run_with_retries``）に委ねる。Vertex キーが
    未設定の場合はフォールバックを諦め、元の 429 例外をそのまま外側に伝える
    （:class:`BackendUnavailableError` には変換しない）。
    """
    try:
        return fn()
    except Exception as exc:
        if not is_rate_limit_error(exc):
            raise
        if current_backend() != Backend.AI_STUDIO:
            raise
        if not vertex_available():
            raise
        force_vertex(reason=f"{type(exc).__name__}: {exc}")
        return fn()
