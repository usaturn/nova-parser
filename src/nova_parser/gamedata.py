"""gamedata モード: 動的にゲームデータ型を発見・抽出する。"""

import json
from pathlib import Path

from google.genai import types

from nova_parser.ocr import MIME_TYPES, get_client

MODEL = "gemini-3-flash-preview"

GAMEDATA_PROMPT = """\
この画像はTRPGルールブックのページです。
画像に含まれるゲームデータを抽出してください。

以下はデータ型の例です:
- スキル: 名称, ルビ, 技能, 上限, タイミング, 対象, 射程, 目標値, 対決, 解説
- 防具: 名称, ルビ, 購, 隠, 防S, 防P, 防I, 制, 電制, 部位, 解説
- サービス: 名称, ルビ, 購, 隠, 電制, 部位, 解説

上記以外のデータ型が画像にある場合は、適切な型名とフィールドを定義して抽出してください。
該当するデータがない場合はtypesを空配列にしてください。

出力は以下のJSON形式に従ってください:
{"types": [{"type_name": "白兵武器", "items": [{"名称": "...", "ルビ": "...", ...}]}]}
"""


SCHEMA_PROMPT = """\
この画像はTRPGルールブックのページです。
画像に含まれるゲームデータの型名とフィールド名を特定してください。
データの中身は不要です。型の定義（カラム名）のみ出力してください。

以下はデータ型の例です:
- スキル: 名称, ルビ, 技能, 上限, タイミング, 対象, 射程, 目標値, 対決, 解説
- 防具: 名称, ルビ, 購, 隠, 防S, 防P, 防I, 制, 電制, 部位, 解説
- サービス: 名称, ルビ, 購, 隠, 電制, 部位, 解説

上記以外のデータ型が画像にある場合は、適切な型名とフィールドを定義してください。
該当するデータがない場合はtypesを空配列にしてください。

出力は以下のJSON形式に従ってください:
{"types": [{"type_name": "白兵武器", "fields": ["名称", "ルビ", "購", "隠"]}]}
"""


def extract_schema(image_path: Path) -> dict:
    """画像からゲームデータの型名とフィールド名のみを抽出し、dict を返す。"""
    client = get_client()
    mime_type = MIME_TYPES[image_path.suffix.lower()]
    image_bytes = image_path.read_bytes()

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            SCHEMA_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )

    result = json.loads(response.text)
    if isinstance(result, list):
        result = {"types": result}
    return result


def extract_gamedata(image_path: Path) -> dict:
    """画像からゲームデータを動的に抽出し、dict を返す。"""
    client = get_client()
    mime_type = MIME_TYPES[image_path.suffix.lower()]
    image_bytes = image_path.read_bytes()

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            GAMEDATA_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )

    result = json.loads(response.text)
    if isinstance(result, list):
        result = {"types": result}
    result["source_file"] = image_path.name
    return result
