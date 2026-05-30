"""extract モードの核心ロジック（キャッシュ・TSV commit・スキーマ検証）。

M1 進行中: main.py から段階的に一次切り出し（モノリス解消）。
- C1: 画像単位キャッシュの多層 fingerprint — 完了
- S1: スキーマ入口検証 — 完了（Phase A）
- キャッシュ層全体（CACHE_VERSION / _load / _save / hash / path / ensure_unique） — Phase B+C 完了
- TSV 原子 commit（_build / _commit / manifest / staging / backup） — 次の大物（Phase D）

現在の run_extract（main.py）は「並列制御・進捗表示・集計」のオーケストレーション層。
将来的に Extractor Protocol をここで定義し注入可能にする。
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

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


# --- Schema validation (S1: M1 Phase A 移動) ---------------------------------

_NON_EXTRACT_TSV_SUFFIXES = (".docai.tsv", ".structured.tsv", ".schema.tsv")
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _sanitize_type_filename(name: str) -> str:
    """モデル由来の type_name を OS 安全なファイル名断片に整える。"""
    sanitized = _UNSAFE_FILENAME_RE.sub("_", name).strip(" .")
    sanitized = sanitized.encode("utf-8")[:200].decode("utf-8", errors="ignore")
    return sanitized or "_"


def _validate_schema_type_names(schema: dict) -> None:
    """extract schema の matched 側 type_name をファイル名として検証する。"""

    def invalid_type_name(name: object, reason: str) -> None:
        if isinstance(name, str):
            display_name = name.encode("unicode_escape").decode("ascii")
        else:
            display_name = repr(name)
        msg = f'extract schema の type_name "{display_name}" はファイル名として使えません: {reason}'
        raise ValueError(msg)

    types = schema.get("types")
    if not isinstance(types, list):
        raise ValueError("extract schema の types は list である必要があります")

    seen_type_names: set[str] = set()
    seen_sanitized_names: dict[str, str] = {}
    for index, type_data in enumerate(types):
        if not isinstance(type_data, dict):
            raise ValueError(f"extract schema の types[{index}] は object である必要があります")

        type_name = type_data.get("type_name")
        if not isinstance(type_name, str):
            invalid_type_name(type_name, "文字列である必要があります")
        if not type_name.strip():
            invalid_type_name(type_name, "空文字や空白だけの名前は使えません")
        if ".." in type_name:
            invalid_type_name(type_name, '".." を含められません')
        if "\\" in type_name:
            invalid_type_name(type_name, "バックスラッシュを含められません")
        if re.search(r"[\x00-\x1f]", type_name):
            invalid_type_name(type_name, "制御文字を含められません")
        if type_name.startswith("/"):
            invalid_type_name(type_name, "先頭を / にできません")
        if type_name.startswith("."):
            invalid_type_name(type_name, "先頭を . にできません")
        if type_name.endswith((".", " ")):
            invalid_type_name(type_name, "末尾を . や空白にできません")
        if len(type_name.encode("utf-8")) > 200:
            invalid_type_name(type_name, "UTF-8 で 200 バイトを超えています")
        if any(f"{type_name}.tsv".endswith(suffix) for suffix in _NON_EXTRACT_TSV_SUFFIXES):
            invalid_type_name(type_name, "予約された suffix と衝突します")
        if type_name.startswith("none_"):
            invalid_type_name(type_name, "none_ は unmatched TSV 用の予約 prefix です")
        if type_name in seen_type_names:
            invalid_type_name(type_name, "schema 内で重複しています")
        seen_type_names.add(type_name)
        sanitized_name = _sanitize_type_filename(type_name)
        if sanitized_name.startswith("none_"):
            invalid_type_name(type_name, 'sanitize 後に "none_" で始まり unmatched TSV と衝突します')
        if sanitized_name in seen_sanitized_names:
            other_name = seen_sanitized_names[sanitized_name].encode("unicode_escape").decode("ascii")
            invalid_type_name(type_name, f'sanitize 後のファイル名が "{other_name}" と衝突します')
        seen_sanitized_names[sanitized_name] = type_name


def _validate_extract_schema(schema: dict) -> None:
    """extract schema の完全検証（type_name + fields）。

    入口で厳密に保証することで、後段の KeyError / 不親切エラーを防止。
    type_name 検証は既存 _validate_schema_type_names のロジックを維持（エラーメッセージ互換）。
    """
    # まず type_name 系検証（既存ロジックを委譲してメッセージ互換を確保）
    _validate_schema_type_names(schema)

    types = schema.get("types")
    if not isinstance(types, list) or len(types) == 0:
        raise ValueError("extract schema の types は 1 件以上の list である必要があります")

    for t_index, type_data in enumerate(types):
        if not isinstance(type_data, dict):
            # ここは type_name 検証で既に弾かれているが防御
            raise ValueError(f"extract schema の types[{t_index}] は object である必要があります")

        fields = type_data.get("fields")
        tn = type_data.get("type_name") or f"types[{t_index}]"
        if not isinstance(fields, list) or len(fields) == 0:
            raise ValueError(f'extract schema の "{tn}" の fields は 1 件以上の list[str] である必要があります')

        seen_fields: set[str] = set()
        prefix = f'extract schema の "{tn}"'
        for f_index, field in enumerate(fields):
            if not isinstance(field, str):
                raise ValueError(f"{prefix} fields[{f_index}] は文字列である必要があります")
            if not field.strip():
                raise ValueError(f"{prefix} fields[{f_index}] は空文字や空白だけではいけません")
            if re.search(r"[\x00-\x1f]", field):
                raise ValueError(f"{prefix} fields[{f_index}] に制御文字を含められません")
            if field == "source":
                raise ValueError(f'{prefix} のフィールド名 "source" は予約語（TSV 出力列）と衝突します')
            if field in seen_fields:
                raise ValueError(f'{prefix} でフィールド名 "{field}" が重複しています')
            seen_fields.add(field)


__all__ = [
    "_CacheMiss",
    "_ExtractFingerprints",
    "_schema_fingerprint",
    "_compute_extract_prompt_fingerprint",
    "_build_extract_fingerprints",
    # M1 Phase A 移動
    "_NON_EXTRACT_TSV_SUFFIXES",
    "_UNSAFE_FILENAME_RE",
    "_sanitize_type_filename",
    "_validate_schema_type_names",
    "_validate_extract_schema",
    # M1 Phase B 移動
    "CACHE_VERSION",
    "_EXTRACT_CACHE_SUBDIR",
    "_image_content_hash",
    "_extract_cache_path",
    "_ensure_unique_extract_caches",
]

# --- Cache support (M1 Phase B 移動) -----------------------------------------

CACHE_VERSION = "2"  # C1 により payload 形式変更時は bump（旧キャッシュ自動無効化）

_EXTRACT_CACHE_SUBDIR = Path("cache") / "extract"


@functools.lru_cache(maxsize=None)
def _image_content_hash(image: Path) -> str:
    """画像バイト列の SHA-256 を逐次読みで算出する（C1/Q1: プロセス内二重計算を lru で回避）。

    Staged Review 20260530-224330 指摘1対応: 二重適用を解除。
    注意: この cache_clear() 設計は「同一プロセス内で同一Pathのファイルが書き換わる」ケースに依存する。
    よりロバストにする方法（mtime/size をキーにする等）は将来の改善課題。
    """
    hasher = hashlib.sha256()
    with image.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def _extract_cache_path(image: Path, output_dir: Path) -> Path:
    """extract キャッシュの保存パスを返す。"""
    return output_dir / _EXTRACT_CACHE_SUBDIR / f"{image.stem}.json"


def _ensure_unique_extract_caches(images: list[Path]) -> None:
    """extract キャッシュファイル名（image.stem）の衝突を事前検出する。"""
    stem_to_images: dict[str, list[Path]] = {}
    for img in images:
        stem_to_images.setdefault(img.stem, []).append(img)

    collisions = {stem: paths for stem, paths in stem_to_images.items() if len(paths) > 1}
    if not collisions:
        return

    details = "; ".join(
        f"{stem}.json <- {', '.join(str(p) for p in paths)}" for stem, paths in sorted(collisions.items())
    )
    msg = f"extract モードで stem が衝突しキャッシュを一意に決められません: {details}"
    raise ValueError(msg)


# --- Core cache I/O (M1 Phase C 移動) ----------------------------------------


# 注: _atomic_write_text は extract モジュール内でも必要になったためここに定義。
# 将来的にはより下位のユーティリティモジュールへ移動を検討。
def _atomic_write_text(output_file: Path, text: str) -> None:
    """同一ディレクトリ上の一時ファイル経由でテキストを書き込む。"""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output_file.parent,
            prefix=f".{output_file.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_file.write(text)
            tmp_path = Path(tmp_file.name)
        tmp_path.replace(output_file)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def _load_extract_cache(
    image: Path,
    fps: _ExtractFingerprints,
    schema: dict,
    output_dir: Path,
    *,
    cache_version: str | None = None,
) -> dict | _CacheMiss:
    """C1: キャッシュが存在し全 fingerprint 条件を満たす場合のみ結果 dict を返す。

    fps 内の全値（schema/prompt/model/extractor/result_schema/validator）を比較。
    いずれか不一致で具体的な _CacheMiss 理由を返す（stale 防止）。
    """
    from nova_parser.json_contracts import validate_extract_result

    expected_cache_version = CACHE_VERSION if cache_version is None else cache_version
    cache_path = _extract_cache_path(image, output_dir)
    if not cache_path.exists():
        return _CacheMiss("missing")
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return _CacheMiss("corrupted")
    if not isinstance(payload, dict):
        return _CacheMiss("corrupted")
    if payload.get("cache_version") != expected_cache_version:
        return _CacheMiss("cache_version_mismatch")
    if payload.get("schema_hash") != fps.schema:
        return _CacheMiss("schema_mismatch")
    # C1 新規チェック群
    if payload.get("prompt_fingerprint") != fps.prompt:
        return _CacheMiss("prompt_mismatch")
    if payload.get("model") != fps.model:
        return _CacheMiss("model_mismatch")
    if payload.get("extractor_id") != fps.extractor_id:
        return _CacheMiss("extractor_mismatch")
    if payload.get("result_schema_fingerprint") != fps.result_schema:
        return _CacheMiss("result_schema_mismatch")
    if payload.get("validator_fingerprint") != fps.validator:
        return _CacheMiss("validator_mismatch")

    try:
        current_hash = _image_content_hash(image)
    except OSError:
        return _CacheMiss("source_mismatch")
    if payload.get("source_sha256") != current_hash:
        return _CacheMiss("source_mismatch")

    result = {
        "matched_types": payload.get("matched_types"),
        "unmatched_types": payload.get("unmatched_types"),
    }
    try:
        validate_extract_result(result, schema)
    except TypeError, ValueError:
        return _CacheMiss("invalid_shape")
    return result


def _save_extract_cache(
    image: Path,
    fps: _ExtractFingerprints,
    result: dict,
    output_dir: Path,
    *,
    cache_version: str | None = None,
) -> None:
    """C1: 抽出結果 + 多層 fingerprint をキャッシュ JSON として永続化する。"""
    cache_path = _extract_cache_path(image, output_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        relpath = str(image.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        relpath = str(image)
    payload = {
        "cache_version": CACHE_VERSION if cache_version is None else cache_version,
        "schema_hash": fps.schema,
        "prompt_fingerprint": fps.prompt,
        "model": fps.model,
        "extractor_id": fps.extractor_id,
        "result_schema_fingerprint": fps.result_schema,
        "validator_fingerprint": fps.validator,
        "source_file": image.name,
        "source_relpath": relpath,
        "source_sha256": _image_content_hash(image),
        "matched_types": result.get("matched_types", []),
        "unmatched_types": result.get("unmatched_types", []),
    }
    _atomic_write_text(cache_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
