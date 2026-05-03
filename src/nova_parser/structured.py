"""Pydantic AI を使った構造化データ抽出。"""

from pathlib import Path

from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.google import GoogleModel

from nova_parser import gemini_backend
from nova_parser.models import PageExtraction
from nova_parser.ocr import MIME_TYPES, MODEL

STRUCTURED_PROMPT = """\
あなたはテーブルトーク RPG のルールブックから構造化データを抽出する専門家です。
画像に含まれるゲームデータを以下のカテゴリに分類して抽出してください:

1. **組織 (organizations)**: 組織名・分類・下部組織・本部・解説
2. **技能・特技 (skills)**: 技能名・ふりがな・前提技能・上限・タイミング・対象・射程・目標値・対決・解説
3. **装備 (equipment)**: 装備名・ふりがな・カテゴリ・タイプ・購入価格・隠匿・防御力(S/P/I)・制・電制・部位・解説
4. **ルール説明文 (rules)**: 見出し・本文・子セクション

注意事項:
- 該当するデータがないカテゴリは空リストにしてください
- 数値フィールドで値が不明・該当なしの場合は null にしてください
- テキストは原文をできるだけ忠実に抽出してください
- 読み取れない文字は [?] と表記してください
"""


def _build_agent() -> Agent[None, PageExtraction]:
    """構造化抽出用の Agent を構築する。

    バックエンド切替時に provider を再生成する必要があるため、毎回最新の
    provider を取得する。
    """
    provider = gemini_backend.get_provider()
    model = GoogleModel(MODEL, provider=provider)
    return Agent(
        model,
        output_type=PageExtraction,
        instructions=STRUCTURED_PROMPT,
    )


def extract_structured(image_path: Path) -> PageExtraction:
    """画像からゲームデータを構造化抽出する。"""
    mime_type = MIME_TYPES[image_path.suffix.lower()]
    image_bytes = image_path.read_bytes()

    contents = [
        "この画像からゲームデータを構造化抽出してください。",
        BinaryContent(data=image_bytes, media_type=mime_type),
    ]
    result = gemini_backend.call_with_backend_fallback(
        lambda: _build_agent().run_sync(contents),
    )

    result.output.source_file = image_path.name
    return result.output
