"""Gemini による縦ブロック候補グループ化の純粋ロジックと few-shot 例読込。

Vision SDK・FastAPI・Gemini API へ依存しない。モデル呼び出しは後続タスクで追加する。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel

from nova_parser.regional_ocr.models import BlockRect

MODEL = "gemini-3.5-flash-lite"
PROMPT_CONTRACT_VERSION = "regional-vertical-groups-v1"
LayoutFamily = Literal["portrait", "landscape_sparse", "landscape_dense"]

_EXAMPLES_PATH = Path(__file__).resolve().parent / "data" / "gemini_vertical_examples.json"


class GeminiLayoutExample(BaseModel):
    """テキスト few-shot 用の1ページ分の例（画像 bytes / path は含まない）。"""

    stem: str
    family: LayoutFamily
    image_width: int
    image_height: int
    candidates: list[BlockRect]
    groups: list[list[int]]


def classify_layout(image_width: int, image_height: int, candidate_count: int) -> LayoutFamily:
    """向きと候補密度から few-shot 用のレイアウト種別を返す。"""
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
