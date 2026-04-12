"""docai モード: Document AI で OCR し、Gemini で構造化抽出する。"""

import io
import os
from pathlib import Path

from google.cloud import documentai_v1 as documentai

from nova_parser.ocr import MIME_TYPES, generate_json
from nova_parser.perf import tracker
from nova_parser.prompts import DOCAI_EXTRACT_PROMPT, SCHEMA_EXTRACT_PROMPT

DOCAI_PAGE_LIMIT = 15


def get_processor_name() -> str:
    """環境変数から Document AI プロセッサのリソース名を取得する。"""
    name = os.environ.get("DOCUMENT_AI_PROCESSOR")
    if not name:
        msg = (
            "環境変数 DOCUMENT_AI_PROCESSOR が設定されていません。\n"
            "例: projects/PROJECT_NUMBER/locations/LOCATION/processors/PROCESSOR_ID"
        )
        raise RuntimeError(msg)
    return name


def _find_docai_credentials_file() -> Path | None:
    """プロジェクト内の Document AI サービスアカウントキーを探す。"""
    candidates = [
        Path(__file__).resolve().parents[2] / ".secrets" / "docai-sa.json",
        Path.cwd() / ".secrets" / "docai-sa.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _get_documentai_client() -> documentai.DocumentProcessorServiceClient:
    """Document AI クライアントを初期化する。

    GOOGLE_APPLICATION_CREDENTIALS が有効なファイルを指していればそれを使い、
    存在しない場合はプロジェクト内の .secrets/docai-sa.json にフォールバックする。
    """
    creds_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_file and Path(creds_file).exists():
        return documentai.DocumentProcessorServiceClient()

    fallback = _find_docai_credentials_file()
    if fallback:
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_file(str(fallback))
        return documentai.DocumentProcessorServiceClient(credentials=credentials)

    return documentai.DocumentProcessorServiceClient()


def _split_pdf(pdf_bytes: bytes, chunk_size: int = DOCAI_PAGE_LIMIT) -> list[bytes]:
    """PDF を chunk_size ページごとに分割し、各チャンクのバイト列を返す。"""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(pdf_bytes))
    total = len(reader.pages)
    if total <= chunk_size:
        return [pdf_bytes]

    chunks: list[bytes] = []
    for start in range(0, total, chunk_size):
        writer = PdfWriter()
        for page in reader.pages[start : start + chunk_size]:
            writer.add_page(page)
        buf = io.BytesIO()
        writer.write(buf)
        chunks.append(buf.getvalue())
    return chunks


def _process_single_document(
    client: documentai.DocumentProcessorServiceClient,
    processor_name: str,
    content: bytes,
    mime_type: str,
) -> documentai.Document:
    """Document AI で単一ドキュメントを処理し、Document オブジェクトを返す。"""
    raw_document = documentai.RawDocument(content=content, mime_type=mime_type)
    request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)
    result = client.process_document(request=request)
    return result.document


def _ocr_single_document(
    client: documentai.DocumentProcessorServiceClient,
    processor_name: str,
    content: bytes,
    mime_type: str,
) -> str:
    """Document AI で単一ドキュメントを OCR し、テキストを返す。"""
    return _process_single_document(client, processor_name, content, mime_type).text


def process_image_with_documentai(image_path: Path) -> documentai.Document:
    """画像を Document AI で処理し、完全な Document オブジェクトを返す。

    PDF は非対応（ピクセル座標での切り出しに画像が必要なため）。
    """
    mime_type = MIME_TYPES[image_path.suffix.lower()]
    if mime_type == "application/pdf":
        msg = "process_image_with_documentai は PDF に対応していません。画像ファイルを指定してください。"
        raise ValueError(msg)

    processor_name = get_processor_name()
    client = _get_documentai_client()
    return _process_single_document(client, processor_name, image_path.read_bytes(), mime_type)


def ocr_with_documentai(image_path: Path, *, show_progress: bool = True) -> str:
    """Document AI で画像/PDF を OCR し、テキストを返す。

    PDF が Document AI のページ上限を超える場合は自動的に分割して処理する。
    """
    processor_name = get_processor_name()
    client = _get_documentai_client()
    mime_type = MIME_TYPES[image_path.suffix.lower()]
    file_content = image_path.read_bytes()

    with tracker.timer("DocAI OCR", str(image_path)):
        if mime_type == "application/pdf":
            chunks = _split_pdf(file_content)
            if len(chunks) > 1 and show_progress:
                print(f"({len(chunks)} チャンクに分割) ", end="", flush=True)
            texts = [_ocr_single_document(client, processor_name, chunk, mime_type) for chunk in chunks]
            text = "\n".join(texts)
        else:
            text = _ocr_single_document(client, processor_name, file_content, mime_type)

    # Document AI は「N◎VA」を「NOVA」として認識するため補正する
    text = text.replace("NOVA", "N◎VA")
    return text


def extract_gamedata_from_text(ocr_text: str) -> dict:
    """Gemini を使って OCR テキストからゲームデータを構造化抽出する。"""
    result = generate_json([DOCAI_EXTRACT_PROMPT + ocr_text])
    if isinstance(result, list):
        result = {"types": result}
    return result


def extract_with_schema(image_path: Path, schema: dict, *, show_progress: bool = True) -> dict:
    """Document AI OCR → スキーマ準拠で Gemini 構造化抽出する。"""
    ocr_text = ocr_with_documentai(image_path, show_progress=show_progress)

    schema_section = "\n".join(f"- {t['type_name']}: {', '.join(t['fields'])}" for t in schema["types"])
    prompt = SCHEMA_EXTRACT_PROMPT.format(schema_section=schema_section, ocr_text=ocr_text)

    with tracker.timer("Gemini JSON", str(image_path)):
        return generate_json([prompt])


def extract_docai(image_path: Path, *, show_progress: bool = True) -> dict:
    """Document AI で OCR → Gemini で構造化抽出のパイプラインを実行する。"""
    ocr_text = ocr_with_documentai(image_path, show_progress=show_progress)
    with tracker.timer("Gemini JSON", str(image_path)):
        result = extract_gamedata_from_text(ocr_text)
    return {**result, "source_file": image_path.name}
