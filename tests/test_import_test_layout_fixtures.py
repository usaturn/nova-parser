from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from scripts.import_test_layout_fixtures import (
    discover_sample_pages,
    fixture_from_sample,
    generate_fixtures,
    load_or_detect_paragraphs,
    locate_recompressed_crop,
)


def _make_source() -> Image.Image:
    image = Image.new("RGB", (180, 140), "white")
    draw = ImageDraw.Draw(image)
    for y in range(8, 132, 11):
        draw.line((5, y, 174, y + (y % 7)), fill=(20 + y, 40, 180 - y // 2), width=2)
    draw.rectangle((23, 17, 121, 96), outline="black", width=3)
    draw.ellipse((48, 35, 92, 79), fill=(180, 70, 30))
    draw.text((28, 82), "layout sample 42", fill="black")
    return image


def test_discover_sample_pages_accepts_unsuffixed_originals_and_orders_crops(tmp_path: Path) -> None:
    source = _make_source()
    source.save(tmp_path / "page.webp", format="WEBP", quality=91)
    source.crop((20, 10, 100, 90)).save(tmp_path / "page_02.webp", format="WEBP", quality=70)
    source.crop((60, 40, 150, 120)).save(tmp_path / "page_01.webp", format="WEBP", quality=70)
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")

    pages = discover_sample_pages(tmp_path)

    assert len(pages) == 1
    assert pages[0].stem == "page"
    assert pages[0].original_path.name == "page.webp"
    assert [path.name for path in pages[0].crop_paths] == ["page_01.webp", "page_02.webp"]


def test_locate_recompressed_crop_recovers_original_pixel_coordinates(tmp_path: Path) -> None:
    source = _make_source()
    original_path = tmp_path / "source.webp"
    crop_path = tmp_path / "crop.webp"
    source.save(original_path, format="WEBP", quality=92)
    source.crop((23, 17, 123, 99)).save(crop_path, format="WEBP", quality=58)

    with Image.open(original_path) as original, Image.open(crop_path) as crop:
        match = locate_recompressed_crop(original, crop)

    assert (match.x, match.y) == (23, 17)
    assert match.score >= 0.90


def test_locate_recompressed_crop_rejects_unrelated_image() -> None:
    source = _make_source()
    unrelated = Image.new("RGB", (70, 50), (0, 255, 0))
    ImageDraw.Draw(unrelated).line((0, 0, 69, 49), fill="blue", width=5)

    with pytest.raises(ValueError, match="confidence"):
        locate_recompressed_crop(source, unrelated)


def test_fixture_from_sample_preserves_full_page_selection(tmp_path: Path) -> None:
    source = _make_source()
    original_path = tmp_path / "page.png"
    crop_path = tmp_path / "page_01.webp"
    source.save(original_path)
    source.save(crop_path, format="WEBP", quality=75)
    page = discover_sample_pages(tmp_path)[0]

    fixture = fixture_from_sample(
        page,
        paragraph_blocks=[{"x": 10, "y": 20, "width": 30, "height": 40}],
    )

    assert fixture == {
        "image_name": "page.png",
        "image_width": 180,
        "image_height": 140,
        "paragraph_blocks": [{"x": 10, "y": 20, "width": 30, "height": 40}],
        "expected_blocks": [{"x": 0, "y": 0, "width": 180, "height": 140}],
    }


def test_load_or_detect_paragraphs_reuses_dimension_matching_cache(tmp_path: Path) -> None:
    source = _make_source()
    original_path = tmp_path / "page.png"
    source.save(original_path)
    calls = 0

    def detector(image: Image.Image) -> list[dict[str, int]]:
        nonlocal calls
        calls += 1
        assert image.size == source.size
        return [{"x": 10, "y": 20, "width": 30, "height": 40}]

    first = load_or_detect_paragraphs(original_path, tmp_path / "cache", detector)
    second = load_or_detect_paragraphs(original_path, tmp_path / "cache", detector)

    assert first == second == [{"x": 10, "y": 20, "width": 30, "height": 40}]
    assert calls == 1


def test_load_or_detect_paragraphs_can_force_vision_refresh(tmp_path: Path) -> None:
    source = _make_source()
    original_path = tmp_path / "page.png"
    source.save(original_path)
    calls = 0

    def detector(image: Image.Image) -> list[dict[str, int]]:
        nonlocal calls
        calls += 1
        return [{"x": calls, "y": 20, "width": 30, "height": 40}]

    first = load_or_detect_paragraphs(original_path, tmp_path / "cache", detector)
    refreshed = load_or_detect_paragraphs(original_path, tmp_path / "cache", detector, force=True)

    assert first[0]["x"] == 1
    assert refreshed[0]["x"] == 2
    assert calls == 2


def test_generate_fixtures_writes_one_json_per_discovered_page(tmp_path: Path) -> None:
    sample_dir = tmp_path / "samples"
    fixture_dir = tmp_path / "fixtures"
    cache_dir = tmp_path / "cache"
    sample_dir.mkdir()
    source = _make_source()
    source.save(sample_dir / "page.webp", format="WEBP", quality=92)
    source.crop((23, 17, 123, 99)).save(sample_dir / "page_01.webp", format="WEBP", quality=58)

    generated = generate_fixtures(
        sample_dir,
        fixture_dir,
        cache_dir,
        lambda image: [{"x": 5, "y": 6, "width": 70, "height": 80}],
    )

    assert generated == [fixture_dir / "page.json"]
    assert (fixture_dir / "page.json").read_text(encoding="utf-8").startswith('{\n  "image_name": "page.webp"')
