"""ゴールデンテスト用 fixture 採取スクリプト。実装作業中に手動で一度だけ実行する。

- Images/EG/sample/{page}_00.png を Cloud Vision document_text_detection にかけ、
  段落矩形を取得する（実 API 呼び出し・要 ADC）。
- {page}_01.png 以降の正解切り出し画像を元画像内で画素完全一致探索し、
  元ページ座標へ変換する（ローカル処理のみ、スペック 11.1）。
- tests/fixtures/regional_layout/{page}.json へ書き出す。

実行: uv run python scripts/capture_layout_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from nova_parser.regional_ocr.ocr_client import build_vision_client, detect_blocks

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "Images" / "EG" / "sample"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "regional_layout"

PAGES = [
    "ANGEL_GEAR2_p022",
    "ANGEL_GEAR2_p023",
    "ANGEL_GEAR2_p203",
    "ANGEL_GEAR2_p249",
    "ANGEL_GEAR2_p251",
    "ANGEL_GEAR2_p259",
]


def _match_all_rows(obytes: bytes, cbytes: bytes, x: int, y: int, stride: int, cw: int, ch: int) -> bool:
    row_len = cw * 3
    for dy in range(ch):
        o_start = (y + dy) * stride + x * 3
        if obytes[o_start : o_start + row_len] != cbytes[dy * row_len : (dy + 1) * row_len]:
            return False
    return True


def locate_crop(original: Image.Image, crop: Image.Image) -> tuple[int, int]:
    """crop が original 内で画素完全一致する左上座標を返す。見つからなければ ValueError。"""
    ow, oh = original.size
    cw, ch = crop.size
    obytes = original.tobytes()
    cbytes = crop.tobytes()
    stride = ow * 3
    first_row = cbytes[: cw * 3]
    for y in range(oh - ch + 1):
        row = obytes[y * stride : (y + 1) * stride]
        x_byte = row.find(first_row)
        while x_byte != -1:
            if x_byte % 3 == 0 and _match_all_rows(obytes, cbytes, x_byte // 3, y, stride, cw, ch):
                return x_byte // 3, y
            x_byte = row.find(first_row, x_byte + 1)
    raise ValueError("切り出し画像が元画像内で画素一致しません")


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    client = build_vision_client()
    for page in PAGES:
        original_path = SAMPLE_DIR / f"{page}_00.png"
        original = Image.open(original_path).convert("RGB")
        blocks = detect_blocks(client, original)
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
            "expected_blocks": expected,
        }
        out = FIXTURE_DIR / f"{page}.json"
        out.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{page}: paragraphs={len(blocks)} expected={len(expected)} -> {out}")


if __name__ == "__main__":
    main()
