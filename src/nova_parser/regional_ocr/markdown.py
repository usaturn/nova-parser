"""ImageSession から Markdown テキストを生成・書き出すユーティリティ。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from nova_parser.regional_ocr.models import ImageSession


def render_markdown(session: ImageSession) -> str:
    """ocr_status が 'done' のリージョンのテキストを draw_order 昇順で結合して返す。"""
    done_records = [r for r in session.regions if r.ocr_status == "done"]
    done_records.sort(key=lambda r: r.rectangle.draw_order)
    texts = [r.text if r.text is not None else "" for r in done_records]
    return "\n\n---\n\n".join(texts)


def write_markdown(session: ImageSession, output_dir: Path, image_stem: str) -> Path:
    """Markdown テキストを atomic 書き込みでファイルに保存し、そのパスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    content = render_markdown(session)
    dest = output_dir / f"{image_stem}.regions.md"

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
    return dest
