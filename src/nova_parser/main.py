import argparse
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, TypeVar

from dotenv import load_dotenv

from nova_parser.ocr import MIME_TYPES

if False:  # TYPE_CHECKING
    from nova_parser.models import PageExtraction

load_dotenv()


IMAGES_DIR = Path("Images")
OUTPUT_DIR = Path("Output")

MAX_RETRIES = 5
INITIAL_WAIT = 30

T = TypeVar("T")


def resolve_images(file_args: list[str]) -> list[Path]:
    """CLI 引数から画像ファイルリストを解決する。"""
    if file_args:
        images: list[Path] = []
        for f in file_args:
            p = Path(f)
            if not p.exists():
                print(f"エラー: パスが見つかりません: {p}", file=sys.stderr)
                sys.exit(1)
            if p.is_dir():
                dir_images = sorted(
                    child for child in p.iterdir() if child.is_file() and child.suffix.lower() in MIME_TYPES
                )
                if not dir_images:
                    print(
                        f"警告: ディレクトリに対象ファイルが見つかりません: {p}",
                        file=sys.stderr,
                    )
                images.extend(dir_images)
            else:
                if p.suffix.lower() not in MIME_TYPES:
                    print(
                        f"エラー: サポートされていないファイル形式です: {p.suffix} ({p})",
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


def _validate_parallel_files(parallel_files: int) -> int:
    """並列実行数の妥当性を検証する。"""
    if parallel_files < 1:
        msg = "parallel_files は 1 以上である必要があります。"
        raise ValueError(msg)
    return parallel_files


def _run_with_retries(action: Callable[[], T], *, on_retry: Callable[[int, int], None] | None = None) -> T:
    """429 レート制限時に指数バックオフ付きで処理を再試行する。"""
    for attempt in range(MAX_RETRIES):
        try:
            return action()
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt == MAX_RETRIES - 1:
                raise
            wait = INITIAL_WAIT * (2**attempt)
            if on_retry is not None:
                on_retry(attempt + 1, wait)
            time.sleep(wait)

    msg = "リトライ処理が不正な状態で終了しました。"
    raise RuntimeError(msg)


def _atomic_write_text(output_file: Path, text: str) -> None:
    """同一ディレクトリ上の一時ファイル経由でテキストを書き込む。"""
    output_file.parent.mkdir(exist_ok=True)
    tmp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output_file.parent,
            prefix=f".{output_file.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_file.write(text)
            tmp_path = Path(tmp_file.name)
        tmp_path.replace(output_file)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def _ensure_unique_docai_outputs(work_items: list[tuple[int, Path, Path]]) -> None:
    """docai モードの出力先衝突を事前に検出する。"""
    output_to_inputs: dict[Path, list[Path]] = {}

    for _, img, output_file in work_items:
        output_to_inputs.setdefault(output_file, []).append(img)

    collisions = {output_file: inputs for output_file, inputs in output_to_inputs.items() if len(inputs) > 1}
    if not collisions:
        return

    details = "; ".join(
        f"{output_file.name} <- {', '.join(str(path) for path in inputs)}"
        for output_file, inputs in sorted(collisions.items(), key=lambda item: item[0].name)
    )
    msg = f"docai モードで出力ファイル名が衝突します: {details}"
    raise ValueError(msg)


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


def _parse_docai_tsvs(files: list[Path] | None = None) -> dict:
    """docai TSV ファイルからスキーマ提案を生成する。

    files を指定した場合はそのファイルのみ、省略時は Output/*.docai*.tsv を走査する。
    """
    tsv_files = sorted(files) if files else sorted(OUTPUT_DIR.glob("*.docai*.tsv"))
    type_fields: dict[str, list[str]] = {}
    type_source: dict[str, str] = {}

    for tsv_file in tsv_files:
        text = tsv_file.read_text(encoding="utf-8")
        for block in text.split("\n\n"):
            lines = [line for line in block.strip().splitlines() if line.strip()]
            if not lines or not lines[0].startswith("## "):
                continue
            type_name = lines[0][3:].strip()
            if len(lines) < 2:
                continue
            fields = lines[1].split("\t")
            if type_name not in type_fields:
                type_fields[type_name] = list(fields)
                type_source[type_name] = tsv_file.name
            else:
                existing = type_fields[type_name]
                seen = set(existing)
                for f in fields:
                    if f not in seen:
                        existing.append(f)
                        seen.add(f)

    return {"types": [{"type_name": tn, "fields": type_fields[tn], "source": type_source[tn]} for tn in type_fields]}


def run_schema_propose(files: list[Path] | None = None) -> None:
    """schema_propose モード: docai TSV からスキーマ提案を生成する。"""
    import json

    result = _parse_docai_tsvs(files)
    output_file = OUTPUT_DIR / "schema_proposal.json"
    output_file.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"スキーマ提案を生成しました: {output_file}（{len(result['types'])} 型）")


def _normalize_dash(value: str) -> str:
    """値が単独のダッシュ類文字の場合、半角ハイフンに統一する。"""
    if value in {"一", "－", "ー", "−", "-", "–", "—", "―"}:
        return "-"
    return value


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
        rows = ["\t".join(_normalize_dash(str(item.get(f, ""))) for f in field_names) for item in items]
        blocks.append(header + "\n" + "\n".join(rows))
    return "\n\n".join(blocks) + "\n" if blocks else ""


def _structured_to_tsv(extraction: "PageExtraction") -> str:
    """PageExtraction を TSV 文字列に変換する。"""
    blocks: list[str] = []

    if extraction.organizations:
        header = "## 組織\nname\tclassification\tsub_organizations\theadquarters\tdescription"
        rows = []
        for o in extraction.organizations:
            rows.append(
                "\t".join(
                    [
                        o.name,
                        o.classification,
                        ", ".join(o.sub_organizations),
                        o.headquarters,
                        o.description,
                    ]
                )
            )
        blocks.append(header + "\n" + "\n".join(rows))

    if extraction.skills:
        fields = [
            "name",
            "ruby",
            "prerequisite",
            "max_level",
            "timing",
            "target",
            "range",
            "target_value",
            "opposed",
            "description",
        ]
        header = "## 技能\n" + "\t".join(fields)
        rows = [
            "\t".join(_normalize_dash(str(getattr(s, f) if getattr(s, f) is not None else "")) for f in fields)
            for s in extraction.skills
        ]
        blocks.append(header + "\n" + "\n".join(rows))

    if extraction.equipment:
        fields = [
            "name",
            "ruby",
            "category",
            "type",
            "purchase",
            "concealment",
            "defense_s",
            "defense_p",
            "defense_i",
            "restriction",
            "electric_restriction",
            "slot",
            "description",
        ]
        header = "## 装備\n" + "\t".join(fields)
        rows = [
            "\t".join(_normalize_dash(str(getattr(e, f) if getattr(e, f) is not None else "")) for f in fields)
            for e in extraction.equipment
        ]
        blocks.append(header + "\n" + "\n".join(rows))

    if extraction.rules:
        header = "## ルール\ndepth\ttitle\tbody"
        rows: list[str] = []

        def _flatten_rules(rules: list, depth: int = 0) -> None:
            for r in rules:
                rows.append(f"{depth}\t{r.title}\t{r.body}")
                _flatten_rules(r.sub_sections, depth + 1)

        _flatten_rules(extraction.rules)
        blocks.append(header + "\n" + "\n".join(rows))

    return "\n\n".join(blocks) + "\n" if blocks else ""


def run_structured_tsv(images: list[Path]) -> None:
    """structured_tsv モード: 画像からゲームデータを構造化抽出して TSV 出力する。"""
    from nova_parser.structured import extract_structured

    for img in images:
        output_file = OUTPUT_DIR / f"{img.stem}.structured.tsv"
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
        tsv_text = _structured_to_tsv(extraction)
        output_file.write_text(tsv_text, encoding="utf-8")
        print(f"完了 -> {output_file}")


def run_docai_plain(images: list[Path]) -> None:
    """docai_plain モード: Document AI で OCR → Markdown として出力する。"""
    from nova_parser.documentai import ocr_with_documentai

    for img in images:
        output_file = OUTPUT_DIR / f"{img.stem}.docai_plain.md"
        if output_file.exists():
            print(f"スキップ: {output_file}（既に存在します）")
            continue
        print(f"処理中: {img.name} ... ", end="", flush=True)
        for attempt in range(MAX_RETRIES):
            try:
                text = ocr_with_documentai(img)
                break
            except Exception as exc:
                if not _is_rate_limit_error(exc) or attempt == MAX_RETRIES - 1:
                    raise
                wait = INITIAL_WAIT * (2**attempt)
                print(f"\n  レート制限 - {wait}秒後にリトライ ({attempt + 1}/{MAX_RETRIES}) ... ", end="", flush=True)
                time.sleep(wait)
        output_file.write_text(text, encoding="utf-8")
        print(f"完了 -> {output_file}")


def _append_to_tsv(
    type_data: dict,
    schema_fields: list[str] | None,
    source_name: str,
    *,
    matched: bool,
) -> None:
    """抽出結果を型別 TSV ファイルに追記する。"""
    type_name = type_data["type_name"]
    items = type_data.get("items", [])
    if not items:
        return

    prefix = "" if matched else "none_"
    tsv_path = OUTPUT_DIR / f"{prefix}{type_name}.tsv"

    # フィールド決定
    if schema_fields is not None:
        fields = list(schema_fields)
    else:
        fields: list[str] = []
        seen: set[str] = set()
        for item in items:
            for key in item:
                if key not in seen:
                    fields.append(key)
                    seen.add(key)

    file_exists = tsv_path.exists() and tsv_path.stat().st_size > 0
    with tsv_path.open("a", encoding="utf-8") as f:
        if not file_exists:
            f.write("\t".join(fields + ["source"]) + "\n")
        for item in items:
            row = [_normalize_dash(str(item.get(field, ""))) for field in fields] + [source_name]
            f.write("\t".join(row) + "\n")


def run_extract(images: list[Path], schema_path: Path, *, parallel_files: int = 1) -> None:
    """extract モード: スキーマに従って Document AI OCR → Gemini 構造化抽出 → 型別 TSV。"""
    import json

    from nova_parser.documentai import extract_with_schema

    parallel_files = _validate_parallel_files(parallel_files)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_fields = {t["type_name"]: t["fields"] for t in schema["types"]}

    if parallel_files == 1:
        for img in images:
            print(f"処理中: {img.name} ... ", end="", flush=True)
            result = _run_with_retries(
                lambda img=img: extract_with_schema(img, schema),
                on_retry=lambda attempt, wait: print(
                    f"\n  レート制限 - {wait}秒後にリトライ ({attempt}/{MAX_RETRIES}) ... ",
                    end="",
                    flush=True,
                ),
            )
            for t in result.get("matched_types", []):
                _append_to_tsv(t, schema_fields.get(t["type_name"]), img.name, matched=True)
            for t in result.get("unmatched_types", []):
                _append_to_tsv(t, None, img.name, matched=False)
            print("完了")
        return

    results_by_index: dict[int, dict] = {}
    work_items = list(enumerate(images))

    for _, img in work_items:
        print(f"処理中: {img.name} ...")

    with ThreadPoolExecutor(max_workers=parallel_files) as executor:
        future_to_job = {
            executor.submit(
                _run_with_retries,
                lambda img=img: extract_with_schema(img, schema, show_progress=False),
            ): (index, img)
            for index, img in work_items
        }

        try:
            for future in as_completed(future_to_job):
                index, img = future_to_job[future]
                result = future.result()
                results_by_index[index] = result
                print(f"完了: {img.name}")
        except Exception:
            for pending in future_to_job:
                pending.cancel()
            raise

    for index, img in work_items:
        result = results_by_index[index]
        for t in result.get("matched_types", []):
            _append_to_tsv(t, schema_fields.get(t["type_name"]), img.name, matched=True)
        for t in result.get("unmatched_types", []):
            _append_to_tsv(t, None, img.name, matched=False)


def run_crop(images: list[Path], *, min_card_area: float, max_card_area: float, padding: int) -> None:
    """crop モード: Gemini Vision でカード領域を検出・切り出す（フォールバック: Document AI）。"""
    import json

    from PIL import Image

    from nova_parser.crop import crop_cards, detect_and_crop_cards, detect_cards_with_gemini

    for img in images:
        mime = MIME_TYPES.get(img.suffix.lower(), "")
        if mime == "application/pdf":
            print(f"スキップ: {img.name}（crop モードは PDF に対応していません）")
            continue

        print(f"処理中: {img.name} ... ", end="", flush=True)
        for attempt in range(MAX_RETRIES):
            try:
                # Gemini Vision でカード検出を試みる
                regions = detect_cards_with_gemini(img)
                if regions:
                    pil_image = Image.open(img)
                    results = crop_cards(pil_image, regions, padding)
                    print("(Gemini) ", end="", flush=True)
                else:
                    # フォールバック: Document AI ベースの検出
                    from nova_parser.documentai import process_image_with_documentai

                    print("(Document AI フォールバック) ", end="", flush=True)
                    document = process_image_with_documentai(img)
                    pil_image = Image.open(img)
                    results = detect_and_crop_cards(
                        pil_image,
                        document,
                        min_area_ratio=min_card_area,
                        max_area_ratio=max_card_area,
                        padding=padding,
                    )
                break
            except Exception as exc:
                if not _is_rate_limit_error(exc) or attempt == MAX_RETRIES - 1:
                    raise
                wait = INITIAL_WAIT * (2**attempt)
                print(f"\n  レート制限 - {wait}秒後にリトライ ({attempt + 1}/{MAX_RETRIES}) ... ", end="", flush=True)
                time.sleep(wait)

        if not results:
            print("カード領域が検出されませんでした。")
            continue

        cards_meta: list[dict] = []
        for i, (region, cropped_img) in enumerate(results, 1):
            crop_file = OUTPUT_DIR / f"{img.stem}.crop_{i:03d}.png"
            cropped_img.save(crop_file)
            cards_meta.append(
                {
                    "index": i,
                    "left": region.left,
                    "top": region.top,
                    "right": region.right,
                    "bottom": region.bottom,
                    "confidence": round(region.confidence, 4),
                    "text_snippet": region.text_snippet,
                    "file": crop_file.name,
                }
            )

        meta_file = OUTPUT_DIR / f"{img.stem}.crop.json"
        meta_file.write_text(
            json.dumps({"source": img.name, "cards": cards_meta}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"完了 -> {len(results)} 件のカード領域を検出 ({meta_file})")


def run_docai(images: list[Path], *, parallel_files: int = 1) -> None:
    """docai モード: Document AI で OCR → Gemini で構造化抽出 → TSV 出力。"""
    from nova_parser.documentai import extract_docai

    parallel_files = _validate_parallel_files(parallel_files)

    work_items: list[tuple[int, Path, Path]] = []
    for index, img in enumerate(images):
        output_file = OUTPUT_DIR / f"{img.stem}.docai.tsv"
        if output_file.exists():
            print(f"スキップ: {output_file}（既に存在します）")
            continue
        work_items.append((index, img, output_file))

    _ensure_unique_docai_outputs(work_items)

    if parallel_files == 1:
        for _, img, output_file in work_items:
            print(f"処理中: {img.name} ... ", end="", flush=True)
            result = _run_with_retries(
                lambda img=img: extract_docai(img),
                on_retry=lambda attempt, wait: print(
                    f"\n  レート制限 - {wait}秒後にリトライ ({attempt}/{MAX_RETRIES}) ... ",
                    end="",
                    flush=True,
                ),
            )
            tsv_text = _gamedata_to_tsv(result)
            _atomic_write_text(output_file, tsv_text)
            print(f"完了 -> {output_file}")
        return

    for _, img, _ in work_items:
        print(f"処理中: {img.name} ...")

    with ThreadPoolExecutor(max_workers=parallel_files) as executor:
        future_to_job = {
            executor.submit(
                _run_with_retries,
                lambda img=img: extract_docai(img, show_progress=False),
            ): (index, img, output_file)
            for index, img, output_file in work_items
        }

        try:
            for future in as_completed(future_to_job):
                _, img, output_file = future_to_job[future]
                result = future.result()
                tsv_text = _gamedata_to_tsv(result)
                _atomic_write_text(output_file, tsv_text)
                print(f"完了: {img.name} -> {output_file}")
        except Exception:
            for pending in future_to_job:
                pending.cancel()
            raise


def main():
    parser = argparse.ArgumentParser(
        description="画像ファイルを Gemini / Document AI で OCR / 構造化抽出する。",
    )
    parser.add_argument(
        "--mode",
        choices=[
            "plain",
            "structured",
            "structured_tsv",
            "gamedata",
            "schema",
            "docai",
            "docai_plain",
            "schema_propose",
            "extract",
            "crop",
        ],
        default="plain",
        help="出力モード: plain=Markdown OCR, structured=JSON 構造化抽出, "
        "structured_tsv=構造化抽出TSV出力, gamedata=動的ゲームデータ抽出, "
        "schema=型名・フィールド名のみ抽出, docai=Document AI OCR+構造化TSV, "
        "docai_plain=Document AI OCRのみMarkdown出力, "
        "schema_propose=docai TSVからスキーマ提案生成, "
        "extract=スキーマ準拠で型別TSV抽出, "
        "crop=Document AI OCRのブロック座標でカード領域を切り出し（デフォルト: plain）",
    )
    parser.add_argument(
        "--schema",
        type=str,
        default=None,
        help="スキーマ定義ファイルのパス（extract モード時に必須）",
    )
    parser.add_argument(
        "--parallel-files",
        type=int,
        default=1,
        help="docai / extract モードで同時に処理するファイル数（デフォルト: 1）",
    )
    parser.add_argument(
        "--min-card-area",
        type=float,
        default=0.05,
        help="crop モード: カード最小面積比率（デフォルト: 0.05）",
    )
    parser.add_argument(
        "--max-card-area",
        type=float,
        default=0.80,
        help="crop モード: カード最大面積比率（デフォルト: 0.80）",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=15,
        help="crop モード: クロップ時のパディング px（デフォルト: 15）",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="処理する画像/PDFファイルまたはディレクトリのパス"
        "（ディレクトリ指定時は直下の画像を処理。省略時は Images/ 内の全画像を処理）",
    )
    args = parser.parse_args()

    if args.mode == "extract" and not args.schema:
        parser.error("extract モードでは --schema の指定が必須です。")
    if args.schema and not Path(args.schema).exists():
        parser.error(f"スキーマファイルが見つかりません: {args.schema}")
    if args.parallel_files < 1:
        parser.error("--parallel-files は 1 以上で指定してください。")

    OUTPUT_DIR.mkdir(exist_ok=True)

    # schema_propose は画像ではなく TSV ファイルを受け取る
    if args.mode == "schema_propose":
        tsv_files = [Path(f) for f in args.files] if args.files else None
        run_schema_propose(tsv_files)
        print(f"\n全ての結果を {OUTPUT_DIR}/ に保存しました。")
        return

    images = resolve_images(args.files)

    if not images:
        print("対象ファイルが見つかりません。")
        return

    print(f"{len(images)} 件のファイルを処理します。（モード: {args.mode}）\n")

    if args.mode == "plain":
        run_plain(images)
    elif args.mode == "structured":
        run_structured(images)
    elif args.mode == "structured_tsv":
        run_structured_tsv(images)
    elif args.mode == "gamedata":
        run_gamedata(images)
    elif args.mode == "docai":
        run_docai(images, parallel_files=args.parallel_files)
    elif args.mode == "docai_plain":
        run_docai_plain(images)
    elif args.mode == "extract":
        run_extract(images, Path(args.schema), parallel_files=args.parallel_files)
    elif args.mode == "crop":
        run_crop(images, min_card_area=args.min_card_area, max_card_area=args.max_card_area, padding=args.padding)
    else:
        run_schema(images)

    print(f"\n全ての結果を {OUTPUT_DIR}/ に保存しました。")


if __name__ == "__main__":
    main()
