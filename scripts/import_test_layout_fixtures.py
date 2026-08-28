"""Images/TEST の再圧縮済み crop から縦ブロック評価 fixture を組み立てる。"""

from __future__ import annotations

import argparse
import datetime
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

import cv2 as cv
import numpy as np
from PIL import Image

from nova_parser.regional_ocr.blocks import load_blocks, save_blocks
from nova_parser.regional_ocr.models import BlockDetectionResult, BlockRect
from nova_parser.regional_ocr.ocr_client import build_vision_client, detect_blocks

_IMAGE_SUFFIXES = {".png", ".webp", ".jpg", ".jpeg"}
_CROP_STEM = re.compile(r"^(?P<stem>.+)_(?P<order>\d{2})$")
_DEFAULT_MIN_SCORE = 0.90


@dataclass(frozen=True)
class SamplePage:
    """1枚の元画像と読み順に並んだ正解crop。"""

    stem: str
    original_path: Path
    crop_paths: tuple[Path, ...]


@dataclass(frozen=True)
class CropMatch:
    """元画像内で照合したcropの左上座標と正規化相関スコア。"""

    x: int
    y: int
    score: float


def discover_sample_pages(sample_dir: Path) -> list[SamplePage]:
    """無接尾辞の元画像と ``_NN`` crop をページ単位に対応付ける。"""
    originals: dict[str, Path] = {}
    crops: dict[str, list[tuple[int, Path]]] = {}
    for path in sorted(sample_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        match = _CROP_STEM.fullmatch(path.stem)
        if match:
            stem = match.group("stem")
            crops.setdefault(stem, []).append((int(match.group("order")), path))
            continue
        if path.stem in originals:
            raise ValueError(f"duplicate original for {path.stem}: {originals[path.stem].name}, {path.name}")
        originals[path.stem] = path

    missing = sorted(set(crops) - set(originals))
    if missing:
        raise ValueError(f"original image is missing: {', '.join(missing)}")

    pages: list[SamplePage] = []
    for stem, original_path in sorted(originals.items()):
        ordered = sorted(crops.get(stem, []), key=lambda item: (item[0], item[1].name))
        if not ordered:
            continue
        orders = [order for order, _ in ordered]
        if len(orders) != len(set(orders)):
            raise ValueError(f"duplicate crop order for {stem}: {orders}")
        pages.append(
            SamplePage(
                stem=stem,
                original_path=original_path,
                crop_paths=tuple(path for _, path in ordered),
            )
        )
    return pages


def _grayscale(image: Image.Image) -> np.ndarray:
    return cv.cvtColor(np.asarray(image.convert("RGB")), cv.COLOR_RGB2GRAY)


def locate_recompressed_crop(
    original: Image.Image,
    crop: Image.Image,
    *,
    min_score: float = _DEFAULT_MIN_SCORE,
) -> CropMatch:
    """WebP再圧縮を許容してcropの左上座標をテンプレート照合する。"""
    if crop.width > original.width or crop.height > original.height:
        raise ValueError(f"crop exceeds original: crop={crop.size}, original={original.size}")
    result = cv.matchTemplate(_grayscale(original), _grayscale(crop), cv.TM_CCOEFF_NORMED)
    _, score, _, location = cv.minMaxLoc(result)
    if not np.isfinite(score) or score < min_score:
        raise ValueError(f"crop match confidence {score:.3f} is below {min_score:.3f}")
    return CropMatch(x=int(location[0]), y=int(location[1]), score=float(score))


def fixture_from_sample(
    page: SamplePage,
    *,
    paragraph_blocks: Sequence[Mapping[str, int]],
) -> dict[str, object]:
    """サンプルページと段落矩形から既存形式の縦ブロックfixtureを作る。"""
    with Image.open(page.original_path) as original:
        original.load()
        expected: list[dict[str, int]] = []
        for crop_path in page.crop_paths:
            with Image.open(crop_path) as crop:
                match = locate_recompressed_crop(original, crop)
                expected.append(
                    {
                        "x": match.x,
                        "y": match.y,
                        "width": crop.width,
                        "height": crop.height,
                    }
                )
        return {
            "image_name": page.original_path.name,
            "image_width": original.width,
            "image_height": original.height,
            "paragraph_blocks": [dict(block) for block in paragraph_blocks],
            "expected_blocks": expected,
        }


def _block_dict(block: Mapping[str, int] | BlockRect) -> dict[str, int]:
    if isinstance(block, BlockRect):
        return block.model_dump()
    return {key: int(block[key]) for key in ("x", "y", "width", "height")}


def load_or_detect_paragraphs(
    original_path: Path,
    cache_dir: Path,
    detector: Callable[[Image.Image], Sequence[Mapping[str, int] | BlockRect]],
) -> list[dict[str, int]]:
    """寸法一致のVisionキャッシュを優先し、未採取ページだけ検出する。"""
    with Image.open(original_path) as original:
        original.load()
        cached = load_blocks(cache_dir, original_path.name)
        if cached is not None and (cached.image_width, cached.image_height) == original.size:
            return [block.model_dump() for block in cached.blocks]
        blocks = [_block_dict(block) for block in detector(original)]
        save_blocks(
            BlockDetectionResult(
                image_name=original_path.name,
                image_width=original.width,
                image_height=original.height,
                blocks=[BlockRect(**block) for block in blocks],
                detected_at=datetime.datetime.now(datetime.UTC),
            ),
            cache_dir,
        )
        return blocks


def generate_fixtures(
    sample_dir: Path,
    fixture_dir: Path,
    cache_dir: Path,
    detector: Callable[[Image.Image], Sequence[Mapping[str, int] | BlockRect]],
) -> list[Path]:
    """発見した全ページの縦ブロック評価fixtureを生成する。"""
    fixture_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for page in discover_sample_pages(sample_dir):
        paragraphs = load_or_detect_paragraphs(page.original_path, cache_dir, detector)
        fixture = fixture_from_sample(page, paragraph_blocks=paragraphs)
        output_path = fixture_dir / f"{page.stem}.json"
        output_path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        generated.append(output_path)
    return generated


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample_dir", type=Path, nargs="?", default=Path("Images/TEST"))
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=Path("tests/fixtures/regional_layout_test"),
    )
    parser.add_argument("--cache-dir", type=Path, default=Path("Output/TEST"))
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    holder: dict[str, object] = {}

    def detector(image: Image.Image) -> list[BlockRect]:
        if "client" not in holder:
            holder["client"] = build_vision_client()
        return detect_blocks(holder["client"], image)  # type: ignore[arg-type]

    for path in generate_fixtures(args.sample_dir, args.fixture_dir, args.cache_dir, detector):
        print(path)


if __name__ == "__main__":
    main()
