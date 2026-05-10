"""ImageSession の保存・読み込み・更新ユーティリティ。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from nova_parser.regional_ocr.models import ImageSession, RegionRecord


def session_path(output_dir: Path, image_name: str) -> Path:
    """セッション JSON ファイルのパスを返す。image_name は拡張子付き・なし両方を受け付ける。"""
    return output_dir / f"{Path(image_name).stem}.regions.json"


def load_session(output_dir: Path, image_name: str, *, image_width: int, image_height: int) -> ImageSession:
    """セッション JSON が存在すれば復元し、なければ空の ImageSession を返す。"""
    path = session_path(output_dir, image_name)
    if not path.exists():
        return ImageSession(image_name=image_name, image_width=image_width, image_height=image_height, regions=[])
    return ImageSession.model_validate_json(path.read_text(encoding="utf-8"))


def save_session(session: ImageSession, output_dir: Path) -> None:
    """ImageSession を atomic 書き込みで JSON ファイルに保存する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    content = json.dumps(session.model_dump(mode="json"), indent=2, ensure_ascii=False)
    dest = session_path(output_dir, session.image_name)

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


def upsert_region(session: ImageSession, record: RegionRecord) -> ImageSession:
    """rect_id が一致するリージョンを置換し、なければ末尾に追加した新しい ImageSession を返す（pure 関数）。"""
    new_regions = list(session.regions)
    target_id = record.rectangle.rect_id
    for i, existing in enumerate(new_regions):
        if existing.rectangle.rect_id == target_id:
            new_regions[i] = record
            break
    else:
        new_regions.append(record)
    return ImageSession(
        **{
            **session.model_dump(mode="json", exclude={"regions"}),
            "regions": [r.model_dump(mode="json") for r in new_regions],
        }
    )
