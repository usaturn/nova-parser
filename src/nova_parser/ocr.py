"""既存の OCR（プレーンテキスト抽出）ロジック。"""

import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from google import genai
from google.genai import types

from nova_parser import gemini_backend
from nova_parser.perf import tracker

MIME_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

OCR_PROMPT = """\
この画像に含まれるテキストを全て抽出してください。
- 元のレイアウトや改行をできるだけ維持してください
- 表がある場合は Markdown のテーブル形式で出力してください
- 読み取れない文字は [?] と表記してください
"""

MODEL = "gemini-3.1-pro-preview"
FLASH_MODEL = "gemini-3-flash-preview"
JSON_DECODE_RETRY_ATTEMPTS = 2
JSON_DECODE_RETRY_WAIT_SECONDS = 1.0


class GeminiJSONError(ValueError):
    """Gemini の JSON レスポンスが不正だった場合の例外。"""


@dataclass(frozen=True)
class JSONFailureArtifact:
    """Gemini JSON 失敗時に保存する調査用アーティファクト。"""

    output_path: Path
    mode: str
    source_path: Path
    prompt: str
    ocr_text: str | None = None


def get_client() -> genai.Client:
    """Gemini クライアントを取得する。

    バックエンド選択（AI Studio 優先 / Vertex AI フォールバック）は
    :mod:`nova_parser.gemini_backend` に集約されている。
    """
    return gemini_backend.get_client()


def _atomic_write_text(output_file: Path, text: str) -> None:
    """同一ディレクトリ上の一時ファイル経由でテキストを書き込む。"""
    output_file.parent.mkdir(exist_ok=True)
    tmp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output_file.parent,
            prefix=f".{output_file.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_file.write(text)
            tmp_path = Path(tmp_file.name)
        tmp_path.replace(output_file)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def _coerce_json_result(parsed: Any) -> dict | list:
    """SDK の parsed 結果を dict/list に正規化する。"""
    if isinstance(parsed, (dict, list)):
        return parsed
    if hasattr(parsed, "model_dump"):
        dumped = parsed.model_dump(mode="json")
        if isinstance(dumped, (dict, list)):
            return dumped

    msg = f"Gemini JSON の parsed 結果が想定外です: {type(parsed).__name__}"
    raise ValueError(msg)


def _write_json_failure_artifact(
    artifact: JSONFailureArtifact,
    *,
    model: str,
    response_text: str,
    error_type: str,
    error_message: str,
) -> Path:
    """Gemini JSON 失敗時の調査用アーティファクトを書き出す。"""
    payload = {
        "mode": artifact.mode,
        "source_path": str(artifact.source_path),
        "model": model,
        "error_type": error_type,
        "error_message": error_message,
        "response_text": response_text,
        "prompt": artifact.prompt,
        "ocr_text": artifact.ocr_text,
    }
    _atomic_write_text(
        artifact.output_path,
        json.dumps(payload, indent=2, ensure_ascii=False),
    )
    return artifact.output_path


def _raise_generate_json_error(
    *,
    model: str,
    response_text: str,
    exc: Exception,
    failure_artifact: JSONFailureArtifact | None,
    is_parse_json_error: bool,
) -> None:
    """generate_json 失敗時のアーティファクト保存と例外送出をまとめる。"""
    artifact_path: Path | None = None
    if failure_artifact is not None:
        artifact_path = _write_json_failure_artifact(
            failure_artifact,
            model=model,
            response_text=response_text,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )

    if is_parse_json_error:
        msg = f"Gemini が不正な JSON を返しました: {response_text[:200]}"
    else:
        msg = f"Gemini JSON の検証に失敗しました: {exc}"
    if artifact_path is not None:
        msg += f" (詳細: {artifact_path})"
    raise GeminiJSONError(msg) from exc


def generate_json(
    contents: list,
    *,
    model: str = FLASH_MODEL,
    temperature: float = 0.0,
    response_json_schema: Any | None = None,
    result_validator: Callable[[dict | list], None] | None = None,
    failure_artifact: JSONFailureArtifact | None = None,
) -> dict | list:
    """Gemini に JSON レスポンスを要求し、パース結果を返す。"""
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=response_json_schema,
        temperature=temperature,
    )

    for attempt in range(JSON_DECODE_RETRY_ATTEMPTS):
        response = gemini_backend.call_with_backend_fallback(
            lambda: get_client().models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        )
        response_text = response.text or ""

        try:
            if response.parsed is not None:
                result = _coerce_json_result(response.parsed)
            else:
                result = json.loads(response_text)
        except json.JSONDecodeError as exc:
            if attempt < JSON_DECODE_RETRY_ATTEMPTS - 1:
                if failure_artifact is not None:
                    print(
                        f"  {failure_artifact.source_path.name}: "
                        f"JSONDecodeError のため {JSON_DECODE_RETRY_WAIT_SECONDS:.1f}秒後に再試行 "
                        f"({attempt + 1}/{JSON_DECODE_RETRY_ATTEMPTS})",
                        flush=True,
                    )
                time.sleep(JSON_DECODE_RETRY_WAIT_SECONDS)
                continue
            _raise_generate_json_error(
                model=model,
                response_text=response_text,
                exc=exc,
                failure_artifact=failure_artifact,
                is_parse_json_error=True,
            )
        except (TypeError, ValueError) as exc:
            _raise_generate_json_error(
                model=model,
                response_text=response_text,
                exc=exc,
                failure_artifact=failure_artifact,
                is_parse_json_error=False,
            )

        try:
            if result_validator is not None:
                result_validator(result)
        except (TypeError, ValueError) as exc:
            _raise_generate_json_error(
                model=model,
                response_text=response_text,
                exc=exc,
                failure_artifact=failure_artifact,
                is_parse_json_error=False,
            )
        return result

    msg = "JSONDecodeError リトライ処理が不正な状態で終了しました。"
    raise RuntimeError(msg)


def ocr_image(image_path: Path) -> str:
    """画像ファイルを Gemini に送信し、OCR 結果のテキストを返す。"""
    mime_type = MIME_TYPES[image_path.suffix.lower()]
    image_bytes = image_path.read_bytes()

    with tracker.timer("Gemini OCR", str(image_path)):
        response = gemini_backend.call_with_backend_fallback(
            lambda: get_client().models.generate_content(
                model=MODEL,
                contents=[
                    OCR_PROMPT,
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
            )
        )
    return response.text
