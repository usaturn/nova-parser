"""regional_layout_test fixture からテキスト few-shot bank JSON を生成する。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nova_parser.regional_ocr.gemini_layout import (
    MODEL,
    PROMPT_CONTRACT_VERSION,
    classify_layout,
    groups_from_expected,
)
from nova_parser.regional_ocr.layout import compute_vertical_blocks
from nova_parser.regional_ocr.models import BlockRect

# evaluate_gemini_layout._REFERENCE_STEMS と同じ7ページ。順序固定。
_REFERENCE_STEMS = (
    "WaresBrade_P034",
    "WaresBrade_P040",
    "WaresBrade_P053",
    "warse_rule_p18",
    "warse_rule_p42",
    "warse_start_p20",
    "warse_start_p42",
)


def build_example_bank(fixture_dir: Path) -> dict[str, Any]:
    """固定stemのfixtureから画像を含まない few-shot bank を組み立てる。"""
    examples: list[dict[str, Any]] = []
    for stem in _REFERENCE_STEMS:
        path = fixture_dir / f"{stem}.json"
        fixture = json.loads(path.read_text(encoding="utf-8"))
        image_width = int(fixture["image_width"])
        image_height = int(fixture["image_height"])
        paragraphs = [BlockRect(**block) for block in fixture["paragraph_blocks"]]
        candidates = compute_vertical_blocks(image_width, image_height, paragraphs)
        expected = [BlockRect(**block) for block in fixture["expected_blocks"]]
        # classify_layout の密度入力は統合前段落数（閾値80）。candidates は縦ブロック。
        family = classify_layout(image_width, image_height, len(paragraphs))
        examples.append(
            {
                "stem": stem,
                "family": family,
                "image_width": image_width,
                "image_height": image_height,
                "candidates": [candidate.model_dump() for candidate in candidates],
                "groups": groups_from_expected(candidates, expected),
            }
        )
    return {
        "model": MODEL,
        "prompt_contract_version": PROMPT_CONTRACT_VERSION,
        "examples": examples,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=Path("tests/fixtures/regional_layout_test"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("src/nova_parser/regional_ocr/data/gemini_vertical_examples.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    bank = build_example_bank(args.fixture_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bank, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
