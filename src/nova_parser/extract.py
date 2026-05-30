"""extract モードの核心ロジック（キャッシュ・TSV commit・スキーマ検証）。

main.py から Phase 3 で一次切り出し（M1 完遂 + A1 基盤）。
- C1: 画像単位キャッシュの多層 fingerprint（prompt/model/extractor/contract）
- スキーマ入口検証（S1）
- TSV 原子 commit（staging + manifest + backup）

run_extract（main.py）は「並列/進捗/集計オーケストレーション + extractor 注入」の薄いラッパー。
Extractor Protocol はここで定義し、注入可能にする。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from nova_parser.json_contracts import (
    EXTRACT_RESULT_SCHEMA_VERSION,
    EXTRACT_VALIDATOR_VERSION,
)
from nova_parser.ocr import EXTRACT_MODEL
from nova_parser.prompts import (
    EXTRACT_PROMPT_CONTRACT_VERSION,
    SCHEMA_EXTRACT_PROMPT,
)


@dataclass(frozen=True, slots=True)
class _CacheMiss:
    """extract キャッシュをヒットと見なせなかった理由。"""

    reason: str


@dataclass(frozen=True, slots=True)
class _ExtractFingerprints:
    """C1: extract モードのキャッシュ無効化に用いる多層 fingerprint 群。

    いずれかの不一致でキャッシュミス（機械的 stale 防止）。
    """

    schema: str
    prompt: str
    model: str
    extractor_id: str
    result_schema: str
    validator: str


def _schema_fingerprint(schema: dict) -> str:
    """スキーマ内容の SHA-256 を算出する（main.py から移動）。"""
    canonical = json.dumps(schema, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _compute_extract_prompt_fingerprint() -> str:
    """C1: SCHEMA_EXTRACT_PROMPT + 契約版から prompt_fingerprint を算出。"""
    h = hashlib.sha256()
    h.update(SCHEMA_EXTRACT_PROMPT.encode("utf-8"))
    h.update(f"|contract:{EXTRACT_PROMPT_CONTRACT_VERSION}".encode("utf-8"))
    return f"sha256:{h.hexdigest()}"


def _build_extract_fingerprints(schema: dict) -> _ExtractFingerprints:
    """C1: run 単位で全 fingerprint を 1 回構築（extractor_id は現時点ハードコード）。"""
    schema_fp = _schema_fingerprint(schema)
    prompt_fp = _compute_extract_prompt_fingerprint()
    model = EXTRACT_MODEL
    extractor_id = "gemini-extract/v1"  # 将来: 注入された Extractor から取得
    result_schema_fp = f"v{EXTRACT_RESULT_SCHEMA_VERSION}"
    validator_fp = f"v{EXTRACT_VALIDATOR_VERSION}"

    return _ExtractFingerprints(
        schema=schema_fp,
        prompt=prompt_fp,
        model=model,
        extractor_id=extractor_id,
        result_schema=result_schema_fp,
        validator=validator_fp,
    )


__all__ = [
    "_CacheMiss",
    "_ExtractFingerprints",
    "_schema_fingerprint",
    "_compute_extract_prompt_fingerprint",
    "_build_extract_fingerprints",
]
