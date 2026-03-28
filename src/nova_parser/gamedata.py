"""gamedata モード: 動的にゲームデータ型を発見・抽出する。"""

from pathlib import Path

from google.genai import types

from nova_parser.ocr import MIME_TYPES, generate_json
from nova_parser.prompts import GAMEDATA_PROMPT, SCHEMA_DISCOVER_PROMPT


def extract_schema(image_path: Path) -> dict:
    """画像からゲームデータの型名とフィールド名のみを抽出し、dict を返す。"""
    mime_type = MIME_TYPES[image_path.suffix.lower()]
    image_bytes = image_path.read_bytes()

    result = generate_json(
        [
            SCHEMA_DISCOVER_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ]
    )
    if isinstance(result, list):
        result = {"types": result}
    return result


def extract_gamedata(image_path: Path) -> dict:
    """画像からゲームデータを動的に抽出し、dict を返す。"""
    mime_type = MIME_TYPES[image_path.suffix.lower()]
    image_bytes = image_path.read_bytes()

    result = generate_json(
        [
            GAMEDATA_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ]
    )
    if isinstance(result, list):
        result = {"types": result}
    result["source_file"] = image_path.name
    return result
