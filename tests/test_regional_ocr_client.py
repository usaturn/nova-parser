"""regional_ocr.ocr_client のユニットテスト（AC-B-04〜AC-B-12）。"""

from __future__ import annotations

import pytest
from PIL import Image

# FakeVisionClient / _FakeResponse は tests/conftest.py から共有（AC-C-26）
from tests.conftest import FakeVisionClient, _FakeResponse

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_rect(*, x: int = 0, y: int = 0, width: int = 50, height: int = 50, rect_id: str = "r1"):
    """Rectangle を生成するヘルパー（regional_ocr.models に依存）。"""
    from nova_parser.regional_ocr.models import Rectangle  # type: ignore[import]

    return Rectangle(rect_id=rect_id, draw_order=0, x=x, y=y, width=width, height=height)


def _make_image(width: int = 100, height: int = 100, mode: str = "RGB") -> Image.Image:
    """テスト用のメモリ上画像を生成するヘルパー。"""
    return Image.new(mode, (width, height), color=(128, 128, 128))


# ---------------------------------------------------------------------------
# AC-B-04: build_vision_client() - DefaultCredentialsError → AdcNotConfiguredError
# ---------------------------------------------------------------------------


def test_build_vision_client_raises_adc_not_configured_error_when_credentials_missing(monkeypatch):
    """AC-B-04: build_vision_client() を、vision.ImageAnnotatorClient() が
    google.auth.exceptions.DefaultCredentialsError を raise するよう monkeypatch した状態で
    呼び出したとき、AdcNotConfiguredError が raise される。

    google.cloud.vision が未インストールの場合は ocr_client 自体の import エラーで red になる。
    """
    import google.auth.exceptions  # type: ignore[import]

    from nova_parser.regional_ocr.errors import AdcNotConfiguredError  # type: ignore[import]
    from nova_parser.regional_ocr.ocr_client import build_vision_client  # type: ignore[import]

    def _raise_credentials_error():
        raise google.auth.exceptions.DefaultCredentialsError("ADC not set")

    # ocr_client が内部で `from google.cloud import vision` を行うため、
    # そのモジュール内の `vision.ImageAnnotatorClient` を差し替える
    monkeypatch.setattr(
        "nova_parser.regional_ocr.ocr_client.vision.ImageAnnotatorClient",
        _raise_credentials_error,
    )

    with pytest.raises(AdcNotConfiguredError):
        build_vision_client()


# ---------------------------------------------------------------------------
# AC-B-05: build_vision_client() - 正常時は FakeVisionClient インスタンスを返す
# ---------------------------------------------------------------------------


def test_build_vision_client_returns_client_instance_without_exception(monkeypatch):
    """AC-B-05: build_vision_client() を、vision.ImageAnnotatorClient が
    FakeVisionClient インスタンスを返すよう monkeypatch した状態で呼び出したとき、
    例外が発生せず FakeVisionClient インスタンスが返される。

    google.cloud.vision が未インストールの場合は ocr_client 自体の import エラーで red になる。
    """
    from nova_parser.regional_ocr.ocr_client import build_vision_client  # type: ignore[import]

    fake_client = FakeVisionClient(_FakeResponse(text="ok"))

    monkeypatch.setattr(
        "nova_parser.regional_ocr.ocr_client.vision.ImageAnnotatorClient",
        lambda: fake_client,
    )

    result = build_vision_client()
    assert result is fake_client


# ---------------------------------------------------------------------------
# AC-B-06: ocr_rectangle() - 正常系：FakeVisionClient が text を返す
# ---------------------------------------------------------------------------


def test_ocr_rectangle_returns_text_from_vision_response():
    """AC-B-06: ocr_rectangle(client, image, rect) を、FakeVisionClient が
    _FakeResponse(text='OCR結果') を返す状態で呼び出したとき、
    戻り値が 'OCR結果' と等しい str となる。
    """
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle  # type: ignore[import]

    client = FakeVisionClient(_FakeResponse(text="OCR結果"))
    image = _make_image()
    rect = _make_rect()

    result = ocr_rectangle(client, image, rect)
    assert result == "OCR結果"


# ---------------------------------------------------------------------------
# AC-B-07: ocr_rectangle() - error_message 非空 → OcrBackendError
# ---------------------------------------------------------------------------


def test_ocr_rectangle_raises_ocr_backend_error_when_vision_returns_error():
    """AC-B-07: ocr_rectangle(client, image, rect) を、FakeVisionClient が
    _FakeResponse(error_message='backend error') を返す状態で呼び出したとき、
    OcrBackendError が raise される。
    """
    from nova_parser.regional_ocr.errors import OcrBackendError  # type: ignore[import]
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle  # type: ignore[import]

    client = FakeVisionClient(_FakeResponse(error_message="backend error"))
    image = _make_image()
    rect = _make_rect()

    with pytest.raises(OcrBackendError):
        ocr_rectangle(client, image, rect)


# ---------------------------------------------------------------------------
# AC-B-08: ocr_rectangle() - デフォルト language_hints が ['ja']
# ---------------------------------------------------------------------------


def test_ocr_rectangle_default_language_hints_is_ja():
    """AC-B-08: ocr_rectangle(client, image, rect) をデフォルト引数（language_hints 未指定）で
    呼び出したとき、FakeVisionClient の calls[0]['image_context'].language_hints が ['ja'] と等しい。
    """
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle  # type: ignore[import]

    client = FakeVisionClient(_FakeResponse(text="text"))
    image = _make_image()
    rect = _make_rect()

    ocr_rectangle(client, image, rect)

    assert client.calls[0]["image_context"].language_hints == ["ja"]


# ---------------------------------------------------------------------------
# AC-B-09: ocr_rectangle() - language_hints=('en', 'ja') が正しく伝わる
# ---------------------------------------------------------------------------


def test_ocr_rectangle_custom_language_hints_propagated_to_vision_client():
    """AC-B-09: ocr_rectangle(client, image, rect, language_hints=('en', 'ja')) で呼び出したとき、
    FakeVisionClient の calls[0]['image_context'].language_hints が ['en', 'ja'] と等しい。
    """
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle  # type: ignore[import]

    client = FakeVisionClient(_FakeResponse(text="text"))
    image = _make_image()
    rect = _make_rect()

    ocr_rectangle(client, image, rect, language_hints=("en", "ja"))

    assert client.calls[0]["image_context"].language_hints == ["en", "ja"]


# ---------------------------------------------------------------------------
# AC-B-10: ocr_rectangle() - PNG シグネチャ確認
# ---------------------------------------------------------------------------


def test_ocr_rectangle_passes_png_bytes_to_vision_client():
    """AC-B-10: ocr_rectangle(client, image, rect) を呼び出したとき、
    FakeVisionClient の calls[0]['image'].content の先頭 8 バイトが
    PNG シグネチャ (b'\\x89PNG\\r\\n\\x1a\\n') と一致する。
    """
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle  # type: ignore[import]

    client = FakeVisionClient(_FakeResponse(text="text"))
    image = _make_image()
    rect = _make_rect()

    ocr_rectangle(client, image, rect)

    png_signature = b"\x89PNG\r\n\x1a\n"
    assert client.calls[0]["image"].content[:8] == png_signature


# ---------------------------------------------------------------------------
# AC-B-11: ocr_rectangle() - 面積ゼロの rect → ValueError（OcrBackendError ではない）
# ---------------------------------------------------------------------------


def test_ocr_rectangle_raises_value_error_for_zero_area_rect_after_clamp():
    """AC-B-11: ocr_rectangle(client, image, rect) を、クランプ後に面積ゼロになる rect
    （例: x=image.width, y=0, width=10, height=10）で呼び出したとき、
    ValueError が raise される（OcrBackendError でない）。
    """
    from nova_parser.regional_ocr.errors import OcrBackendError  # type: ignore[import]
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle  # type: ignore[import]

    client = FakeVisionClient(_FakeResponse(text="text"))
    image = _make_image(width=100, height=100)
    # x=image.width=100 なのでクランプ後 width=0 → 面積ゼロ
    rect = _make_rect(x=100, y=0, width=10, height=10)

    with pytest.raises(ValueError) as exc_info:
        ocr_rectangle(client, image, rect)

    # OcrBackendError ではないことを確認
    assert not isinstance(exc_info.value, OcrBackendError)


# ---------------------------------------------------------------------------
# AC-B-12: ocr_rectangle() - text='' のとき戻り値は '' であり None ではない
# ---------------------------------------------------------------------------


def test_ocr_rectangle_returns_empty_string_not_none_when_text_is_empty():
    """AC-B-12: ocr_rectangle(client, image, rect) を、FakeVisionClient が
    _FakeResponse(text='') を返す状態で呼び出したとき、
    戻り値が '' （空文字列）であり None ではない。
    """
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle  # type: ignore[import]

    client = FakeVisionClient(_FakeResponse(text=""))
    image = _make_image()
    rect = _make_rect()

    result = ocr_rectangle(client, image, rect)
    assert result == ""
    assert result is not None
