import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from nova_parser.ocr import MIME_TYPES

load_dotenv()


IMAGES_DIR = Path("Images")
OUTPUT_DIR = Path("Output")

MAX_RETRIES = 5
INITIAL_WAIT = 30


def resolve_images(file_args: list[str]) -> list[Path]:
    """CLI 引数から画像ファイルリストを解決する。"""
    if file_args:
        images: list[Path] = []
        for f in file_args:
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
        return images

    if not IMAGES_DIR.exists():
        return []
    return sorted(p for p in IMAGES_DIR.iterdir() if p.suffix.lower() in MIME_TYPES)


def _is_rate_limit_error(exc: Exception) -> bool:
    """例外が 429 レート制限エラーかどうか判定する。"""
    from google.genai.errors import ClientError
    from pydantic_ai.exceptions import ModelHTTPError

    if isinstance(exc, ClientError) and exc.code == 429:
        return True
    if isinstance(exc, ModelHTTPError) and exc.status_code == 429:
        return True
    return False


def run_plain(images: list[Path]) -> None:
    """plain モード: 画像を OCR してMarkdown として出力する。"""
    from nova_parser.ocr import get_client, ocr_image

    client = get_client()
    for img in images:
        output_file = OUTPUT_DIR / f"{img.stem}.plain.md"
        if output_file.exists():
            print(f"スキップ: {output_file}（既に存在します）")
            continue
        print(f"処理中: {img.name} ... ", end="", flush=True)
        for attempt in range(MAX_RETRIES):
            try:
                text = ocr_image(client, img)
                break
            except Exception as exc:
                if not _is_rate_limit_error(exc) or attempt == MAX_RETRIES - 1:
                    raise
                wait = INITIAL_WAIT * (2**attempt)
                print(f"\n  レート制限 - {wait}秒後にリトライ ({attempt + 1}/{MAX_RETRIES}) ... ", end="", flush=True)
                time.sleep(wait)
        output_file.write_text(text, encoding="utf-8")
        print(f"完了 -> {output_file}")


def run_structured(images: list[Path]) -> None:
    """structured モード: 画像からゲームデータを構造化抽出して JSON 出力する。"""
    from nova_parser.structured import extract_structured

    for img in images:
        output_file = OUTPUT_DIR / f"{img.stem}.structured.json"
        if output_file.exists():
            print(f"スキップ: {output_file}（既に存在します）")
            continue
        print(f"処理中: {img.name} ... ", end="", flush=True)
        for attempt in range(MAX_RETRIES):
            try:
                extraction = extract_structured(img)
                break
            except Exception as exc:
                if not _is_rate_limit_error(exc) or attempt == MAX_RETRIES - 1:
                    raise
                wait = INITIAL_WAIT * (2**attempt)
                print(f"\n  レート制限 - {wait}秒後にリトライ ({attempt + 1}/{MAX_RETRIES}) ... ", end="", flush=True)
                time.sleep(wait)
        output_file.write_text(
            extraction.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"完了 -> {output_file}")


def run_gamedata(images: list[Path]) -> None:
    """gamedata モード: 画像からゲームデータを動的に抽出して JSON 出力する。"""
    import json

    from nova_parser.gamedata import extract_gamedata

    for img in images:
        output_file = OUTPUT_DIR / f"{img.stem}.gamedata.json"
        if output_file.exists():
            print(f"スキップ: {output_file}（既に存在します）")
            continue
        print(f"処理中: {img.name} ... ", end="", flush=True)
        for attempt in range(MAX_RETRIES):
            try:
                result = extract_gamedata(img)
                break
            except Exception as exc:
                if not _is_rate_limit_error(exc) or attempt == MAX_RETRIES - 1:
                    raise
                wait = INITIAL_WAIT * (2**attempt)
                print(f"\n  レート制限 - {wait}秒後にリトライ ({attempt + 1}/{MAX_RETRIES}) ... ", end="", flush=True)
                time.sleep(wait)
        output_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"完了 -> {output_file}")


def run_schema(images: list[Path]) -> None:
    """schema モード: 画像からゲームデータの型名とフィールド名のみを抽出して TSV 出力する。"""
    from nova_parser.gamedata import extract_schema

    for img in images:
        output_file = OUTPUT_DIR / f"{img.stem}.schema.tsv"
        if output_file.exists():
            print(f"スキップ: {output_file}（既に存在します）")
            continue
        print(f"処理中: {img.name} ... ", end="", flush=True)
        for attempt in range(MAX_RETRIES):
            try:
                result = extract_schema(img)
                break
            except Exception as exc:
                if not _is_rate_limit_error(exc) or attempt == MAX_RETRIES - 1:
                    raise
                wait = INITIAL_WAIT * (2**attempt)
                print(f"\n  レート制限 - {wait}秒後にリトライ ({attempt + 1}/{MAX_RETRIES}) ... ", end="", flush=True)
                time.sleep(wait)
        lines = []
        for t in result.get("types", []):
            fields = [t["type_name"], *t["fields"]]
            lines.append("\t".join(fields))
        output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"完了 -> {output_file}")


def _gamedata_to_tsv(result: dict) -> str:
    """ゲームデータ dict を同種パターンごとの TSV 文字列に変換する。"""
    blocks: list[str] = []
    for t in result.get("types", []):
        type_name = t["type_name"]
        items = t.get("items", [])
        if not items:
            continue
        # 全アイテムからフィールド名を収集（出現順を保持）
        field_names: list[str] = []
        seen: set[str] = set()
        for item in items:
            for key in item:
                if key not in seen:
                    field_names.append(key)
                    seen.add(key)
        header = f"## {type_name}\n" + "\t".join(field_names)
        rows = ["\t".join(str(item.get(f, "")) for f in field_names) for item in items]
        blocks.append(header + "\n" + "\n".join(rows))
    return "\n\n".join(blocks) + "\n" if blocks else ""


def run_docai(images: list[Path]) -> None:
    """docai モード: Document AI で OCR → Gemini で構造化抽出 → TSV 出力。"""
    from nova_parser.documentai import extract_docai

    for img in images:
        output_file = OUTPUT_DIR / f"{img.stem}.docai.tsv"
        if output_file.exists():
            print(f"スキップ: {output_file}（既に存在します）")
            continue
        print(f"処理中: {img.name} ... ", end="", flush=True)
        for attempt in range(MAX_RETRIES):
            try:
                result = extract_docai(img)
                break
            except Exception as exc:
                if not _is_rate_limit_error(exc) or attempt == MAX_RETRIES - 1:
                    raise
                wait = INITIAL_WAIT * (2**attempt)
                print(f"\n  レート制限 - {wait}秒後にリトライ ({attempt + 1}/{MAX_RETRIES}) ... ", end="", flush=True)
                time.sleep(wait)
        tsv_text = _gamedata_to_tsv(result)
        output_file.write_text(tsv_text, encoding="utf-8")
        print(f"完了 -> {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="画像ファイルを Gemini / Document AI で OCR / 構造化抽出する。",
    )
    parser.add_argument(
        "--mode",
        choices=["plain", "structured", "gamedata", "schema", "docai"],
        default="plain",
        help="出力モード: plain=Markdown OCR, structured=JSON 構造化抽出, "
        "gamedata=動的ゲームデータ抽出, schema=型名・フィールド名のみ抽出, "
        "docai=Document AI OCR+構造化TSV（デフォルト: plain）",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="処理する画像ファイルのパス（省略時は Images/ 内の全画像を処理）",
    )
    args = parser.parse_args()

    images = resolve_images(args.files)

    if not images:
        print(f"{IMAGES_DIR}/ に画像ファイルが見つかりません。")
        return

    print(f"{len(images)} 件の画像を処理します。（モード: {args.mode}）\n")

    OUTPUT_DIR.mkdir(exist_ok=True)

    if args.mode == "plain":
        run_plain(images)
    elif args.mode == "structured":
        run_structured(images)
    elif args.mode == "gamedata":
        run_gamedata(images)
    elif args.mode == "docai":
        run_docai(images)
    else:
        run_schema(images)

    print(f"\n全ての結果を {OUTPUT_DIR}/ に保存しました。")


if __name__ == "__main__":
    main()
