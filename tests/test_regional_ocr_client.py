"""regional_ocr.ocr_client のユニットテスト（AC-B-04〜AC-B-12）。"""

from __future__ import annotations

import pytest
from PIL import Image

# FakeVisionClient / _FakeResponse は tests/conftest.py から共有（AC-C-26）
from tests.conftest import FakeVisionClient, _FakeResponse

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_rect(
    *,
    x: int = 0,
    y: int = 0,
    width: int = 50,
    height: int = 50,
    rect_id: str = "r1",
    reading_order: str = "vision",
):
    """Rectangle を生成するヘルパー（regional_ocr.models に依存）。"""
    from nova_parser.regional_ocr.models import Rectangle  # type: ignore[import]

    return Rectangle(
        rect_id=rect_id,
        draw_order=0,
        x=x,
        y=y,
        width=width,
        height=height,
        reading_order=reading_order,
    )


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


def test_ocr_rectangle_orders_vertical_blocks_from_right_to_left():
    """縦ブロックでは Vision のブロック配列順でなく画像上の右から左へ読む。"""
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle

    def block(right: int, text: str) -> dict[str, object]:
        return {
            "vertices": [(right - 20, 0), (right, 0), (right, 100), (right - 20, 100)],
            "symbols": [(character, 0) for character in text],
        }

    response = _FakeResponse(
        text="怪異\n世界設定関連\n異世界\n侵蝕\n怪異本文\n異世界本文\n侵蝕本文",
        structured_blocks=[
            block(1051, "怪異"),
            block(1197, "世界設定関連"),
            block(656, "異世界"),
            block(371, "侵蝕"),
            block(990, "怪異本文"),
            block(593, "異世界本文"),
            block(310, "侵蝕本文"),
        ],
    )

    result = ocr_rectangle(
        FakeVisionClient(response),
        _make_image(),
        _make_rect(reading_order="vertical"),
    )

    assert result == "世界設定関連\n怪異\n怪異本文\n異世界\n異世界本文\n侵蝕\n侵蝕本文"


def test_ocr_rectangle_keeps_top_to_bottom_within_a_split_column():
    """同一列が上下 2 block に分割され、下段の右端が数 px 大きくても上→下を保つ。"""
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle

    response = _FakeResponse(
        text="Vision既定順",
        structured_blocks=[
            # 同一列（X 範囲がほぼ一致）。下段の右端だけ 2px 張り出している
            {
                "vertices": [(1021, 0), (1051, 0), (1051, 90), (1021, 90)],
                "symbols": [(character, 0) for character in "上段"],
            },
            {
                "vertices": [(1023, 100), (1053, 100), (1053, 190), (1023, 190)],
                "symbols": [(character, 0) for character in "下段"],
            },
            # 別列
            {
                "vertices": [(870, 0), (900, 0), (900, 90), (870, 90)],
                "symbols": [(character, 0) for character in "左列"],
            },
        ],
    )

    result = ocr_rectangle(
        FakeVisionClient(response),
        _make_image(),
        _make_rect(reading_order="vertical"),
    )

    assert result == "上段\n下段\n左列"


def test_ocr_rectangle_orders_columns_right_to_left_and_rows_top_to_bottom():
    """2 列それぞれが上下に分割されていても、列は右→左・列内は上→下で読む。"""
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle

    def block(left: int, right: int, top: int, text: str) -> dict[str, object]:
        return {
            "vertices": [(left, top), (right, top), (right, top + 90), (left, top + 90)],
            "symbols": [(character, 0) for character in text],
        }

    response = _FakeResponse(
        text="Vision既定順",
        structured_blocks=[
            block(70, 100, 0, "見出A"),
            block(72, 102, 100, "本文A"),
            block(20, 50, 0, "見出B"),
            block(22, 52, 100, "本文B"),
        ],
    )

    result = ocr_rectangle(
        FakeVisionClient(response),
        _make_image(),
        _make_rect(reading_order="vertical"),
    )

    assert result == "見出A\n本文A\n見出B\n本文B"


@pytest.mark.parametrize("heading_right", [95, 105])
def test_ocr_rectangle_keeps_columns_separate_across_a_spanning_block(heading_right: int):
    """左右 2 列にまたがる幅広 block があっても、両列を 1 列へ併合しない。

    heading_right は幅広 block が右端 X 降順の先頭に来る場合（105）と
    後続に来る場合（95）の両方を再現する。
    """
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle

    def block(left: int, right: int, top: int, text: str) -> dict[str, object]:
        return {
            "vertices": [(left, top), (right, top), (right, top + 80), (left, top + 80)],
            "symbols": [(character, 0) for character in text],
        }

    response = _FakeResponse(
        text="Vision既定順",
        structured_blocks=[
            block(80, 100, 100, "右上"),
            block(80, 100, 200, "右下"),
            block(20, heading_right, 0, "見出"),
            block(20, 50, 100, "左上"),
            block(20, 50, 200, "左下"),
        ],
    )

    result = ocr_rectangle(
        FakeVisionClient(response),
        _make_image(),
        _make_rect(reading_order="vertical"),
    )

    assert result == "見出\n右上\n右下\n左上\n左下"


def test_ocr_rectangle_groups_blocks_of_differing_width_in_one_column():
    """橋渡し防止を入れても、幅の異なる block が重なる通常の列は 1 列にまとまる。"""
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle

    response = _FakeResponse(
        text="Vision既定順",
        structured_blocks=[
            # 下段の方が幅広かつ右端も大きい（右端 X 降順では下段が先頭に来る）
            {
                "vertices": [(1000, 100), (1060, 100), (1060, 180), (1000, 180)],
                "symbols": [(character, 0) for character in "下段"],
            },
            {
                "vertices": [(1030, 0), (1050, 0), (1050, 80), (1030, 80)],
                "symbols": [(character, 0) for character in "上段"],
            },
        ],
    )

    result = ocr_rectangle(
        FakeVisionClient(response),
        _make_image(),
        _make_rect(reading_order="vertical"),
    )

    assert result == "上段\n下段"


def test_ocr_rectangle_restores_hyphen_break_as_line_wrap():
    """HYPHEN は行折り返しなので、ハイフンの後に改行を入れる。"""
    from google.cloud import vision

    from nova_parser.regional_ocr.ocr_client import ocr_rectangle

    break_type = vision.TextAnnotation.DetectedBreak.BreakType
    response = _FakeResponse(
        text="Vision既定順",
        structured_blocks=[
            {
                "vertices": [(0, 0), (20, 0), (20, 100), (0, 100)],
                "symbols": [
                    ("i", 0),
                    ("n", 0),
                    ("t", break_type.HYPHEN),
                    ("e", 0),
                    ("r", 0),
                ],
            }
        ],
    )

    result = ocr_rectangle(
        FakeVisionClient(response),
        _make_image(),
        _make_rect(reading_order="vertical"),
    )

    assert result == "int-\ner"


@pytest.mark.parametrize(
    ("break_type_name", "expected"),
    [("SPACE", "甲 乙"), ("LINE_BREAK", "甲\n乙")],
)
def test_ocr_rectangle_prepends_prefix_breaks(break_type_name: str, expected: str):
    """is_prefix=True の break は symbol の前へ挿入する。"""
    from google.cloud import vision

    from nova_parser.regional_ocr.ocr_client import ocr_rectangle

    break_type = getattr(vision.TextAnnotation.DetectedBreak.BreakType, break_type_name)
    response = _FakeResponse(
        text="Vision既定順",
        structured_blocks=[
            {
                "vertices": [(0, 0), (20, 0), (20, 100), (0, 100)],
                "symbols": [("甲", 0), ("乙", break_type, True)],
            }
        ],
    )

    result = ocr_rectangle(
        FakeVisionClient(response),
        _make_image(),
        _make_rect(reading_order="vertical"),
    )

    assert result == expected


def test_ocr_rectangle_keeps_prefix_break_before_trailing_symbol():
    """block 末尾 symbol に付いた prefix break は rstrip() で消えない。"""
    from google.cloud import vision

    from nova_parser.regional_ocr.ocr_client import ocr_rectangle

    break_type = vision.TextAnnotation.DetectedBreak.BreakType
    response = _FakeResponse(
        text="Vision既定順",
        structured_blocks=[
            {
                "vertices": [(0, 0), (20, 0), (20, 100), (0, 100)],
                "symbols": [("甲", 0), ("乙", break_type.LINE_BREAK, True)],
            }
        ],
    )

    result = ocr_rectangle(
        FakeVisionClient(response),
        _make_image(),
        _make_rect(reading_order="vertical"),
    )

    assert result == "甲\n乙"


def test_vertical_text_orders_real_vision_proto_blocks():
    """実 proto（vision.Block / vision.Symbol）でも列順・列内順が期待どおりになる。"""
    from google.cloud import vision

    from nova_parser.regional_ocr.ocr_client import _vertical_text

    def block(left: int, right: int, top: int, text: str) -> vision.Block:
        return vision.Block(
            bounding_box=vision.BoundingPoly(
                vertices=[
                    vision.Vertex(x=left, y=top),
                    vision.Vertex(x=right, y=top),
                    vision.Vertex(x=right, y=top + 90),
                    vision.Vertex(x=left, y=top + 90),
                ]
            ),
            paragraphs=[
                vision.Paragraph(words=[vision.Word(symbols=[vision.Symbol(text=c) for c in text])]),
            ],
        )

    annotation = vision.TextAnnotation(
        pages=[
            vision.Page(
                blocks=[
                    block(1021, 1051, 0, "上段"),
                    block(1023, 1053, 100, "下段"),
                    block(870, 900, 0, "左列"),
                ]
            )
        ],
        text="Vision既定順",
    )

    assert _vertical_text(annotation) == "上段\n下段\n左列"


def test_ocr_rectangle_restores_all_supported_symbol_breaks():
    """縦書き再構成では Vision の symbol break を文字列へ復元する。"""
    from google.cloud import vision

    from nova_parser.regional_ocr.ocr_client import ocr_rectangle

    break_type = vision.TextAnnotation.DetectedBreak.BreakType
    response = _FakeResponse(
        text="Vision既定順",
        structured_blocks=[
            {
                "vertices": [(0, 0), (20, 0), (20, 100), (0, 100)],
                "symbols": [
                    ("語", break_type.SPACE),
                    ("句", break_type.SURE_SPACE),
                    ("次", break_type.EOL_SURE_SPACE),
                    ("終", break_type.LINE_BREAK),
                    ("末", break_type.HYPHEN),
                ],
            }
        ],
    )

    result = ocr_rectangle(
        FakeVisionClient(response),
        _make_image(),
        _make_rect(reading_order="vertical"),
    )

    assert result == "語 句 次\n終\n末-"


def test_ocr_rectangle_preserves_vision_text_for_non_vertical_region():
    """構造化 block があっても通常矩形は Vision の集約済みテキストを維持する。"""
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle

    response = _FakeResponse(
        text="Vision既定順",
        structured_blocks=[
            {
                "vertices": [(0, 0), (20, 0), (20, 100), (0, 100)],
                "symbols": [("再", 0), ("構", 0), ("成", 0)],
            }
        ],
    )

    result = ocr_rectangle(FakeVisionClient(response), _make_image(), _make_rect())

    assert result == "Vision既定順"


def test_ocr_rectangle_falls_back_to_vision_text_when_vertical_blocks_are_missing():
    """縦書き指定でも構造化 block がなければ Vision のテキストを失わない。"""
    from nova_parser.regional_ocr.ocr_client import ocr_rectangle

    result = ocr_rectangle(
        FakeVisionClient(_FakeResponse(text="fallback")),
        _make_image(),
        _make_rect(reading_order="vertical"),
    )

    assert result == "fallback"


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
