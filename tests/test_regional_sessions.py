"""regional_ocr.sessions のユニットテスト（AC-21〜AC-26, AC-41, AC-43〜AC-46）。"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
from nova_parser.regional_ocr.sessions import (
    load_session,
    save_session,
    session_path,
    upsert_region,
)

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_rect(rect_id: str, draw_order: int) -> Rectangle:
    """テスト用の Rectangle を生成するヘルパー。"""
    return Rectangle(rect_id=rect_id, draw_order=draw_order, x=0, y=0, width=100, height=100)


def _make_record(rect_id: str, draw_order: int, text: str | None = None) -> RegionRecord:
    """テスト用の RegionRecord を生成するヘルパー。"""
    return RegionRecord(rectangle=_make_rect(rect_id, draw_order), text=text, ocr_status="pending")


def _make_session(records: list[RegionRecord] | None = None) -> ImageSession:
    """テスト用の ImageSession を生成するヘルパー。"""
    return ImageSession(
        image_name="test.png",
        image_width=1000,
        image_height=800,
        regions=records or [],
    )


# ---------------------------------------------------------------------------
# AC-21: session_path の返却値確認
# ---------------------------------------------------------------------------


def test_session_path_returns_correct_path(tmp_path):
    """AC-21: session_path(output_dir, 'foo') の返却値が output_dir / 'foo.regions.json' と等しい。"""
    result = session_path(tmp_path, "foo")
    assert result == tmp_path / "foo.regions.json"


# ---------------------------------------------------------------------------
# AC-22: 対応する regions.json が存在しない場合、空の ImageSession を返す
# ---------------------------------------------------------------------------


def test_load_session_returns_empty_session_when_file_not_found(tmp_path):
    """AC-22: load_session を、対応する regions.json が存在しない output_dir と image_name で呼び出したとき、
    regions=[] の ImageSession が返却され、例外が raise されない。
    """
    session = load_session(tmp_path, "nonexistent", image_width=800, image_height=600)
    assert session.regions == []
    assert isinstance(session, ImageSession)


# ---------------------------------------------------------------------------
# AC-23: save_session → load_session のラウンドトリップ整合性
# ---------------------------------------------------------------------------


def test_save_and_load_session_roundtrip_consistency(tmp_path):
    """AC-23: save_session で保存した JSON ファイルを load_session で読み直したとき、
    元の ImageSession と等価なオブジェクトが復元される（ラウンドトリップ整合性）。
    load_session には session.image_name をそのまま渡す（"test.png"）。
    """
    records = [_make_record("r1", 0, "hello")]
    original = _make_session(records)
    # original.image_name == "test.png"
    save_session(original, tmp_path)
    restored = load_session(tmp_path, original.image_name, image_width=1000, image_height=800)
    assert restored.image_name == original.image_name  # "test.png" で等値復元
    assert restored.image_width == original.image_width
    assert restored.image_height == original.image_height
    assert len(restored.regions) == len(original.regions)
    assert restored.regions[0].rectangle.rect_id == original.regions[0].rectangle.rect_id
    assert restored.regions[0].text == original.regions[0].text


# ---------------------------------------------------------------------------
# AC-24: save_session が日本語テキストを Unicode エスケープしない
# ---------------------------------------------------------------------------


def test_save_session_stores_japanese_text_without_unicode_escape(tmp_path):
    """AC-24: save_session で保存した JSON ファイルを直接読み込んだとき、
    日本語テキストが Unicode エスケープ（\\uXXXX）されずに UTF-8 文字として格納されている。
    """
    records = [_make_record("r1", 0, "日本語テキスト")]
    session = _make_session(records)
    save_session(session, tmp_path)
    path = session_path(tmp_path, session.image_name)
    raw_content = path.read_text(encoding="utf-8")
    # Unicode エスケープされていないことを確認（\\u3042 等が含まれない）
    assert "\\u" not in raw_content
    assert "日本語テキスト" in raw_content


# ---------------------------------------------------------------------------
# AC-25: upsert_region が新規 rect_id の場合 regions 末尾に追加（pure 関数）
# ---------------------------------------------------------------------------


def test_upsert_region_appends_new_record_and_is_pure():
    """AC-25: upsert_region で存在しない rect_id を持つ RegionRecord を渡したとき、
    返却 ImageSession の regions 末尾に該当 RegionRecord が追加されており、
    元の ImageSession の regions は変更されていない（pure 関数）。
    """
    original = _make_session([_make_record("r1", 0)])
    original_regions_count = len(original.regions)
    new_record = _make_record("r2", 1, "new text")

    updated = upsert_region(original, new_record)

    # 元のセッションは変更されていない
    assert len(original.regions) == original_regions_count

    # 新しいセッションには追加されている
    assert len(updated.regions) == original_regions_count + 1
    assert updated.regions[-1].rectangle.rect_id == "r2"
    assert updated.regions[-1].text == "new text"


# ---------------------------------------------------------------------------
# AC-26: upsert_region が既存 rect_id の場合は置換・リスト長は変わらない
# ---------------------------------------------------------------------------


def test_upsert_region_replaces_existing_record_at_same_index():
    """AC-26: upsert_region で既存の rect_id と一致する RegionRecord を渡したとき、
    返却 ImageSession の同インデックス位置の RegionRecord が新しいものに置換されており、
    リストの長さは変わらない。
    """
    original_record = _make_record("r1", 0, "old text")
    original = _make_session([original_record])

    # draw_order は rect_id が違う場合の一意性チェックのため、既存と同じにする
    replacement = RegionRecord(
        rectangle=_make_rect("r1", 0),
        text="updated text",
        ocr_status="done",
    )
    updated = upsert_region(original, replacement)

    assert len(updated.regions) == len(original.regions)
    assert updated.regions[0].text == "updated text"
    assert updated.regions[0].ocr_status == "done"


# ---------------------------------------------------------------------------
# AC-41: save_session の atomic 書き込み確認
# ---------------------------------------------------------------------------


def test_save_session_atomic_write_file_is_readable_after_completion(tmp_path):
    """AC-41: save_session が書き込みを行う際、最終ファイルへの rename 前に一時ファイルを経由する
    atomic 書き込みが行われる。テストでは tmp_path を output_dir として save_session を呼び出し、
    完了後に session_path のファイルが読み取れることで検証する。
    """
    records = [_make_record("r1", 0, "atomic")]
    session = _make_session(records)
    save_session(session, tmp_path)

    path = session_path(tmp_path, session.image_name)
    # 完了後にファイルが存在し、読み取り可能であることを確認
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "image_name" in data


# ---------------------------------------------------------------------------
# AC-43: 拡張子付き image_name でのラウンドトリップ整合性
# ---------------------------------------------------------------------------


def test_save_and_load_session_roundtrip_with_extension_in_image_name(tmp_path):
    """AC-43: ImageSession(image_name='photo.png', ...) を save_session で保存し、
    load_session(output_dir, 'photo.png', ...) で復元したとき、
    restored.image_name == 'photo.png' で等値復元され、
    session_path(output_dir, 'photo.png') のファイルが exists() する。
    """
    session = ImageSession(image_name="photo.png", image_width=800, image_height=600, regions=[])
    save_session(session, tmp_path)

    # session_path(tmp_path, 'photo.png') のファイルが存在すること
    expected_path = session_path(tmp_path, "photo.png")
    assert expected_path.exists()

    # load_session に 'photo.png' を渡して復元できること
    restored = load_session(tmp_path, "photo.png", image_width=800, image_height=600)
    assert restored.image_name == "photo.png"


# ---------------------------------------------------------------------------
# AC-44: session_path は拡張子付き・なし両方で同一 Path を返す
# ---------------------------------------------------------------------------


def test_session_path_with_extension_equals_without_extension(tmp_path):
    """AC-44: session_path(tmp_path, 'photo.png') と session_path(tmp_path, 'photo') が
    同一の Path（tmp_path / 'photo.regions.json'）を返す。
    """
    with_ext = session_path(tmp_path, "photo.png")
    without_ext = session_path(tmp_path, "photo")
    expected = tmp_path / "photo.regions.json"
    assert with_ext == expected
    assert without_ext == expected
    assert with_ext == without_ext


# ---------------------------------------------------------------------------
# AC-45: upsert_region で draw_order 重複時に pydantic.ValidationError が raise される
# ---------------------------------------------------------------------------


def test_upsert_region_raises_validation_error_on_draw_order_conflict():
    """AC-45: 既存 regions に Rectangle(rect_id='r1', draw_order=0, ...) を含む RegionRecord がある
    ImageSession に対して、Rectangle(rect_id='r2', draw_order=0, ...) を含む新 RegionRecord を
    upsert_region に渡したとき、pydantic.ValidationError が raise される。
    """
    existing_record = _make_record("r1", draw_order=0)
    session = _make_session([existing_record])

    # rect_id は異なるが draw_order が既存（0）と重複する新規レコード
    conflicting_record = _make_record("r2", draw_order=0)

    with pytest.raises(ValidationError):
        upsert_region(session, conflicting_record)


# ---------------------------------------------------------------------------
# AC-46: save_session 完了後に .tmp ファイルが残存しない
# ---------------------------------------------------------------------------


def test_save_session_no_tmp_file_remains_after_completion(tmp_path):
    """AC-46: save_session 完了後に tmp_path 配下に '*.tmp' サフィックスのファイルが残存しない
    （cleanup 確認）。
    """
    session = _make_session([_make_record("r1", 0, "cleanup_test")])
    save_session(session, tmp_path)

    remaining_tmp_files = list(tmp_path.glob("*.tmp"))
    assert remaining_tmp_files == []
