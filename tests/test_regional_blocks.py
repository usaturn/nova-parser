"""regional_ocr のブロック検出（モデル・detect_blocks・キャッシュ）のテスト。"""

from __future__ import annotations

import datetime

import pytest
from pydantic import ValidationError

from nova_parser.regional_ocr.models import BlockDetectionResult, BlockRect

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
