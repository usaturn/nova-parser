"""crop モジュールのユニットテスト。"""

from PIL import Image

from nova_parser.crop import (
    CardRegion,
    PageBlocks,
    cluster_blocks,
    crop_cards,
    detect_and_crop_cards,
    extract_block_regions,
    filter_card_candidates,
)


# --- テストヘルパー ---


def _make_document_dict(
    *,
    width: float = 1000.0,
    height: float = 1000.0,
    blocks: list[dict] | None = None,
    text: str = "sample text for testing",
) -> dict:
    """Document AI Document をシミュレートする dict を返す。

    google.cloud.documentai_v1.Document(**dict) で Document オブジェクトに変換可能。
    """
    if blocks is None:
        blocks = [
            {
                "layout": {
                    "bounding_poly": {
                        "normalized_vertices": [
                            {"x": 0.1, "y": 0.1},
                            {"x": 0.5, "y": 0.1},
                            {"x": 0.5, "y": 0.3},
                            {"x": 0.1, "y": 0.3},
                        ],
                    },
                    "confidence": 0.95,
                    "text_anchor": {
                        "text_segments": [{"start_index": 0, "end_index": 11}],
                    },
                },
            },
        ]
    return {
        "text": text,
        "pages": [
            {
                "dimension": {"width": width, "height": height},
                "blocks": blocks,
            },
        ],
    }


def _make_document(**kwargs):
    """dict から documentai.Document オブジェクトを生成する。"""
    from google.cloud import documentai_v1 as documentai

    return documentai.Document(_make_document_dict(**kwargs))


def _make_image(width: int = 1000, height: int = 1000) -> Image.Image:
    """テスト用のメモリ上の画像を生成する。"""
    return Image.new("RGB", (width, height), color=(255, 255, 255))


# --- extract_block_regions ---


class TestExtractBlockRegions:
    def test_basic_extraction(self):
        doc = _make_document()
        result = extract_block_regions(doc)

        assert isinstance(result, PageBlocks)
        assert result.page_width == 1000
        assert result.page_height == 1000
        assert len(result.regions) == 1

        region = result.regions[0]
        assert region.left == 100
        assert region.top == 100
        assert region.right == 500
        assert region.bottom == 300
        assert abs(region.confidence - 0.95) < 1e-6
        assert region.text_snippet == "sample text"

    def test_empty_blocks(self):
        doc = _make_document(blocks=[])
        result = extract_block_regions(doc)

        assert result.regions == []
        assert result.page_width == 1000
        assert result.page_height == 1000

    def test_skips_blocks_with_few_vertices(self):
        blocks = [
            {
                "layout": {
                    "bounding_poly": {
                        "normalized_vertices": [
                            {"x": 0.1, "y": 0.1},
                            {"x": 0.5, "y": 0.1},
                        ],
                    },
                    "confidence": 0.9,
                    "text_anchor": {"text_segments": []},
                },
            },
        ]
        doc = _make_document(blocks=blocks)
        result = extract_block_regions(doc)
        assert result.regions == []

    def test_snippet_truncation(self):
        long_text = "a" * 200
        blocks = [
            {
                "layout": {
                    "bounding_poly": {
                        "normalized_vertices": [
                            {"x": 0.0, "y": 0.0},
                            {"x": 1.0, "y": 0.0},
                            {"x": 1.0, "y": 1.0},
                            {"x": 0.0, "y": 1.0},
                        ],
                    },
                    "confidence": 0.9,
                    "text_anchor": {
                        "text_segments": [{"start_index": 0, "end_index": 200}],
                    },
                },
            },
        ]
        doc = _make_document(blocks=blocks, text=long_text)
        result = extract_block_regions(doc)
        assert len(result.regions[0].text_snippet) == 100


# --- cluster_blocks ---


class TestClusterBlocks:
    def test_empty_input(self):
        assert cluster_blocks([], 1000, 1000) == []

    def test_single_region(self):
        regions = [CardRegion(100, 100, 500, 300, 0.9, "test")]
        result = cluster_blocks(regions, 1000, 1000)
        assert len(result) == 1
        assert result[0].left == 100

    def test_vertically_close_regions_merge(self):
        regions = [
            CardRegion(100, 100, 500, 200, 0.9, "top"),
            CardRegion(100, 210, 500, 300, 0.85, "bottom"),
        ]
        result = cluster_blocks(regions, 1000, 1000)
        assert len(result) == 1
        assert result[0].top == 100
        assert result[0].bottom == 300
        assert result[0].confidence == (0.9 + 0.85) / 2

    def test_distant_regions_stay_separate(self):
        regions = [
            CardRegion(100, 100, 500, 200, 0.9, "top"),
            CardRegion(100, 500, 500, 600, 0.85, "bottom"),
        ]
        result = cluster_blocks(regions, 1000, 1000)
        assert len(result) == 2

    def test_no_horizontal_overlap_stays_separate(self):
        regions = [
            CardRegion(100, 100, 200, 200, 0.9, "left"),
            CardRegion(600, 210, 900, 300, 0.85, "right"),
        ]
        result = cluster_blocks(regions, 1000, 1000)
        assert len(result) == 2


# --- filter_card_candidates ---


class TestFilterCardCandidates:
    def test_empty_input(self):
        assert filter_card_candidates([], 1000, 1000) == []

    def test_zero_page_area(self):
        regions = [CardRegion(0, 0, 100, 100, 0.9, "test")]
        assert filter_card_candidates(regions, 0, 0) == []

    def test_filters_by_area_ratio(self):
        regions = [
            CardRegion(0, 0, 100, 100, 0.9, "small"),  # 1% area
            CardRegion(0, 0, 300, 300, 0.9, "medium"),  # 9% area
            CardRegion(0, 0, 950, 950, 0.9, "large"),  # 90.25% area
        ]
        result = filter_card_candidates(regions, 1000, 1000)
        assert len(result) == 1
        assert result[0].text_snippet == "medium"

    def test_custom_thresholds(self):
        regions = [
            CardRegion(0, 0, 100, 100, 0.9, "tiny"),  # 1%
        ]
        result = filter_card_candidates(regions, 1000, 1000, min_area_ratio=0.005, max_area_ratio=0.02)
        assert len(result) == 1


# --- crop_cards ---


class TestCropCards:
    def test_basic_crop(self):
        img = _make_image(1000, 1000)
        regions = [CardRegion(100, 100, 500, 300, 0.9, "test")]
        result = crop_cards(img, regions, padding=10)

        assert len(result) == 1
        region, cropped = result[0]
        assert region.left == 100
        assert cropped.size == (420, 220)  # (500+10)-(100-10) x (300+10)-(100-10)

    def test_padding_clamps_to_image_bounds(self):
        img = _make_image(500, 500)
        regions = [CardRegion(0, 0, 500, 500, 0.9, "full")]
        result = crop_cards(img, regions, padding=50)

        assert len(result) == 1
        _, cropped = result[0]
        assert cropped.size == (500, 500)

    def test_empty_regions(self):
        img = _make_image()
        result = crop_cards(img, [], padding=10)
        assert result == []

    def test_multiple_regions(self):
        img = _make_image(1000, 1000)
        regions = [
            CardRegion(100, 100, 300, 300, 0.9, "a"),
            CardRegion(500, 500, 700, 700, 0.8, "b"),
        ]
        result = crop_cards(img, regions, padding=0)
        assert len(result) == 2
        assert result[0][1].size == (200, 200)
        assert result[1][1].size == (200, 200)


# --- detect_and_crop_cards ---


class TestDetectAndCropCards:
    def test_end_to_end(self):
        doc = _make_document()
        img = _make_image()

        results = detect_and_crop_cards(img, doc)
        assert len(results) == 1
        region, cropped = results[0]
        assert abs(region.confidence - 0.95) < 1e-6
        assert cropped.size[0] > 0
        assert cropped.size[1] > 0

    def test_no_candidates_returns_empty(self):
        blocks = [
            {
                "layout": {
                    "bounding_poly": {
                        "normalized_vertices": [
                            {"x": 0.0, "y": 0.0},
                            {"x": 0.01, "y": 0.0},
                            {"x": 0.01, "y": 0.01},
                            {"x": 0.0, "y": 0.01},
                        ],
                    },
                    "confidence": 0.9,
                    "text_anchor": {"text_segments": [{"start_index": 0, "end_index": 1}]},
                },
            },
        ]
        doc = _make_document(blocks=blocks, text="X")
        img = _make_image()
        assert detect_and_crop_cards(img, doc) == []

    def test_custom_area_thresholds(self):
        doc = _make_document()
        img = _make_image()
        # default block area ratio = 0.4*0.2 = 0.08, set max below that
        results = detect_and_crop_cards(img, doc, max_area_ratio=0.05)
        assert results == []

    def test_empty_document(self):
        doc = _make_document(blocks=[], text="")
        img = _make_image()
        assert detect_and_crop_cards(img, doc) == []
