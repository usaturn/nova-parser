"""regional_ocr のブロック検出（モデル・detect_blocks・キャッシュ）のテスト。"""

from __future__ import annotations

import datetime

import pytest
from PIL import Image
from pydantic import ValidationError

from nova_parser.regional_ocr.blocks import blocks_path, load_blocks, save_blocks
from nova_parser.regional_ocr.errors import OcrBackendError
from nova_parser.regional_ocr.models import BlockDetectionResult, BlockRect
from nova_parser.regional_ocr.ocr_client import detect_blocks
from tests.conftest import FakeVisionClient, _FakeResponse

# ---------------------------------------------------------------------------
# モデル
# ---------------------------------------------------------------------------


def test_block_rect_accepts_valid_rectangle():
    rect = BlockRect(x=0, y=0, width=10, height=20)
    assert (rect.x, rect.y, rect.width, rect.height) == (0, 0, 10, 20)


def test_block_rect_rejects_zero_width_and_negative_origin():
    with pytest.raises(ValidationError):
        BlockRect(x=0, y=0, width=0, height=10)
    with pytest.raises(ValidationError):
        BlockRect(x=-1, y=0, width=10, height=10)


def test_block_detection_result_roundtrips_json():
    result = BlockDetectionResult(
        image_name="a.png",
        image_width=100,
        image_height=100,
        blocks=[BlockRect(x=10, y=10, width=30, height=40)],
        detected_at=datetime.datetime(2026, 7, 18, tzinfo=datetime.UTC),
    )
    restored = BlockDetectionResult.model_validate_json(result.model_dump_json())
    assert restored == result
    assert restored.schema_version == 1


# ---------------------------------------------------------------------------
# detect_blocks
# ---------------------------------------------------------------------------


def _gray_image(size: tuple[int, int] = (100, 100)) -> Image.Image:
    return Image.new("RGB", size, color=(128, 128, 128))


def test_detect_blocks_converts_axis_aligned_vertices():
    fake = FakeVisionClient(_FakeResponse(blocks=[[(10, 10), (60, 10), (60, 40), (10, 40)]]))
    blocks = detect_blocks(fake, _gray_image())
    assert blocks == [BlockRect(x=10, y=10, width=50, height=30)]


def test_detect_blocks_converts_rotated_quad_to_bounding_rect():
    fake = FakeVisionClient(_FakeResponse(blocks=[[(50, 10), (90, 50), (50, 90), (10, 50)]]))
    blocks = detect_blocks(fake, _gray_image())
    assert blocks == [BlockRect(x=10, y=10, width=80, height=80)]


def test_detect_blocks_clamps_to_image_bounds():
    fake = FakeVisionClient(_FakeResponse(blocks=[[(-10, -10), (150, -10), (150, 150), (-10, 150)]]))
    blocks = detect_blocks(fake, _gray_image((100, 100)))
    assert blocks == [BlockRect(x=0, y=0, width=100, height=100)]


def test_detect_blocks_skips_degenerate_rect():
    fake = FakeVisionClient(
        _FakeResponse(blocks=[[(10, 10), (10, 40)], [(20, 20), (70, 20), (70, 60), (20, 60)]]),
    )
    blocks = detect_blocks(fake, _gray_image())
    assert blocks == [BlockRect(x=20, y=20, width=50, height=40)]


def test_detect_blocks_returns_empty_when_no_pages():
    fake = FakeVisionClient(_FakeResponse(text=""))
    assert detect_blocks(fake, _gray_image()) == []


def test_detect_blocks_raises_ocr_backend_error_on_api_error():
    fake = FakeVisionClient(_FakeResponse(error_message="boom"))
    with pytest.raises(OcrBackendError, match="boom"):
        detect_blocks(fake, _gray_image())


def test_detect_blocks_passes_language_hints_to_document_text_detection():
    fake = FakeVisionClient(_FakeResponse(blocks=[[(0, 0), (10, 0), (10, 10), (0, 10)]]))
    detect_blocks(fake, _gray_image(), language_hints=("ja", "en"))
    assert len(fake.document_calls) == 1
    assert list(fake.document_calls[0]["image_context"].language_hints) == ["ja", "en"]


# ---------------------------------------------------------------------------
# キャッシュ（blocks.py）
# ---------------------------------------------------------------------------


def _sample_result(image_name: str = "a.png") -> BlockDetectionResult:
    return BlockDetectionResult(
        image_name=image_name,
        image_width=100,
        image_height=100,
        blocks=[BlockRect(x=10, y=10, width=30, height=40)],
        detected_at=datetime.datetime(2026, 7, 18, tzinfo=datetime.UTC),
    )


def test_blocks_path_uses_stem_with_blocks_json_suffix(tmp_path):
    assert blocks_path(tmp_path, "foo.png") == tmp_path / "foo.blocks.json"
    assert blocks_path(tmp_path, "foo") == tmp_path / "foo.blocks.json"


def test_load_blocks_returns_none_when_file_missing(tmp_path):
    assert load_blocks(tmp_path, "a.png") is None


def test_save_then_load_roundtrips(tmp_path):
    result = _sample_result()
    save_blocks(result, tmp_path)
    assert (tmp_path / "a.blocks.json").exists()
    assert load_blocks(tmp_path, "a.png") == result


def test_save_blocks_creates_output_dir(tmp_path):
    nested = tmp_path / "out" / "deep"
    save_blocks(_sample_result(), nested)
    assert (nested / "a.blocks.json").exists()


def test_load_blocks_returns_none_on_broken_json(tmp_path):
    (tmp_path / "a.blocks.json").write_text("{{{ broken", encoding="utf-8")
    assert load_blocks(tmp_path, "a.png") is None


def test_load_blocks_returns_none_on_schema_mismatch(tmp_path):
    (tmp_path / "a.blocks.json").write_text('{"image_name": "a.png"}', encoding="utf-8")
    assert load_blocks(tmp_path, "a.png") is None
