"""docai モード: Document AI で OCR し、Gemini で構造化抽出する。"""

import json
import os
from pathlib import Path

from google.cloud import documentai_v1 as documentai
from google.genai import types

from nova_parser.ocr import MIME_TYPES, get_client

GEMINI_MODEL = "gemini-3-flash-preview"

EXTRACT_PROMPT = """\
以下はTRPGルールブックのページから OCR で抽出したテキストです。
このテキストに含まれるゲームデータを抽出してください。

以下はデータ型の例です:
- スキル: 名称, ルビ, 技能, 上限, タイミング, 対象, 射程, 目標値, 対決, 解説
- 防具: 名称, ルビ, 購, 隠, 防S, 防P, 防I, 制, 電制, 部位, 解説
- サービス: 名称, ルビ, 購, 隠, 電制, 部位, 解説
- ニューラルウェア: 名称, ルビ, 購, 隠, 電制, 部位, 解説

上記以外のデータ型がテキストにある場合は、適切な型名とフィールドを定義して抽出してください。
該当するデータがない場合はtypesを空配列にしてください。
各項目の値は原文をできるだけ忠実に抽出してください。

出力は以下のJSON形式に従ってください:
{"types": [{"type_name": "白兵武器", "items": [{"名称": "...", "ルビ": "...", ...}]}]}

--- OCR テキスト ---
"""


def get_processor_name() -> str:
    """環境変数から Document AI プロセッサのリソース名を取得する。"""
    name = os.environ.get("DOCUMENT_AI_PROCESSOR")
    if not name:
        msg = (
            "環境変数 DOCUMENT_AI_PROCESSOR が設定されていません。\n"
            "例: projects/PROJECT_NUMBER/locations/LOCATION/processors/PROCESSOR_ID"
        )
        raise RuntimeError(msg)
    return name


def _get_documentai_client() -> documentai.DocumentProcessorServiceClient:
    """Document AI クライアントを初期化する（OAuth2 / ADC 認証）。

    GOOGLE_APPLICATION_CREDENTIALS が存在しないファイルを指している場合は
    一時的に無視して gcloud ADC にフォールバックする。
    """
    creds_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_file and not Path(creds_file).exists():
        saved = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS")
        try:
            return documentai.DocumentProcessorServiceClient()
        except Exception:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved
            raise
    return documentai.DocumentProcessorServiceClient()


def ocr_with_documentai(image_path: Path) -> str:
    """Document AI で画像を OCR し、テキストを返す。"""
    processor_name = get_processor_name()
    client = _get_documentai_client()
    mime_type = MIME_TYPES[image_path.suffix.lower()]
    image_content = image_path.read_bytes()

    raw_document = documentai.RawDocument(
        content=image_content,
        mime_type=mime_type,
    )
    request = documentai.ProcessRequest(
        name=processor_name,
        raw_document=raw_document,
    )

    result = client.process_document(request=request)
    text = result.document.text
    # Document AI は「N◎VA」を「NOVA」として認識するため補正する
    text = text.replace("NOVA", "N◎VA")
    return text


def extract_gamedata_from_text(ocr_text: str) -> dict:
    """Gemini を使って OCR テキストからゲームデータを構造化抽出する。"""
    gemini_client = get_client()

    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[EXTRACT_PROMPT + ocr_text],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )

    result = json.loads(response.text)
    if isinstance(result, list):
        result = {"types": result}
    return result


def extract_docai(image_path: Path) -> dict:
    """Document AI で OCR → Gemini で構造化抽出のパイプラインを実行する。"""
    ocr_text = ocr_with_documentai(image_path)
    result = extract_gamedata_from_text(ocr_text)
    result["source_file"] = image_path.name
    return result
