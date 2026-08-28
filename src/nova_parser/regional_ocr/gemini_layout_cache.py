"""Gemini 縦ブロック成功結果の fingerprint / cache。"""

from __future__ import annotations

import datetime
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, Field

from nova_parser.regional_ocr.gemini_layout import MODEL, PROMPT_CONTRACT_VERSION
from nova_parser.regional_ocr.models import BlockRect

_EXAMPLES_PATH = Path(__file__).resolve().parent / "data" / "gemini_vertical_examples.json"


class GeminiLayoutCacheEntry(BaseModel):
    """成功した Gemini 縦ブロック結果の cache 形式。"""

    image_name: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_contract_version: str = Field(min_length=1)
    vertical_blocks: list[BlockRect]
    created_at: datetime.datetime


def cache_path(output_dir: Path, image_name: str) -> Path:
    """Gemini layout cache JSON のパス。image_name は拡張子付き・なし両方を受け付ける。"""
    return output_dir / "gemini-layout-cache" / f"{Path(image_name).stem}.json"


def example_bank_sha256() -> str:
    """同梱 few-shot example bank ファイル bytes の SHA-256。"""
    return hashlib.sha256(_EXAMPLES_PATH.read_bytes()).hexdigest()


def build_fingerprint(
    image_path: Path,
    image_width: int,
    image_height: int,
    candidates: Sequence[BlockRect],
    *,
    model: str = MODEL,
) -> str:
    """モデル入力とプロンプト契約を識別する安定したキャッシュ指紋を返す。"""
    manifest = {
        "candidates": [candidate.model_dump() for candidate in candidates],
        "example_bank_sha256": example_bank_sha256(),
        "image_height": image_height,
        "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        "image_width": image_width,
        "model": model,
        "prompt_contract_version": PROMPT_CONTRACT_VERSION,
    }
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_cached_blocks(output_dir: Path, image_name: str, fingerprint: str) -> list[BlockRect] | None:
    """fingerprint 一致の cache があれば vertical_blocks を返す。欠損・破損・不一致は None。"""
    path = cache_path(output_dir, image_name)
    if not path.exists():
        return None
    try:
        entry = GeminiLayoutCacheEntry.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    if entry.image_name != image_name or entry.fingerprint != fingerprint:
        return None
    return entry.vertical_blocks


def save_cached_blocks(output_dir: Path, entry: GeminiLayoutCacheEntry) -> Path:
    """GeminiLayoutCacheEntry を atomic 書き込みで保存し、保存先 Path を返す。"""
    dest = cache_path(output_dir, entry.image_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(entry.model_dump(mode="json"), indent=2, ensure_ascii=False)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=dest.parent,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        tmp_path.replace(dest)
    finally:
        tmp_path.unlink(missing_ok=True)
    return dest
