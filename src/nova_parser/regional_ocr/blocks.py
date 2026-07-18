"""BlockDetectionResult の保存・読み込みユーティリティ。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from nova_parser.regional_ocr.models import BlockDetectionResult


def blocks_path(output_dir: Path, image_name: str) -> Path:
    """ブロックキャッシュ JSON のパスを返す。image_name は拡張子付き・なし両方を受け付ける。"""
    return output_dir / f"{Path(image_name).stem}.blocks.json"


def load_blocks(output_dir: Path, image_name: str) -> BlockDetectionResult | None:
    """キャッシュが存在し妥当なら復元して返す。欠損・破損・スキーマ不一致は None（キャッシュなし扱い）。"""
    path = blocks_path(output_dir, image_name)
    if not path.exists():
        return None
    try:
        return BlockDetectionResult.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        # pydantic ValidationError は ValueError のサブクラス。壊れたキャッシュは再検出で上書きする。
        return None


def save_blocks(result: BlockDetectionResult, output_dir: Path) -> None:
    """BlockDetectionResult を atomic 書き込みで JSON ファイルに保存する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    content = json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False)
    dest = blocks_path(output_dir, result.image_name)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=output_dir,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        tmp_path.replace(dest)
    finally:
        tmp_path.unlink(missing_ok=True)
