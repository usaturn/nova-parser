import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


IMAGES_DIR = Path("Images")
OUTPUT_DIR = Path("Output")

MIME_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

OCR_PROMPT = """\
この画像に含まれるテキストを全て抽出してください。
- 元のレイアウトや改行をできるだけ維持してください
- 表がある場合は Markdown のテーブル形式で出力してください
- 読み取れない文字は [?] と表記してください
"""

MODEL = "gemini-3.1-pro-preview"


def get_client() -> genai.Client:
    """Gemini クライアントを初期化する（Vertex AI Express モード）。"""
    return genai.Client(
        vertexai=True,
        api_key=os.environ.get("VERTEX_AI_API_KEY"),
    )


def list_images() -> list[Path]:
    """Images/ ディレクトリ内の画像ファイル一覧を返す。"""
    if not IMAGES_DIR.exists():
        return []
    return sorted(p for p in IMAGES_DIR.iterdir() if p.suffix.lower() in MIME_TYPES)


def ocr_image(client: genai.Client, image_path: Path) -> str:
    """画像ファイルを Gemini に送信し、OCR 結果のテキストを返す。"""
    mime_type = MIME_TYPES[image_path.suffix.lower()]
    image_bytes = image_path.read_bytes()

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            OCR_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
    )
    return response.text


def main():
    parser = argparse.ArgumentParser(
        description="画像ファイルを Gemini で OCR し、Markdown 形式で出力する。",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="処理する画像ファイルのパス（省略時は Images/ 内の全画像を処理）",
    )
    args = parser.parse_args()

    if args.files:
        images: list[Path] = []
        for f in args.files:
            p = Path(f)
            if not p.exists():
                print(f"エラー: ファイルが見つかりません: {p}", file=sys.stderr)
                sys.exit(1)
            if p.suffix.lower() not in MIME_TYPES:
                print(
                    f"エラー: サポートされていない画像形式です: {p.suffix} ({p})",
                    file=sys.stderr,
                )
                sys.exit(1)
            images.append(p)
    else:
        images = list_images()

    if not images:
        print(f"{IMAGES_DIR}/ に画像ファイルが見つかりません。")
        return

    client = get_client()
    print(f"{len(images)} 件の画像を処理します。\n")

    OUTPUT_DIR.mkdir(exist_ok=True)

    for img in images:
        print(f"処理中: {img.name} ... ", end="", flush=True)
        text = ocr_image(client, img)
        output_file = OUTPUT_DIR / f"{img.stem}.md"
        output_file.write_text(text, encoding="utf-8")
        print(f"完了 -> {output_file}")

    print(f"\n全ての結果を {OUTPUT_DIR}/ に保存しました。")


if __name__ == "__main__":
    main()
