"""regional_ocr.images のユニットテスト（AC-27〜AC-35, AC-40）。"""

from __future__ import annotations

import pytest
from PIL import Image

from nova_parser.regional_ocr.errors import ImageNotFoundError, ImagePathTraversalError
from nova_parser.regional_ocr.images import (
    IMAGE_MIME_TYPES,
    list_images,
    open_pil,
    resolve_image,
)

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _create_image_file(path, mode: str = "RGB", size: tuple[int, int] = (10, 10)) -> None:
    """テスト用の画像ファイルを保存するヘルパー。"""
    img = Image.new(mode, size, color=(100, 100, 100))
    img.save(path)


# ---------------------------------------------------------------------------
# AC-27: IMAGE_MIME_TYPES に '.pdf' キーが含まれない
# ---------------------------------------------------------------------------


def test_image_mime_types_does_not_contain_pdf_key():
    """AC-27: IMAGE_MIME_TYPES に '.pdf' キーが含まれない。"""
    assert ".pdf" not in IMAGE_MIME_TYPES


# ---------------------------------------------------------------------------
# AC-28: IMAGE_MIME_TYPES に '.png', '.jpg', '.jpeg', '.webp' が含まれる
# ---------------------------------------------------------------------------


def test_image_mime_types_contains_required_extensions():
    """AC-28: IMAGE_MIME_TYPES に '.png', '.jpg', '.jpeg', '.webp' がすべて含まれる。"""
    assert ".png" in IMAGE_MIME_TYPES
    assert ".jpg" in IMAGE_MIME_TYPES
    assert ".jpeg" in IMAGE_MIME_TYPES
    assert ".webp" in IMAGE_MIME_TYPES


# ---------------------------------------------------------------------------
# AC-29: list_images が regions.json と regions.md を除外する
# ---------------------------------------------------------------------------


def test_list_images_excludes_regions_json_and_regions_md(tmp_path):
    """AC-29: list_images を、PNG・WEBP ファイルが複数存在し regions.json と regions.md が混在する
    ディレクトリで呼び出したとき、返却 ImageListResponse の images に regions.json と
    regions.md が含まれない。
    """
    # 画像ファイルを作成
    _create_image_file(tmp_path / "photo1.png")
    _create_image_file(tmp_path / "photo2.webp")
    # 除外されるべきファイルを作成
    (tmp_path / "photo1.regions.json").write_text("{}", encoding="utf-8")
    (tmp_path / "photo1.regions.md").write_text("# test", encoding="utf-8")

    response = list_images(tmp_path)

    image_names = response.images
    assert "photo1.regions.json" not in image_names
    assert "photo1.regions.md" not in image_names
    # 画像ファイルは含まれる
    assert "photo1.png" in image_names
    assert "photo2.webp" in image_names


# ---------------------------------------------------------------------------
# AC-30: list_images がステム衝突時に warnings に 'stem collision: ' を含む文字列を返す
# ---------------------------------------------------------------------------


def test_list_images_warns_on_stem_collision(tmp_path):
    """AC-30: list_images を、'foo.png' と 'foo.webp' が同一ディレクトリに存在するディレクトリで
    呼び出したとき、ImageListResponse.warnings に 'stem collision: ' を含む文字列が 1 件以上存在し、
    例外は raise されない。
    """
    _create_image_file(tmp_path / "foo.png")
    _create_image_file(tmp_path / "foo.webp")

    response = list_images(tmp_path)

    assert any("stem collision: " in w for w in response.warnings)


# ---------------------------------------------------------------------------
# AC-31: resolve_image に '../etc/passwd' を渡すと ImagePathTraversalError
# ---------------------------------------------------------------------------


def test_resolve_image_raises_traversal_error_on_relative_path_escape(tmp_path):
    """AC-31: resolve_image に name='../etc/passwd' を渡したとき、ImagePathTraversalError が raise される。"""
    with pytest.raises(ImagePathTraversalError):
        resolve_image(tmp_path, "../etc/passwd")


# ---------------------------------------------------------------------------
# AC-32: resolve_image に絶対パスを渡すと ImagePathTraversalError
# ---------------------------------------------------------------------------


def test_resolve_image_raises_traversal_error_on_absolute_path(tmp_path):
    """AC-32: resolve_image に name='/etc/passwd' （絶対パス）を渡したとき、
    ImagePathTraversalError が raise される。
    """
    with pytest.raises(ImagePathTraversalError):
        resolve_image(tmp_path, "/etc/passwd")


# ---------------------------------------------------------------------------
# AC-33: resolve_image に存在しないファイル名を渡すと ImageNotFoundError
# ---------------------------------------------------------------------------


def test_resolve_image_raises_not_found_error_for_nonexistent_file(tmp_path):
    """AC-33: resolve_image に存在しないファイル名（traversal なし）を渡したとき、
    ImageNotFoundError が raise される。
    """
    with pytest.raises(ImageNotFoundError):
        resolve_image(tmp_path, "nonexistent.png")


# ---------------------------------------------------------------------------
# AC-34: resolve_image が正常なファイル名で絶対 Path を返す
# ---------------------------------------------------------------------------


def test_resolve_image_returns_absolute_path_for_existing_file(tmp_path):
    """AC-34: resolve_image に image_dir 直下に存在するファイル名を渡したとき、
    ValidationError も例外も発生せず、image_dir 配下の絶対 Path が返却される。
    """
    _create_image_file(tmp_path / "test.png")
    result = resolve_image(tmp_path, "test.png")
    assert result.is_absolute()
    assert result == tmp_path / "test.png"


# ---------------------------------------------------------------------------
# AC-35: open_pil が RGBA を RGB に変換する
# ---------------------------------------------------------------------------


def test_open_pil_converts_rgba_to_rgb(tmp_path):
    """AC-35: open_pil で RGBA モードの PNG を開いたとき、返却 Image の mode が 'RGB' となる。"""
    img_path = tmp_path / "rgba_image.png"
    _create_image_file(img_path, mode="RGBA")
    result = open_pil(img_path)
    assert result.mode == "RGB"


# ---------------------------------------------------------------------------
# AC-40: nova_parser.ocr の MIME_TYPES が変更されておらず、IMAGE_MIME_TYPES は regional_ocr.images からのみ
# ---------------------------------------------------------------------------


def test_existing_ocr_mime_types_is_unchanged_and_image_mime_types_is_independent():
    """AC-40: nova_parser.ocr の MIME_TYPES を import しても KeyError が発生せず、
    IMAGE_MIME_TYPES は nova_parser.regional_ocr.images からのみ import 可能で、
    既存の nova_parser.ocr.MIME_TYPES の内容が変更されていない。
    """
    import nova_parser.ocr as ocr_mod

    # 既存の MIME_TYPES が .pdf を含んでいることを確認（変更されていない）
    assert ".pdf" in ocr_mod.MIME_TYPES
    assert ocr_mod.MIME_TYPES[".pdf"] == "application/pdf"

    # IMAGE_MIME_TYPES は nova_parser.regional_ocr.images からのみ import 可能（.pdf を含まない）
    assert ".pdf" not in IMAGE_MIME_TYPES

    # 両者が独立した辞書であること
    assert ocr_mod.MIME_TYPES is not IMAGE_MIME_TYPES
