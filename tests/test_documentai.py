"""nova_parser.documentai モジュールのユニットテスト。"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

import nova_parser.documentai as documentai_mod
import nova_parser.perf as perf_mod
from nova_parser.documentai import (
    _get_documentai_client,
    _split_pdf,
    extract_docai,
    extract_gamedata_from_text,
    get_processor_name,
    ocr_with_documentai,
    process_image_with_documentai,
)
from tests.conftest import FakeDocAIClient, FakeDocAIDocument


@pytest.fixture(autouse=True)
def _reset_perf_tracker():
    """ocr_with_documentai / extract_docai が tracker.timer を呼ぶため毎テスト後にリセット。"""
    perf_mod.tracker.reset()
    yield
    perf_mod.tracker.reset()


# ---------------------------------------------------------------------------
# get_processor_name
# ---------------------------------------------------------------------------


def test_get_processor_name_returns_env_value(monkeypatch):
    monkeypatch.setenv("DOCUMENT_AI_PROCESSOR", "projects/p/locations/us/processors/abc")

    assert get_processor_name() == "projects/p/locations/us/processors/abc"


def test_get_processor_name_raises_runtime_error_when_unset(monkeypatch):
    monkeypatch.delenv("DOCUMENT_AI_PROCESSOR", raising=False)

    with pytest.raises(RuntimeError, match="DOCUMENT_AI_PROCESSOR"):
        get_processor_name()


# ---------------------------------------------------------------------------
# _get_documentai_client
# ---------------------------------------------------------------------------


def test_get_documentai_client_uses_application_credentials_when_path_exists(monkeypatch, tmp_path: Path):
    creds = tmp_path / "creds.json"
    creds.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds))

    captured: dict[str, object] = {}

    def fake_ctor(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "client-default-adc"

    monkeypatch.setattr(documentai_mod.documentai, "DocumentProcessorServiceClient", fake_ctor)

    result = _get_documentai_client()

    assert result == "client-default-adc"
    assert captured["args"] == ()
    assert captured["kwargs"] == {}


def test_get_documentai_client_falls_back_to_secrets_file(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    fake_secrets = tmp_path / "docai-sa.json"
    fake_secrets.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(documentai_mod, "_find_docai_credentials_file", lambda: fake_secrets)

    captured: dict[str, object] = {}

    from google.oauth2 import service_account

    def fake_from_file(path):
        captured["creds_path"] = path
        return "fake-credentials"

    monkeypatch.setattr(service_account.Credentials, "from_service_account_file", staticmethod(fake_from_file))

    def fake_ctor(*, credentials):
        captured["credentials"] = credentials
        return "client-with-credentials"

    monkeypatch.setattr(documentai_mod.documentai, "DocumentProcessorServiceClient", fake_ctor)

    result = _get_documentai_client()

    assert result == "client-with-credentials"
    assert captured["creds_path"] == str(fake_secrets)
    assert captured["credentials"] == "fake-credentials"


def test_get_documentai_client_default_when_no_credentials(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(documentai_mod, "_find_docai_credentials_file", lambda: None)

    captured: dict[str, object] = {}

    def fake_ctor(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "client-default"

    monkeypatch.setattr(documentai_mod.documentai, "DocumentProcessorServiceClient", fake_ctor)

    result = _get_documentai_client()

    assert result == "client-default"
    assert captured["kwargs"] == {}


# ---------------------------------------------------------------------------
# _split_pdf
# ---------------------------------------------------------------------------


def _make_pdf_bytes(num_pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_split_pdf_returns_single_chunk_when_under_limit():
    pdf_bytes = _make_pdf_bytes(2)

    chunks = _split_pdf(pdf_bytes, chunk_size=15)

    assert len(chunks) == 1
    assert chunks[0] == pdf_bytes


def test_split_pdf_splits_when_over_limit():
    pdf_bytes = _make_pdf_bytes(3)

    chunks = _split_pdf(pdf_bytes, chunk_size=2)

    assert len(chunks) == 2
    page_counts = [len(PdfReader(io.BytesIO(c)).pages) for c in chunks]
    assert page_counts == [2, 1]


# ---------------------------------------------------------------------------
# process_image_with_documentai
# ---------------------------------------------------------------------------


def test_process_image_with_documentai_calls_client_for_image(monkeypatch, tmp_path: Path):
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    monkeypatch.setenv("DOCUMENT_AI_PROCESSOR", "projects/p/locations/us/processors/abc")

    fake_client = FakeDocAIClient([FakeDocAIDocument(text="hello")])
    monkeypatch.setattr(documentai_mod, "_get_documentai_client", lambda: fake_client)

    result = process_image_with_documentai(image)

    assert result.text == "hello"
    assert len(fake_client.calls) == 1
    request = fake_client.calls[0]["request"]
    assert request.name == "projects/p/locations/us/processors/abc"
    assert request.raw_document.content == b"\x89PNG\r\n\x1a\nfake"
    assert request.raw_document.mime_type == "image/png"


def test_process_image_with_documentai_raises_value_error_for_pdf(tmp_path: Path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    with pytest.raises(ValueError, match="PDF"):
        process_image_with_documentai(pdf)


# ---------------------------------------------------------------------------
# ocr_with_documentai
# ---------------------------------------------------------------------------


def test_ocr_with_documentai_corrects_nova_to_kanji(monkeypatch, tmp_path: Path):
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG fake")
    monkeypatch.setenv("DOCUMENT_AI_PROCESSOR", "p")

    fake_client = FakeDocAIClient([FakeDocAIDocument(text="Hello NOVA world NOVA")])
    monkeypatch.setattr(documentai_mod, "_get_documentai_client", lambda: fake_client)

    result = ocr_with_documentai(image, show_progress=False)

    assert result == "Hello N◎VA world N◎VA"


def test_ocr_with_documentai_concatenates_chunks_for_oversize_pdf(monkeypatch, tmp_path: Path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setenv("DOCUMENT_AI_PROCESSOR", "p")
    monkeypatch.setattr(documentai_mod, "_split_pdf", lambda content: [b"c1", b"c2", b"c3"])

    fake_client = FakeDocAIClient(
        [
            FakeDocAIDocument(text="page1"),
            FakeDocAIDocument(text="page2"),
            FakeDocAIDocument(text="page3"),
        ]
    )
    monkeypatch.setattr(documentai_mod, "_get_documentai_client", lambda: fake_client)

    result = ocr_with_documentai(pdf, show_progress=False)

    assert result == "page1\npage2\npage3"
    assert len(fake_client.calls) == 3


# ---------------------------------------------------------------------------
# extract_gamedata_from_text / extract_docai
# ---------------------------------------------------------------------------


def test_extract_gamedata_from_text_invokes_generate_json_with_prompt(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_generate_json(
        contents,
        *,
        response_json_schema=None,
        result_validator=None,
        failure_artifact=None,
    ):
        captured["contents"] = contents
        captured["failure_artifact"] = failure_artifact
        return {"types": [{"type_name": "X", "items": []}]}

    monkeypatch.setattr(documentai_mod, "generate_json", fake_generate_json)

    result = extract_gamedata_from_text("OCR_TEXT", source_path=Path("/img/foo.png"), output_dir=tmp_path)

    assert result == {"types": [{"type_name": "X", "items": []}]}
    assert isinstance(captured["contents"], list)
    prompt = captured["contents"][0]
    assert prompt.startswith("以下はTRPGルールブック")
    assert prompt.endswith("OCR_TEXT")
    artifact = captured["failure_artifact"]
    assert artifact is not None
    assert artifact.mode == "docai"
    assert artifact.source_path == Path("/img/foo.png")
    assert artifact.ocr_text == "OCR_TEXT"
    assert artifact.output_path == tmp_path / "foo.docai.gemini_json_error.json"


def test_extract_docai_attaches_source_file_name(monkeypatch, tmp_path: Path):
    image = tmp_path / "page42.png"
    image.write_bytes(b"\x89PNG fake")
    monkeypatch.setenv("DOCUMENT_AI_PROCESSOR", "p")

    fake_client = FakeDocAIClient([FakeDocAIDocument(text="some text")])
    monkeypatch.setattr(documentai_mod, "_get_documentai_client", lambda: fake_client)
    monkeypatch.setattr(
        documentai_mod,
        "extract_gamedata_from_text",
        lambda text, *, source_path, output_dir=Path("Output"): {"types": []},
    )

    result = extract_docai(image, show_progress=False, output_dir=tmp_path)

    assert result["source_file"] == "page42.png"
    assert result["types"] == []
