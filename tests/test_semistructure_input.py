"""半構造化入力境界のテスト。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
from nova_parser.semistructure.input import load_pages
from nova_parser.semistructure.manifest import load_manifest
from nova_parser.semistructure.models import Audience, DocumentType
from tests.semistructure_factories import make_manifest, write_region_fixture


@pytest.fixture
def fixture_dir() -> Path:
    """半構造化入力fixtureのディレクトリを返す。"""
    return Path(__file__).parent / "fixtures" / "semistructure"


def test_load_manifest_validates_json(fixture_dir: Path) -> None:
    """マニフェストJSONを既存のPydantic型へ変換する。"""
    manifest = load_manifest(fixture_dir / "manifest.json")

    assert manifest.book_id == "eg-test"
    assert manifest.default_document_type == DocumentType.RULEBOOK
    assert manifest.audience_overrides[0].audience == Audience.GM


def test_load_pages_sorts_pages_and_preserves_raw_text(fixture_dir: Path) -> None:
    """ページ順、改行、ハッシュ、audience継承値を確定する。"""
    manifest = load_manifest(fixture_dir / "manifest.json")
    pages = load_pages(fixture_dir, manifest)

    assert [page.page_number for page in pages] == [22, 234]
    assert pages[0].regions[0].raw_text == "最初にお読みくだ\nさい"
    expected_hash = hashlib.sha256((fixture_dir / "p022.regions.json").read_bytes()).hexdigest()
    assert pages[0].source_sha256 == f"sha256:{expected_hash}"
    assert pages[0].inherited_audience == Audience.SHARED
    assert pages[1].inherited_audience == Audience.GM


def test_load_pages_sorts_regions_by_draw_order(fixture_dir: Path) -> None:
    """JSON配列順にかかわらず領域をdraw_order順にする。"""
    manifest = load_manifest(fixture_dir / "manifest.json")

    pages = load_pages(fixture_dir, manifest)

    assert [region.draw_order for region in pages[1].regions] == [0, 1]
    assert [region.raw_text for region in pages[1].regions] == ["先", "後"]


def test_load_pages_rejects_duplicate_page_number(tmp_path: Path) -> None:
    """異なる入力ファイルが同じページ番号へ解決される場合は拒否する。"""
    write_region_fixture(tmp_path / "a_p022.regions.json", image_name="a.png")
    write_region_fixture(tmp_path / "b_p022.regions.json", image_name="b.png")
    manifest = make_manifest(
        input_glob="*.regions.json",
        page_pattern=r"_p(?P<page>[0-9]{3})\.regions\.json$",
    )

    with pytest.raises(ValueError, match="ページ番号が重複"):
        load_pages(tmp_path, manifest)


@pytest.mark.parametrize(
    ("status", "text", "message"),
    [
        ("pending", "本文", "OCRが完了していません"),
        ("done", None, "OCR本文がありません"),
    ],
)
def test_load_pages_rejects_incomplete_region(
    tmp_path: Path,
    status: str,
    text: str | None,
    message: str,
) -> None:
    """done以外の状態と本文Noneを入力エラーにする。"""
    _write_session(
        tmp_path / "book_p022.regions.json",
        RegionRecord(
            rectangle=Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=10, height=10),
            text=text,
            ocr_status=status,
        ),
    )

    with pytest.raises(ValueError, match=message):
        load_pages(tmp_path, _manifest())


def test_load_pages_rejects_rectangle_outside_image(tmp_path: Path) -> None:
    """右端または下端が画像寸法を超える矩形を拒否する。"""
    _write_session(
        tmp_path / "book_p022.regions.json",
        RegionRecord(
            rectangle=Rectangle(rect_id="r1", draw_order=0, x=95, y=0, width=10, height=10),
            text="本文",
            ocr_status="done",
        ),
    )

    with pytest.raises(ValueError, match="矩形が画像外"):
        load_pages(tmp_path, _manifest())


def _manifest():
    return make_manifest(page_pattern=r"_p(?P<page>[0-9]{3})\.regions\.json$")


def _write_session(path: Path, *regions: RegionRecord) -> None:
    session = ImageSession(
        image_name="book_p022.png",
        image_width=100,
        image_height=100,
        regions=list(regions),
    )
    path.write_text(session.model_dump_json(), encoding="utf-8")
