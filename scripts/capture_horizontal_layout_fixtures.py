"""横ブロックゴールデンテスト用 fixture 採取スクリプト。実装作業中に手動で一度だけ実行する。

- Images/EG_Silver_Wing/sample/{page}_00.png の段落矩形を取得する。
  Output/EG_Silver_Wing/{page}.blocks.json キャッシュが寸法一致で存在すれば流用し、
  なければ Cloud Vision document_text_detection を呼ぶ（実 API 呼び出し・要 ADC）。
- {page}_01.png 以降の正解切り出し画像を元画像内で画素完全一致探索し、
  元ページ座標へ変換する（ローカル処理のみ、スペック 11.1）。
- tests/fixtures/regional_layout/{page}.json へ expected_horizontal_blocks キーで書き出す。

実行: uv run python scripts/capture_horizontal_layout_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path

from capture_layout_fixtures import locate_crop
from PIL import Image

from nova_parser.regional_ocr.blocks import load_blocks
from nova_parser.regional_ocr.models import BlockRect
from nova_parser.regional_ocr.ocr_client import build_vision_client, detect_blocks

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "Images" / "EG_Silver_Wing" / "sample"
CACHE_DIR = ROOT / "Output" / "EG_Silver_Wing"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "regional_layout"

PAGES = [
    "AG2_SILVER_WINGED_SAVIOR_p006",
    "AG2_SILVER_WINGED_SAVIOR_p012",
    "AG2_SILVER_WINGED_SAVIOR_p014",
    "AG2_SILVER_WINGED_SAVIOR_p015",
    "AG2_SILVER_WINGED_SAVIOR_p019",
    "AG2_SILVER_WINGED_SAVIOR_p021",
    "AG2_SILVER_WINGED_SAVIOR_p029",
    "AG2_SILVER_WINGED_SAVIOR_p035",
    "AG2_SILVER_WINGED_SAVIOR_p067",
    "AG2_SILVER_WINGED_SAVIOR_p123",
]


def _paragraphs_for(page: str, original: Image.Image, holder: dict[str, object]) -> list[BlockRect]:
    """アプリのキャッシュが寸法一致なら流用し、なければ実 Vision で検出する（クライアントは遅延生成）。"""
    cached = load_blocks(CACHE_DIR, f"{page}.png")
    if cached is not None and (cached.image_width, cached.image_height) == original.size:
        return cached.blocks
    if "client" not in holder:
        holder["client"] = build_vision_client()
    return detect_blocks(holder["client"], original)  # type: ignore[arg-type]


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    holder: dict[str, object] = {}
    for page in PAGES:
        original_path = SAMPLE_DIR / f"{page}_00.png"
        original = Image.open(original_path).convert("RGB")
        blocks = _paragraphs_for(page, original, holder)
        expected: list[dict[str, int]] = []
        for crop_path in sorted(SAMPLE_DIR.glob(f"{page}_*.png")):
            if crop_path.name == original_path.name:
                continue
            crop = Image.open(crop_path).convert("RGB")
            try:
                x, y = locate_crop(original, crop)
            except ValueError as exc:
                raise SystemExit(f"{crop_path.name}: {exc}") from exc
            expected.append({"x": x, "y": y, "width": crop.width, "height": crop.height})
        fixture = {
            "image_name": original_path.name,
            "image_width": original.width,
            "image_height": original.height,
            "paragraph_blocks": [b.model_dump() for b in blocks],
            "expected_horizontal_blocks": expected,
        }
        out = FIXTURE_DIR / f"{page}.json"
        out.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{page}: paragraphs={len(blocks)} expected={len(expected)} -> {out}")


if __name__ == "__main__":
    main()
