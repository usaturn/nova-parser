"""画像ファイルの一覧取得・パス解決・読み込みユーティリティ。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from nova_parser.regional_ocr.errors import ImageNotFoundError, ImagePathTraversalError
from nova_parser.regional_ocr.models import ImageListResponse

IMAGE_MIME_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}


def list_images(image_dir: Path) -> ImageListResponse:
    """image_dir 直下の画像ファイル一覧を返す。ステム衝突がある場合は warnings に追加する。"""
    filtered = sorted(
        (p for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_MIME_TYPES),
        key=lambda p: p.name,
    )

    stem_map: dict[str, list[Path]] = {}
    for p in filtered:
        stem_map.setdefault(p.stem, []).append(p)

    warnings: list[str] = []
    for _stem, paths in stem_map.items():
        if len(paths) >= 2:
            names = ", ".join(p.name for p in sorted(paths, key=lambda x: x.name))
            warnings.append(f"stem collision: {names}")

    return ImageListResponse(images=[p.name for p in filtered], warnings=warnings)


def resolve_image(image_dir: Path, name: str) -> Path:
    """name を検証して image_dir 配下の絶対パスを返す。不正なパスは ImagePathTraversalError を raise する。"""
    if name.startswith("/") or Path(name).is_absolute():
        raise ImagePathTraversalError(f"絶対パスは使用できません: {name}")

    for segment in name.replace("\\", "/").split("/"):
        if segment == "..":
            raise ImagePathTraversalError(f"パストラバーサルが検出されました: {name}")

    candidate = (image_dir / name).resolve()
    if not candidate.is_relative_to(image_dir.resolve()):
        raise ImagePathTraversalError(f"パストラバーサルが検出されました: {name}")

    if not candidate.exists():
        raise ImageNotFoundError(f"画像ファイルが見つかりません: {name}")

    return candidate


def open_pil(path: Path) -> Image.Image:
    """画像ファイルを開き、RGBA モードの場合は RGB に変換して返す。"""
    image = Image.open(path)
    if image.mode == "RGBA":
        return image.convert("RGB")
    return image
