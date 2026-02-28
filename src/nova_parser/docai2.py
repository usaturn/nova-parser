"""docai2 モード: Document AI OCR + Gemini 構造化抽出 → TSV 出力。

既存 docai モードの改良版。以下の点を改善:
- None が文字列として TSV に出力される問題を修正
- プロンプトを改良（None 排除の明示指示、フィールド名の忠実使用）
"""

import json
import os
from pathlib import Path

from google.cloud import documentai_v1 as documentai
from google.genai import types

from nova_parser.ocr import MIME_TYPES, get_client

GEMINI_MODEL = "gemini-3-flash-preview"

EXTRACT_PROMPT = """\
以下はTRPGルールブック「トーキョーN◎VA」のページからOCRで抽出したテキストです。
このテキストに含まれるゲームデータを抽出してください。

【重要な指示】
- 値が存在しない・不明なフィールドは空文字列 "" にしてください。null や None は絶対に使わないでください。
- フィールド名（キー名）は、画像の表の列見出しをそのまま使用してください。独自のフィールド名に変換しないでください。
- 各項目の値は原文をできるだけ忠実に抽出してください。

以下はデータ型の例です。ただし画像の表見出しを忠実に使うこと:
- スキル: 名称, ルビ, 技能, 上限, タイミング, 対象, 射程, 目標値, 対決, 解説
- 防具: 名称, ルビ, 購, 隠, 防S, 防P, 防I, 制, 電制, 部位, 解説
- サービス/ソーシャル: 名称, ルビ, 購, 隠, 電制, 部位, 解説
- 組織: 名称, ルビ, 分類, 下部組織, 本部, 解説
- 白兵武器: 名称, ルビ, 隠, 受, ス, 購, 攻, 射, 電制, 部位, 解説
- 射撃武器: 名称, ルビ, 隠, 受, ス, 購, 攻, 射, 電制, 部位, 解説
- ニューラルウェア: 名称, ルビ, 購, 隠, 電制, 部位, 解説

上記以外のデータ型がテキストにある場合は、画像の見出しに基づいて適切な型名とフィールドを定義して抽出してください。
該当するデータがない場合はtypesを空配列にしてください。

出力は以下のJSON形式に従ってください:
{"types": [{"type_name": "白兵武器", "items": [{"名称": "...", "ルビ": "...", ...}]}]}

--- OCR テキスト ---
"""


def get_docai_client() -> documentai.DocumentProcessorServiceClient:
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


def _get_processor_name() -> str:
    """環境変数から Document AI プロセッサのリソース名を取得する。"""
    name = os.environ.get("DOCUMENT_AI_PROCESSOR")
    if not name:
        msg = (
            "環境変数 DOCUMENT_AI_PROCESSOR が設定されていません。\n"
            "例: projects/PROJECT_NUMBER/locations/LOCATION/processors/PROCESSOR_ID"
        )
        raise RuntimeError(msg)
    return name


def ocr_image(image_path: Path) -> str:
    """Document AI で画像を OCR し、テキストを返す。"""
    processor_name = _get_processor_name()
    client = get_docai_client()
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


def classify_and_extract(ocr_text: str) -> dict:
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


def _safe_value(val: object) -> str:
    """値を安全に文字列に変換する。None は空文字列にする。"""
    if val is None:
        return ""
    return str(val)


def to_tsv(result: dict) -> str:
    """構造化抽出結果を TSV 文字列に変換する。"""
    blocks: list[str] = []
    for t in result.get("types", []):
        type_name = t["type_name"]
        items = t.get("items", [])
        if not items:
            continue
        # 全アイテムからフィールド名を収集（出現順を保持）
        field_names: list[str] = []
        seen: set[str] = set()
        for item in items:
            for key in item:
                if key not in seen:
                    field_names.append(key)
                    seen.add(key)
        header = f"## {type_name}\n" + "\t".join(field_names)
        rows = ["\t".join(_safe_value(item.get(f, "")) for f in field_names) for item in items]
        blocks.append(header + "\n" + "\n".join(rows))
    return "\n\n".join(blocks) + "\n" if blocks else ""


def extract_docai2(image_path: Path) -> str:
    """Document AI OCR → Gemini 構造化抽出 → TSV 変換のパイプラインを実行する。"""
    ocr_text = ocr_image(image_path)
    result = classify_and_extract(ocr_text)
    result["source_file"] = image_path.name
    return to_tsv(result)
