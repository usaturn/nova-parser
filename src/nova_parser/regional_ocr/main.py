"""nova-parser-regional のエントリポイント。"""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from nova_parser.regional_ocr.app import create_app
from nova_parser.regional_ocr.ocr_client import build_vision_client
from nova_parser.regional_ocr.state import AppState

load_dotenv()


def main(argv: list[str] | None = None) -> None:
    """CLI エントリポイント。argv=None なら sys.argv を使用する。"""
    parser = argparse.ArgumentParser(description="対話的矩形 OCR Web ツール（Cloud Vision API）")
    parser.add_argument("image_dir", type=Path, help="OCR 対象画像が格納されたディレクトリ")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="サイドカ JSON と Markdown の保存先（未指定時: Output/<画像ディレクトリ名>）",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    resolved_image_dir = args.image_dir.resolve()
    if args.output_dir is None:
        base = Path("Output")
        output_dir = (base / resolved_image_dir.name) if resolved_image_dir.name else base
        resolved_output_dir = output_dir.resolve()
    else:
        resolved_output_dir = args.output_dir.resolve()

    state = AppState(
        image_dir=resolved_image_dir,
        output_dir=resolved_output_dir,
        vision_client_factory=build_vision_client,
    )
    app = create_app(state)
    uvicorn.run(app, host=args.host, port=args.port)
