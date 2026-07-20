"""正本 JSONL の原子書き込みとレビュー判断の読み込み・適用。"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from nova_parser.semistructure.models import ReviewDecision, ReviewStatus, SemanticSegment

T = TypeVar("T", bound=BaseModel)

_STALE_REASON = "stale_review_decision"


def write_jsonl_atomic(path: Path, records: Iterable[BaseModel]) -> None:
    """同一ディレクトリの一時ファイルへ JSONL を書き、`Path.replace()` で確定する。

    - エンコーディング: UTF-8
    - `model_dump_json(ensure_ascii=False)` で 1 行 1 JSON
    - 親ディレクトリが無ければ作成する
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for record in records:
                handle.write(record.model_dump_json(ensure_ascii=False))
                handle.write("\n")
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def read_jsonl(path: Path, model_type: type[T]) -> list[T]:
    """JSONL を 1 行ずつ `model_type` として読み込む。空行は無視する。"""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    records: list[T] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        records.append(model_type.model_validate_json(stripped))
    return records


def load_review_decisions(path: Path) -> dict[str, ReviewDecision]:
    """レビュー判断 JSONL を `review_id` キーの辞書として読み込む。

    同一 `review_id` が複数ある場合は後勝ちとする。
    """
    decisions = read_jsonl(path, ReviewDecision)
    return {decision.review_id: decision for decision in decisions}


def apply_review_decisions(
    segments: Sequence[SemanticSegment],
    decisions: Mapping[str, ReviewDecision],
) -> list[SemanticSegment]:
    """人手判断を正本セグメントへ再適用する。

    適用条件:
    - `review_id` が `"{book_id}:{segment_id}"` と一致（または decisions が segment_id キー）
    - `decision.segment_id == segment.segment_id`
    - `decision.input_hash` がセグメントの現行入力ハッシュと一致

    入力ハッシュの解決順:
    1. `processing["input_hash"]`
    2. `processing["input_sha256"]`（構造分類器の入力ハッシュ）
    3. 上記が無い場合は `raw_text` と `source_spans` から計算した決定的ハッシュ

    ハッシュ不一致の判断は適用せず、`stale_review_decision` を理由に
    `review_status=REQUIRED` へ戻す。
    """
    applied: list[SemanticSegment] = []
    for segment in segments:
        decision = _lookup_decision(segment, decisions)
        if decision is None:
            applied.append(segment)
            continue

        if decision.segment_id != segment.segment_id:
            applied.append(segment)
            continue

        current_hash = resolve_segment_input_hash(segment)
        if decision.input_hash != current_hash:
            applied.append(_mark_stale_review(segment))
            continue

        applied.append(segment.model_copy(update={"review_status": ReviewStatus(decision.status)}))
    return applied


def resolve_segment_input_hash(segment: SemanticSegment) -> str:
    """レビュー判断照合用の入力ハッシュをセグメントから解決する。"""
    processing = segment.processing
    if processing.get("input_hash"):
        return processing["input_hash"]
    if processing.get("input_sha256"):
        return processing["input_sha256"]
    return _compute_source_input_hash(segment)


def _lookup_decision(
    segment: SemanticSegment,
    decisions: Mapping[str, ReviewDecision],
) -> ReviewDecision | None:
    """review_id 優先、無ければ segment_id キーで判断を探す。"""
    review_id = f"{segment.book_id}:{segment.segment_id}"
    if review_id in decisions:
        return decisions[review_id]
    return decisions.get(segment.segment_id)


def _mark_stale_review(segment: SemanticSegment) -> SemanticSegment:
    """古い判断を無効化し、再レビュー必須にする。"""
    reasons = _split_reasons(segment.processing.get("review_reasons", ""))
    if _STALE_REASON not in reasons:
        reasons.append(_STALE_REASON)
    processing = dict(segment.processing)
    processing["review_reasons"] = ",".join(reasons)
    return segment.model_copy(
        update={
            "review_status": ReviewStatus.REQUIRED,
            "processing": processing,
        }
    )


def _split_reasons(raw: str) -> list[str]:
    """CSV 形式のレビュー理由を分割する。"""
    return [part.strip() for part in raw.split(",") if part.strip()]


def _compute_source_input_hash(segment: SemanticSegment) -> str:
    """processing にハッシュが無いときの決定的フォールバック。"""
    span_parts = [f"{span.page}:{span.rect_id}:{span.start}:{span.end}" for span in segment.source_spans]
    payload = "|".join(
        [
            segment.book_id,
            segment.segment_id,
            segment.raw_text,
            segment.normalized_text,
            ",".join(span_parts),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
