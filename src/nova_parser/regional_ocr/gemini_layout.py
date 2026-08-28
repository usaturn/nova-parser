"""Gemini による縦ブロック候補グループ化とモデル呼び出し。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Literal, Sequence

from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel

from nova_parser import gemini_backend
from nova_parser.regional_ocr.models import BlockRect

MODEL = "gemini-3.5-flash-lite"
PROMPT_CONTRACT_VERSION = "regional-vertical-groups-v1"
LayoutFamily = Literal["portrait", "landscape_sparse", "landscape_dense"]

_EXAMPLES_PATH = Path(__file__).resolve().parent / "data" / "gemini_vertical_examples.json"
_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
GROUP_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "groups": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"candidate_ids": {"type": "ARRAY", "items": {"type": "INTEGER"}}},
                "required": ["candidate_ids"],
            },
        }
    },
    "required": ["groups"],
}
_OUTPUT_TOKEN_LIMITS = (2048, 8192)
_GENERATION_FAILED = "Gemini vertical layout generation failed"


class GeminiLayoutError(RuntimeError):
    """Gemini 縦ブロック生成が失敗した場合の例外。"""


class GeminiLayoutExample(BaseModel):
    """テキスト few-shot 用の1ページ分の例（画像 bytes / path は含まない）。"""

    stem: str
    family: LayoutFamily
    image_width: int
    image_height: int
    candidates: list[BlockRect]
    groups: list[list[int]]


def classify_layout(image_width: int, image_height: int, candidate_count: int) -> LayoutFamily:
    """向きと段落密度から few-shot 用のレイアウト種別を返す。

    ``candidate_count`` は縦ブロック統合前の Cloud Vision 段落／テキストブロック数
    （fixture の ``paragraph_blocks`` 長）。統合後の縦ブロック候補数ではない。
    横長かつこの値が 80 以上なら ``landscape_dense``、未満なら ``landscape_sparse``。
    """
    if image_height >= image_width:
        return "portrait"
    if candidate_count >= 80:
        return "landscape_dense"
    return "landscape_sparse"


def groups_from_expected(
    candidates: Sequence[BlockRect],
    expected: Sequence[BlockRect],
) -> list[list[int]]:
    """正解矩形内に中心がある候補を、重複なしの few-shot 正解 groups へ変換する。"""
    assigned: set[int] = set()
    groups: list[list[int]] = []
    for target in expected:
        ids: list[int] = []
        for index, candidate in enumerate(candidates):
            if index in assigned:
                continue
            center_x = candidate.x + candidate.width / 2
            center_y = candidate.y + candidate.height / 2
            if target.left <= center_x <= target.right and target.top <= center_y <= target.bottom:
                ids.append(index)
                assigned.add(index)
        if ids:
            groups.append(ids)
    return groups


def validate_candidate_groups(payload: object, candidate_count: int) -> list[list[int]]:
    """モデル JSON を検証し、正規化した groups を返す。bool は整数として受理しない。"""
    if not isinstance(payload, dict) or not isinstance(payload.get("groups"), list):
        raise ValueError("groups must be an array")
    raw_groups = payload["groups"]
    if candidate_count and not raw_groups:
        raise ValueError("at least one group is required")
    used: set[int] = set()
    groups: list[list[int]] = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, dict) or not isinstance(raw_group.get("candidate_ids"), list):
            raise ValueError("candidate_ids must be an array")
        ids = raw_group["candidate_ids"]
        if not ids:
            raise ValueError("empty group is not allowed")
        for candidate_id in ids:
            if isinstance(candidate_id, bool) or not isinstance(candidate_id, int):
                raise ValueError("candidate id must be an integer")
            if not 0 <= candidate_id < candidate_count:
                raise ValueError("candidate id is out of range")
            if candidate_id in used:
                raise ValueError("duplicate candidate id")
            used.add(candidate_id)
        groups.append(ids)
    return groups


def merge_candidate_groups(
    candidates: Sequence[BlockRect],
    groups: Sequence[Sequence[int]],
) -> list[BlockRect]:
    """検証済み groups の各候補集合を外接矩形へ変換する。"""
    merged: list[BlockRect] = []
    for group in groups:
        blocks = [candidates[index] for index in group]
        left = min(block.x for block in blocks)
        top = min(block.y for block in blocks)
        right = max(block.right for block in blocks)
        bottom = max(block.bottom for block in blocks)
        merged.append(BlockRect(x=left, y=top, width=right - left, height=bottom - top))
    return merged


def load_examples(family: LayoutFamily) -> list[GeminiLayoutExample]:
    """同梱 few-shot bank から指定 family の例だけを返す。"""
    payload = json.loads(_EXAMPLES_PATH.read_text(encoding="utf-8"))
    examples = [GeminiLayoutExample.model_validate(item) for item in payload["examples"]]
    return [example for example in examples if example.family == family]


def _candidate_payload(candidates: Sequence[BlockRect]) -> list[dict[str, int]]:
    return [{"id": index, **candidate.model_dump()} for index, candidate in enumerate(candidates)]


def _group_instructions(image_width: int, image_height: int, candidates: Sequence[BlockRect]) -> str:
    listed = _candidate_payload(candidates)
    return (
        "日本語書籍ページのOCR用「縦ブロック」を作るため、ローカル候補を統合・除外してください。\n"
        "これは段落抽出ではなく、UIで1回クリックしてOCRする大きな長方形cropです。\n"
        "\n"
        "- 同じ視覚列で縦に続く候補は、途中に空白や見出しがあっても同じgroupへ統合する。\n"
        "- 左右の独立列、欄外注釈、別カード、上下段だけを分ける。\n"
        "- ヘッダー、フッター、ページ番号、罫線、図だけの候補は除外する。\n"
        "- candidate IDは全groupsを通じて最大1回だけ使用する。\n"
        "- 正しいcropを作る最小限のgroupsを読み順で返す。\n"
        "\n"
        f"画像寸法: {image_width}x{image_height}\n"
        f"候補: {json.dumps(listed, ensure_ascii=False)}"
    )


def _groups_json(groups: Sequence[Sequence[int]]) -> str:
    return json.dumps({"groups": [{"candidate_ids": list(group)} for group in groups]}, ensure_ascii=False)


def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def _image_part(path: Path) -> types.Part:
    mime_type = _IMAGE_MIME_TYPES[path.suffix.lower()]
    return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type)


def _build_contents(
    image_path: Path,
    image_width: int,
    image_height: int,
    candidates: Sequence[BlockRect],
    family: LayoutFamily,
) -> list[types.Content]:
    contents: list[types.Content] = []
    for example in load_examples(family):
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text="これは正解例です。この統合粒度を学習してください。\n"
                        + _group_instructions(example.image_width, example.image_height, example.candidates)
                    )
                ],
            )
        )
        contents.append(
            types.Content(
                role="model",
                parts=[types.Part.from_text(text=_groups_json(example.groups))],
            )
        )
    contents.append(
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text="上の正解例から最も近いレイアウトの粒度を適用してください。\n"
                    + _group_instructions(image_width, image_height, candidates)
                ),
                _image_part(image_path),
            ],
        )
    )
    return contents


def _generate_content(
    client_factory: Callable[[], genai.Client],
    model: str,
    contents: list[types.Content],
    max_output_tokens: int,
) -> object:
    return gemini_backend.call_with_backend_fallback(
        lambda: client_factory().models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=GROUP_SCHEMA,
                thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
                temperature=0,
                max_output_tokens=max_output_tokens,
            ),
        )
    )


def _parse_json_with_token_retry(generate: Callable[[int], object]) -> object:
    """JSON が MAX_TOKENS で切れた場合だけ出力上限を増やして1回再試行する。"""
    for index, max_output_tokens in enumerate(_OUTPUT_TOKEN_LIMITS):
        response = generate(max_output_tokens)
        try:
            return json.loads(response.text)  # type: ignore[attr-defined]
        except json.JSONDecodeError:
            finish_candidates = getattr(response, "candidates", None) or []
            finish_reason = finish_candidates[0].finish_reason if finish_candidates else None
            if finish_reason == types.FinishReason.MAX_TOKENS and index + 1 < len(_OUTPUT_TOKEN_LIMITS):
                continue
            raise
    raise RuntimeError("unreachable")


def _layout_family(
    image_width: int,
    image_height: int,
    source_block_count: int | None,
) -> LayoutFamily:
    """few-shot family を決める。横長では段落数が必須で、縦ブロック数は使わない。"""
    if source_block_count is not None:
        return classify_layout(image_width, image_height, source_block_count)
    if image_height >= image_width:
        return classify_layout(image_width, image_height, 0)
    raise ValueError("source_block_count (pre-merge paragraph count) is required for landscape pages")


def generate_vertical_blocks(
    image_path: Path,
    candidates: Sequence[BlockRect],
    *,
    client_factory: Callable[[], genai.Client] = gemini_backend.get_client,
    model: str = MODEL,
    source_block_count: int | None = None,
) -> list[BlockRect]:
    """対象画像と縦ブロック候補を Gemini で group 化し、外接矩形を返す。

    ``source_block_count`` は ``classify_layout`` に渡す Cloud Vision 段落数。
    縦ブロック候補数は渡さない。portrait では省略可。横長では必須。
    """
    try:
        image_width, image_height = _image_size(image_path)
        family = _layout_family(image_width, image_height, source_block_count)
        contents = _build_contents(image_path, image_width, image_height, candidates, family)
        parsed = _parse_json_with_token_retry(
            lambda max_output_tokens: _generate_content(client_factory, model, contents, max_output_tokens)
        )
        groups = validate_candidate_groups(parsed, len(candidates))
        return merge_candidate_groups(candidates, groups)
    except Exception as error:
        raise GeminiLayoutError(_GENERATION_FAILED) from error
