"""regional_ocr.errors の例外クラス階層テスト。"""

from __future__ import annotations

import pytest

from nova_parser.regional_ocr.errors import (
    AdcNotConfiguredError,
    ImageNotFoundError,
    ImagePathTraversalError,
    OcrBackendError,
    RegionalOcrError,
    RegionNotFoundError,
    StemCollisionError,
)

# ---------------------------------------------------------------------------
# クラス一覧（テストの parametrize で共有）
# ---------------------------------------------------------------------------

ALL_ERRORS: dict[str, type[Exception]] = {
    "RegionalOcrError": RegionalOcrError,
    "ImageNotFoundError": ImageNotFoundError,
    "RegionNotFoundError": RegionNotFoundError,
    "ImagePathTraversalError": ImagePathTraversalError,
    "OcrBackendError": OcrBackendError,
    "StemCollisionError": StemCollisionError,
    "AdcNotConfiguredError": AdcNotConfiguredError,
}

SUBCLASSES_OF_REGIONAL_OCR_ERROR: dict[str, type[RegionalOcrError]] = {
    name: cls for name, cls in ALL_ERRORS.items() if cls is not RegionalOcrError
}


# ---------------------------------------------------------------------------
# 継承関係
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", list(ALL_ERRORS.values()), ids=list(ALL_ERRORS.keys()))
def test_all_errors_inherit_exception(cls: type) -> None:
    """全例外クラスが Exception を継承している。"""
    assert issubclass(cls, Exception)


@pytest.mark.parametrize(
    "cls",
    list(SUBCLASSES_OF_REGIONAL_OCR_ERROR.values()),
    ids=list(SUBCLASSES_OF_REGIONAL_OCR_ERROR.keys()),
)
def test_all_subclasses_inherit_regional_ocr_error(cls: type) -> None:
    """RegionalOcrError 以外の例外クラスが RegionalOcrError を継承している。"""
    assert issubclass(cls, RegionalOcrError)


def test_adc_not_configured_inherits_ocr_backend_error() -> None:
    """AdcNotConfiguredError は OcrBackendError を継承している。"""
    assert issubclass(AdcNotConfiguredError, OcrBackendError)


def test_stem_collision_does_not_inherit_ocr_backend_error() -> None:
    """StemCollisionError は OcrBackendError を継承しない（docstring の意図通り）。"""
    assert not issubclass(StemCollisionError, OcrBackendError)


# ---------------------------------------------------------------------------
# raise / except での捕捉
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    list(SUBCLASSES_OF_REGIONAL_OCR_ERROR.values()),
    ids=list(SUBCLASSES_OF_REGIONAL_OCR_ERROR.keys()),
)
def test_subclasses_caught_by_base_regional_ocr_error(cls: type[RegionalOcrError]) -> None:
    """サブクラスを raise したとき RegionalOcrError でキャッチできる。"""
    with pytest.raises(RegionalOcrError):
        raise cls("boom")


def test_adc_not_configured_caught_by_ocr_backend_error() -> None:
    """AdcNotConfiguredError を raise したとき OcrBackendError でキャッチできる。"""
    with pytest.raises(OcrBackendError):
        raise AdcNotConfiguredError("ADC missing")


# ---------------------------------------------------------------------------
# メッセージ伝搬
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cls", "message"),
    [
        (ImageNotFoundError, "foo.png not found"),
        (RegionNotFoundError, "region 'r1' not found"),
        (ImagePathTraversalError, "path traversal detected"),
        (StemCollisionError, "duplicate stems: foo"),
        (AdcNotConfiguredError, "ADC missing"),
    ],
    ids=[
        "ImageNotFoundError",
        "RegionNotFoundError",
        "ImagePathTraversalError",
        "StemCollisionError",
        "AdcNotConfiguredError",
    ],
)
def test_error_preserves_message_argument(cls: type[Exception], message: str) -> None:
    """コンストラクタ引数のメッセージが str(e) に保持される。"""
    err = cls(message)
    assert str(err) == message


# ---------------------------------------------------------------------------
# Docstring 存在
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", list(ALL_ERRORS.values()), ids=list(ALL_ERRORS.keys()))
def test_all_errors_have_docstring(cls: type) -> None:
    """全例外クラスに非空の __doc__ が定義されている。"""
    assert cls.__doc__ is not None
    assert cls.__doc__.strip()
