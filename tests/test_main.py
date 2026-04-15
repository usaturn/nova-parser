"""main モジュールのユニットテスト。"""

import sys
import time
from pathlib import Path

import pytest

import nova_parser.documentai as documentai_mod
import nova_parser.gamedata as gamedata_mod
import nova_parser.main as main_mod
import nova_parser.ocr as ocr_mod
import nova_parser.perf as perf_mod


def _make_images(tmp_path: Path, *names: str) -> list[Path]:
    """テスト用のダミー画像ファイルを作成する。"""
    images: list[Path] = []
    for name in names:
        image_path = tmp_path / name
        image_path.write_bytes(b"dummy")
        images.append(image_path)
    return images


def _write_schema(schema_path: Path) -> None:
    """extract テスト用の最小スキーマを書き出す。"""
    schema_path.write_text(
        """
{
  "types": [
    {
      "type_name": "Card",
      "fields": ["name", "power"]
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )


def _read_output_texts(output_dir: Path, pattern: str) -> dict[str, str]:
    """出力ディレクトリ内の対象ファイル内容を読み込む。"""
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(output_dir.glob(pattern))}


@pytest.fixture(autouse=True)
def reset_perf_tracker():
    perf_mod.tracker.reset()
    yield
    perf_mod.tracker.reset()


def test_run_docai_parallel_matches_sequential(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "alpha.png", "beta.png")

    seq_calls: list[tuple[str, bool]] = []

    def fake_extract_docai_sequential(
        image_path: Path,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        seq_calls.append((image_path.name, show_progress))
        return {
            "types": [
                {
                    "type_name": "Card",
                    "items": [{"name": image_path.stem, "power": str(len(image_path.stem))}],
                }
            ],
            "source_file": image_path.name,
        }

    monkeypatch.setattr(documentai_mod, "extract_docai", fake_extract_docai_sequential)
    seq_output = tmp_path / "seq_output"
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", seq_output)
    seq_output.mkdir()
    main_mod.run_docai(images, parallel_files=1)

    seq_texts = _read_output_texts(seq_output, "*.docai.tsv")

    par_calls: list[tuple[str, bool]] = []

    def fake_extract_docai_parallel(
        image_path: Path,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        par_calls.append((image_path.name, show_progress))
        if image_path.stem == "alpha":
            time.sleep(0.05)
        return {
            "types": [
                {
                    "type_name": "Card",
                    "items": [{"name": image_path.stem, "power": str(len(image_path.stem))}],
                }
            ],
            "source_file": image_path.name,
        }

    monkeypatch.setattr(documentai_mod, "extract_docai", fake_extract_docai_parallel)
    par_output = tmp_path / "par_output"
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", par_output)
    par_output.mkdir()
    main_mod.run_docai(images, parallel_files=2)

    par_texts = _read_output_texts(par_output, "*.docai.tsv")

    assert seq_texts == par_texts
    assert seq_calls == [("alpha.png", True), ("beta.png", True)]
    assert sorted(par_calls) == [("alpha.png", False), ("beta.png", False)]


def test_run_docai_skips_existing_outputs(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "alpha.png", "beta.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    existing_output = output_dir / "alpha.docai.tsv"
    existing_output.write_text("existing\n", encoding="utf-8")

    called: list[str] = []

    def fake_extract_docai(
        image_path: Path,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        called.append(image_path.name)
        return {
            "types": [
                {
                    "type_name": "Card",
                    "items": [{"name": image_path.stem, "power": "1"}],
                }
            ],
            "source_file": image_path.name,
        }

    monkeypatch.setattr(documentai_mod, "extract_docai", fake_extract_docai)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_docai(images, parallel_files=2)

    assert called == ["beta.png"]
    assert existing_output.read_text(encoding="utf-8") == "existing\n"
    assert (output_dir / "beta.docai.tsv").read_text(encoding="utf-8") == "## Card\nname\tpower\nbeta\t1\n"


def test_run_docai_detects_duplicate_output_targets(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "same.png", "same.jpg")

    def fail_if_called(*args, **kwargs):
        msg = "extract_docai should not be called when output paths collide"
        raise AssertionError(msg)

    monkeypatch.setattr(documentai_mod, "extract_docai", fail_if_called)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", tmp_path / "output")

    with pytest.raises(ValueError, match=r"same\.docai\.tsv"):
        main_mod.run_docai(images, parallel_files=2)


def test_run_docai_allows_duplicate_stems_when_existing_output_skips_all(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "same.png", "same.jpg")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    existing_output = output_dir / "same.docai.tsv"
    existing_output.write_text("existing\n", encoding="utf-8")

    called: list[str] = []

    def fake_extract_docai(
        image_path: Path,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        called.append(image_path.name)
        return {
            "types": [
                {
                    "type_name": "Card",
                    "items": [{"name": image_path.stem, "power": "1"}],
                }
            ],
            "source_file": image_path.name,
        }

    monkeypatch.setattr(documentai_mod, "extract_docai", fake_extract_docai)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_docai(images, parallel_files=2)

    assert called == []
    assert existing_output.read_text(encoding="utf-8") == "existing\n"


def test_run_extract_parallel_matches_sequential(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "first.png", "second.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)

    seq_calls: list[tuple[str, bool]] = []

    def fake_extract_with_schema_sequential(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        seq_calls.append((image_path.name, show_progress))
        return {
            "matched_types": [
                {
                    "type_name": "Card",
                    "items": [{"name": image_path.stem, "power": str(len(image_path.stem))}],
                }
            ],
            "unmatched_types": [
                {
                    "type_name": "Unknown",
                    "items": [{"raw": image_path.stem.upper()}],
                }
            ],
        }

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake_extract_with_schema_sequential)
    seq_output = tmp_path / "seq_extract"
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", seq_output)
    seq_output.mkdir()
    main_mod.run_extract(images, schema_path, parallel_files=1)

    seq_texts = _read_output_texts(seq_output, "*.tsv")

    par_calls: list[tuple[str, bool]] = []

    def fake_extract_with_schema_parallel(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        par_calls.append((image_path.name, show_progress))
        if image_path.name == "first.png":
            time.sleep(0.05)
        return {
            "matched_types": [
                {
                    "type_name": "Card",
                    "items": [{"name": image_path.stem, "power": str(len(image_path.stem))}],
                }
            ],
            "unmatched_types": [
                {
                    "type_name": "Unknown",
                    "items": [{"raw": image_path.stem.upper()}],
                }
            ],
        }

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake_extract_with_schema_parallel)
    par_output = tmp_path / "par_extract"
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", par_output)
    par_output.mkdir()
    main_mod.run_extract(images, schema_path, parallel_files=2)

    par_texts = _read_output_texts(par_output, "*.tsv")

    assert seq_texts == par_texts
    assert seq_texts["Card.tsv"] == (
        "name\tpower\tsource\n"
        "first\t5\tfirst.png\n"
        "second\t6\tsecond.png\n"
    )
    assert seq_calls == [("first.png", True), ("second.png", True)]
    assert sorted(par_calls) == [("first.png", False), ("second.png", False)]


def test_run_extract_failure_does_not_commit(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "first.png", "second.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    existing_card = output_dir / "Card.tsv"
    existing_text = "name\tpower\tsource\nold\t9\told.png\n"
    existing_card.write_text(existing_text, encoding="utf-8")

    append_calls = 0
    original_append = main_mod._append_to_tsv

    def tracking_append(*args, **kwargs):
        nonlocal append_calls
        append_calls += 1
        return original_append(*args, **kwargs)

    def fake_extract_with_schema(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        if image_path.name == "second.png":
            raise RuntimeError("boom")
        time.sleep(0.05)
        return {
            "matched_types": [
                {
                    "type_name": "Card",
                    "items": [{"name": image_path.stem, "power": "1"}],
                }
            ],
            "unmatched_types": [],
        }

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake_extract_with_schema)
    monkeypatch.setattr(main_mod, "_append_to_tsv", tracking_append)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    with pytest.raises(RuntimeError, match="boom"):
        main_mod.run_extract(images, schema_path, parallel_files=2)

    assert append_calls == 0
    assert existing_card.read_text(encoding="utf-8") == existing_text
    assert not (output_dir / "none_Unknown.tsv").exists()


def test_run_extract_reports_retry_timings(monkeypatch, tmp_path, capsys):
    image_path = _make_images(tmp_path, "retry.png")[0]
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    attempts = 0
    sleep_calls: list[int] = []

    def fake_extract_with_schema(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        nonlocal attempts
        attempts += 1
        perf_mod.tracker.record("DocAI OCR", str(image_path), 90.0)
        if attempts == 1:
            perf_mod.tracker.record("Gemini JSON", str(image_path), 40.0, outcome="error")
            raise RuntimeError("429")
        perf_mod.tracker.record("Gemini JSON", str(image_path), 70.0)
        return {
            "matched_types": [
                {
                    "type_name": "Card",
                    "items": [{"name": image_path.stem, "power": "7"}],
                }
            ],
            "unmatched_types": [],
        }

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake_extract_with_schema)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(main_mod, "INITIAL_WAIT", 1)
    monkeypatch.setattr(main_mod, "_is_rate_limit_error", lambda exc: str(exc) == "429")
    monkeypatch.setattr(main_mod.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    main_mod.run_extract([image_path], schema_path, parallel_files=1)

    captured = capsys.readouterr().out
    assert "retry.png: レート制限 - attempt 1/5 失敗: Gemini JSON 40.0s" in captured
    assert "retry.png: retry wait 1.0s" in captured
    assert "DocAI OCR 実 180.0s / 成功 180.0s (2回, 0失敗)" in captured
    assert "Gemini JSON 実 110.0s / 成功 70.0s (2回, 1失敗)" in captured
    assert "retry wait 1.0s, 実計 291.0s, 成功計 250.0s" in captured
    assert sleep_calls == [1]
    assert (output_dir / "Card.tsv").read_text(encoding="utf-8") == "name\tpower\tsource\nretry\t7\tretry.png\n"


def test_run_extract_does_not_retry_json_errors(monkeypatch, tmp_path):
    image_path = _make_images(tmp_path, "invalid.png")[0]
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    attempts = 0

    def fake_extract_with_schema(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        nonlocal attempts
        attempts += 1
        raise ocr_mod.GeminiJSONError("bad json")

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake_extract_with_schema)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    with pytest.raises(ocr_mod.GeminiJSONError, match="bad json"):
        main_mod.run_extract([image_path], schema_path, parallel_files=1)

    assert attempts == 1
    assert not (output_dir / "Card.tsv").exists()


def test_run_schema_omits_empty_perf_summary(monkeypatch, tmp_path, capsys):
    image_path = _make_images(tmp_path, "alpha.png")[0]
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(
        gamedata_mod,
        "extract_schema",
        lambda image_path: {"types": [{"type_name": "Card", "fields": ["name"]}]},
    )

    main_mod.run_schema([image_path])

    captured = capsys.readouterr().out
    assert f"完了 -> {output_dir / 'alpha.schema.tsv'}" in captured
    assert "成功計" not in captured
    assert "実計" not in captured


def test_main_passes_parallel_files_to_docai(monkeypatch, tmp_path):
    image_path = _make_images(tmp_path, "alpha.png")[0]
    output_dir = tmp_path / "output"

    called: dict[str, object] = {}

    def fake_run_docai(images: list[Path], *, parallel_files: int = 1) -> None:
        called["images"] = images
        called["parallel_files"] = parallel_files

    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(main_mod, "resolve_images", lambda files: [image_path])
    monkeypatch.setattr(main_mod, "run_docai", fake_run_docai)
    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "docai", "--parallel-files", "3", str(image_path)],
    )

    main_mod.main()

    assert called == {"images": [image_path], "parallel_files": 3}
