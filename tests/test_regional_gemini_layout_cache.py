"""Gemini vertical layout 成功結果 cache / fingerprint のテスト。"""

from __future__ import annotations

import datetime
from pathlib import Path

from nova_parser.regional_ocr import gemini_layout_cache as cache_module
from nova_parser.regional_ocr.gemini_layout_cache import (
    GeminiLayoutCacheEntry,
    build_fingerprint,
    load_cached_blocks,
    save_cached_blocks,
)
from nova_parser.regional_ocr.models import BlockRect


def test_build_fingerprint_covers_image_candidates_model_dims_and_bank(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"image-v1")
    candidates = [BlockRect(x=1, y=2, width=3, height=4)]

    original = build_fingerprint(image_path, 100, 200, candidates, model="model-a")
    assert original == build_fingerprint(image_path, 100, 200, candidates, model="model-a")

    image_path.write_bytes(b"image-v2")
    assert original != build_fingerprint(image_path, 100, 200, candidates, model="model-a")
    image_path.write_bytes(b"image-v1")

    assert original != build_fingerprint(
        image_path,
        100,
        200,
        [BlockRect(x=9, y=2, width=3, height=4)],
        model="model-a",
    )
    assert original != build_fingerprint(image_path, 100, 200, candidates, model="model-b")
    assert original != build_fingerprint(image_path, 101, 200, candidates, model="model-a")
    assert original != build_fingerprint(image_path, 100, 201, candidates, model="model-a")

    monkeypatch.setattr(cache_module, "example_bank_sha256", lambda: "bank-b")
    assert original != build_fingerprint(image_path, 100, 200, candidates, model="model-a")


def test_cache_reuses_only_matching_fingerprint(tmp_path: Path) -> None:
    entry = GeminiLayoutCacheEntry(
        image_name="page.png",
        fingerprint="fingerprint-a",
        model="gemini-3.5-flash-lite",
        prompt_contract_version="regional-vertical-groups-v1",
        vertical_blocks=[BlockRect(x=1, y=2, width=3, height=4)],
        created_at=datetime.datetime(2026, 8, 28, tzinfo=datetime.UTC),
    )
    save_cached_blocks(tmp_path, entry)
    assert load_cached_blocks(tmp_path, "page.png", "fingerprint-a") == entry.vertical_blocks
    assert load_cached_blocks(tmp_path, "page.png", "fingerprint-b") is None


def test_load_cached_blocks_returns_none_on_miss_and_corruption(tmp_path: Path) -> None:
    assert load_cached_blocks(tmp_path, "page.png", "fingerprint-a") is None

    cache_dir = tmp_path / "gemini-layout-cache"
    cache_dir.mkdir(parents=True)
    broken = cache_dir / "page.json"
    broken.write_text("{{{ broken", encoding="utf-8")
    assert load_cached_blocks(tmp_path, "page.png", "fingerprint-a") is None

    broken.write_text('{"image_name": "page.png"}', encoding="utf-8")
    assert load_cached_blocks(tmp_path, "page.png", "fingerprint-a") is None

    entry = GeminiLayoutCacheEntry(
        image_name="page.png",
        fingerprint="fingerprint-a",
        model="gemini-3.5-flash-lite",
        prompt_contract_version="regional-vertical-groups-v1",
        vertical_blocks=[BlockRect(x=1, y=2, width=3, height=4)],
        created_at=datetime.datetime(2026, 8, 28, tzinfo=datetime.UTC),
    )
    save_cached_blocks(tmp_path, entry)
    # 同一 stem でも entry.image_name と不一致なら miss
    assert load_cached_blocks(tmp_path, "page.webp", "fingerprint-a") is None
