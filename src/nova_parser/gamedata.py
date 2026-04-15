"""gamedata モード: 動的にゲームデータ型を発見・抽出する。"""

from pathlib import Path

from google.genai import types

from nova_parser.json_contracts import build_gamedata_result_schema, validate_gamedata_result
from nova_parser.ocr import MIME_TYPES, JSONFailureArtifact, generate_json
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


def extract_gamedata(image_path: Path, *, output_dir: Path = Path("Output")) -> dict:
    """画像からゲームデータを動的に抽出し、dict を返す。"""
    mime_type = MIME_TYPES[image_path.suffix.lower()]
    image_bytes = image_path.read_bytes()

    prompt = GAMEDATA_PROMPT
    result = generate_json(
        [
            prompt,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
        response_json_schema=build_gamedata_result_schema(),
        result_validator=validate_gamedata_result,
        failure_artifact=JSONFailureArtifact(
            output_path=output_dir / f"{image_path.stem}.gamedata.gemini_json_error.json",
            mode="gamedata",
            source_path=image_path,
            prompt=prompt,
        ),
    )
    if not isinstance(result, dict):
        msg = "gamedata の JSON トップレベルが object ではありません。"
        raise ValueError(msg)
    result["source_file"] = image_path.name
    return result
