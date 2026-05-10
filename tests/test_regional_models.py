"""regional_ocr.models / regional_ocr.errors のユニットテスト（AC-1〜AC-10, AC-36, AC-37）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nova_parser.regional_ocr.errors import (
    AdcNotConfiguredError,
    ImageNotFoundError,
    ImagePathTraversalError,
    OcrBackendError,
    RegionalOcrError,
    RegionNotFoundError,
    StemCollisionError,
)
from nova_parser.regional_ocr.models import (
    ImageSession,
    Rectangle,
    RegionRecord,
)

# ---------------------------------------------------------------------------
# ヘルパー fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_rect() -> Rectangle:
    """有効な Rectangle を返す共通 fixture。"""
    return Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=100, height=200)


@pytest.fixture
def make_region_record(valid_rect):
    """デフォルト値を持つ RegionRecord を生成するファクトリ fixture。"""

    def _make(**kwargs) -> RegionRecord:
        defaults = {
            "rectangle": valid_rect,
            "text": None,
            "ocr_status": "pending",
        }
        defaults.update(kwargs)
        return RegionRecord(**defaults)

    return _make


# ---------------------------------------------------------------------------
# AC-1: Rectangle の正常構築と property 確認
# ---------------------------------------------------------------------------


def test_rectangle_builds_successfully_and_properties_correct():
    """AC-1: Rectangle を rect_id='r1', draw_order=0, x=0, y=0, width=100, height=200 で構築したとき、
    ValidationError が発生せず、left=0, top=0, right=100, bottom=200 が property から得られる。
    """
    rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=100, height=200)
    assert rect.left == 0
    assert rect.top == 0
    assert rect.right == 100
    assert rect.bottom == 200


# ---------------------------------------------------------------------------
# AC-2: width=0 で ValidationError
# ---------------------------------------------------------------------------


def test_rectangle_raises_validation_error_when_width_is_zero():
    """AC-2: Rectangle を width=0 で構築しようとしたとき、pydantic.ValidationError が raise される。"""
    with pytest.raises(ValidationError):
        Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=0, height=100)


# ---------------------------------------------------------------------------
# AC-3: height=-1 で ValidationError
# ---------------------------------------------------------------------------


def test_rectangle_raises_validation_error_when_height_is_negative():
    """AC-3: Rectangle を height=-1 で構築しようとしたとき、pydantic.ValidationError が raise される。"""
    with pytest.raises(ValidationError):
        Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=100, height=-1)


# ---------------------------------------------------------------------------
# AC-4: x=-1 で ValidationError
# ---------------------------------------------------------------------------


def test_rectangle_raises_validation_error_when_x_is_negative():
    """AC-4: Rectangle を x=-1 で構築しようとしたとき、pydantic.ValidationError が raise される。"""
    with pytest.raises(ValidationError):
        Rectangle(rect_id="r1", draw_order=0, x=-1, y=0, width=100, height=100)


# ---------------------------------------------------------------------------
# AC-5: rect_id='' で ValidationError
# ---------------------------------------------------------------------------


def test_rectangle_raises_validation_error_when_rect_id_is_empty():
    """AC-5: Rectangle を rect_id='' (空文字列) で構築しようとしたとき、pydantic.ValidationError が raise される。"""
    with pytest.raises(ValidationError):
        Rectangle(rect_id="", draw_order=0, x=0, y=0, width=100, height=100)


# ---------------------------------------------------------------------------
# AC-6: draw_order=-1 で ValidationError
# ---------------------------------------------------------------------------


def test_rectangle_raises_validation_error_when_draw_order_is_negative():
    """AC-6: Rectangle を draw_order=-1 で構築しようとしたとき、pydantic.ValidationError が raise される。"""
    with pytest.raises(ValidationError):
        Rectangle(rect_id="r1", draw_order=-1, x=0, y=0, width=100, height=100)


# ---------------------------------------------------------------------------
# AC-7: RegionRecord の正常構築
# ---------------------------------------------------------------------------


def test_region_record_builds_successfully_with_defaults(valid_rect):
    """AC-7: RegionRecord を rectangle=valid_rect, text=None, ocr_status='pending' で構築したとき、
    ValidationError が発生せず、ocr_completed_at=None, ocr_error=None となる。
    """
    record = RegionRecord(rectangle=valid_rect, text=None, ocr_status="pending")
    assert record.ocr_completed_at is None
    assert record.ocr_error is None


# ---------------------------------------------------------------------------
# AC-8: rect_id 重複で ImageSession が ValidationError
# ---------------------------------------------------------------------------


def test_image_session_raises_validation_error_on_duplicate_rect_id():
    """AC-8: ImageSession に rect_id が重複する RegionRecord を 2 件含めて構築しようとしたとき、
    pydantic.ValidationError が raise される。
    """
    rect1 = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=100, height=100)
    rect2 = Rectangle(rect_id="r1", draw_order=1, x=10, y=10, width=100, height=100)
    record1 = RegionRecord(rectangle=rect1, text=None, ocr_status="pending")
    record2 = RegionRecord(rectangle=rect2, text=None, ocr_status="pending")
    with pytest.raises(ValidationError):
        ImageSession(
            image_name="test.png",
            image_width=1000,
            image_height=800,
            regions=[record1, record2],
        )


# ---------------------------------------------------------------------------
# AC-9: draw_order 重複で ImageSession が ValidationError
# ---------------------------------------------------------------------------


def test_image_session_raises_validation_error_on_duplicate_draw_order():
    """AC-9: ImageSession に draw_order が重複する RegionRecord を 2 件含めて構築しようとしたとき、
    pydantic.ValidationError が raise される。
    """
    rect1 = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=100, height=100)
    rect2 = Rectangle(rect_id="r2", draw_order=0, x=10, y=10, width=100, height=100)
    record1 = RegionRecord(rectangle=rect1, text=None, ocr_status="pending")
    record2 = RegionRecord(rectangle=rect2, text=None, ocr_status="pending")
    with pytest.raises(ValidationError):
        ImageSession(
            image_name="test.png",
            image_width=1000,
            image_height=800,
            regions=[record1, record2],
        )


# ---------------------------------------------------------------------------
# AC-10: ImageSession を regions=[] で構築
# ---------------------------------------------------------------------------


def test_image_session_builds_successfully_with_empty_regions():
    """AC-10: ImageSession を regions=[] で構築したとき、ValidationError が発生せず、schema_version=1 となる。"""
    session = ImageSession(image_name="test.png", image_width=1000, image_height=800)
    assert session.regions == []
    assert session.schema_version == 1


# ---------------------------------------------------------------------------
# AC-36: 例外クラス継承ツリー確認
# ---------------------------------------------------------------------------


def test_error_class_hierarchy_regional_ocr_error_is_exception():
    """AC-36: RegionalOcrError が Exception のサブクラスであり、
    ImageNotFoundError / RegionNotFoundError / ImagePathTraversalError /
    OcrBackendError / StemCollisionError が RegionalOcrError のサブクラスである。
    """
    assert issubclass(RegionalOcrError, Exception)
    assert issubclass(ImageNotFoundError, RegionalOcrError)
    assert issubclass(RegionNotFoundError, RegionalOcrError)
    assert issubclass(ImagePathTraversalError, RegionalOcrError)
    assert issubclass(OcrBackendError, RegionalOcrError)
    assert issubclass(StemCollisionError, RegionalOcrError)


# ---------------------------------------------------------------------------
# AC-37: AdcNotConfiguredError は OcrBackendError のサブクラス
# ---------------------------------------------------------------------------


def test_error_class_hierarchy_adc_not_configured_error_is_ocr_backend_error():
    """AC-37: AdcNotConfiguredError が OcrBackendError のサブクラスである。"""
    assert issubclass(AdcNotConfiguredError, OcrBackendError)
