"""既存の OCR（プレーンテキスト抽出）ロジック。"""

import json
import os
from pathlib import Path

from google import genai
from google.genai import types

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


def get_client() -> genai.Client:
    """Gemini クライアントを初期化する（Vertex AI Express モード）。"""
    return genai.Client(
        vertexai=True,
        api_key=os.environ.get("VERTEX_AI_API_KEY"),
    )


def generate_json(
    contents: list,
    *,
    model: str = FLASH_MODEL,
    temperature: float = 0.0,
) -> dict | list:
    """Gemini に JSON レスポンスを要求し、パース結果を返す。"""
    client = get_client()
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=temperature,
        ),
    )
    try:
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        msg = f"Gemini が不正な JSON を返しました: {response.text[:200]}"
        raise ValueError(msg) from exc


def ocr_image(client: genai.Client, image_path: Path) -> str:
    """画像ファイルを Gemini に送信し、OCR 結果のテキストを返す。"""
    mime_type = MIME_TYPES[image_path.suffix.lower()]
    image_bytes = image_path.read_bytes()

    with tracker.timer("Gemini OCR", str(image_path)):
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                OCR_PROMPT,
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
        )
    return response.text
