"""書籍マニフェストの読み込み。"""

from pathlib import Path

from nova_parser.semistructure.models import BookManifest


def load_manifest(path: Path) -> BookManifest:
    """JSONファイルを検証済みの書籍マニフェストとして読み込む。"""
    return BookManifest.model_validate_json(path.read_text(encoding="utf-8"))
