"""main モジュールのユニットテスト。"""

import json
import sys
import threading
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
    tmp_path.mkdir(parents=True, exist_ok=True)
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


def _write_schema_with_type_names(schema_path: Path, *type_names: str) -> None:
    """指定した type_name 群で extract テスト用 schema を書き出す。"""
    payload = {
        "types": [{"type_name": type_name, "fields": ["name"]} for type_name in type_names],
    }
    schema_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _read_output_texts(output_dir: Path, pattern: str) -> dict[str, str]:
    """出力ディレクトリ内の対象ファイル内容を読み込む。"""
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(output_dir.glob(pattern))}


def _read_extract_tsv_manifest(output_dir: Path) -> dict:
    """extract TSV manifest を読み込む。"""
    return json.loads((output_dir / "cache" / "extract" / "_meta" / "tsv_manifest.json").read_text(encoding="utf-8"))


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
    seq_output.mkdir()
    main_mod.run_extract(images, schema_path, output_dir=seq_output, parallel_files=1)

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
    par_output.mkdir()
    main_mod.run_extract(images, schema_path, output_dir=par_output, parallel_files=2)

    par_texts = _read_output_texts(par_output, "*.tsv")

    assert seq_texts == par_texts
    assert seq_texts["Card.tsv"] == ("name\tpower\tsource\nfirst\t5\tfirst.png\nsecond\t6\tsecond.png\n")
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
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    with pytest.raises(RuntimeError, match="boom"):
        main_mod.run_extract(images, schema_path, parallel_files=2)

    assert existing_card.read_text(encoding="utf-8") == existing_text
    assert not (output_dir / "none_Unknown.tsv").exists()
    # 成功した first.png はキャッシュとして残っているので次回再実行で再利用できる
    assert (output_dir / "cache" / "extract" / "first.json").exists()
    assert not (output_dir / "cache" / "extract" / "second.json").exists()


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


def _extract_fake(
    results_by_stem: dict[str, dict] | None = None,
    *,
    calls: list[str] | None = None,
):
    """テスト用の `extract_with_schema` 差し替え関数を組み立てる。"""

    def fake(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        if calls is not None:
            calls.append(image_path.name)
        if results_by_stem is not None and image_path.stem in results_by_stem:
            return results_by_stem[image_path.stem]
        return {
            "matched_types": [
                {
                    "type_name": "Card",
                    "items": [{"name": image_path.stem, "power": str(len(image_path.stem))}],
                }
            ],
            "unmatched_types": [],
        }

    return fake


def _assert_run_extract_rejects_schema_type_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    type_names: list[str],
    pattern: str,
) -> None:
    """matched 側 schema の不正 type_name が run_extract 入口で reject されることを確認する。"""
    images = _make_images(tmp_path, "first.png")
    schema_path = tmp_path / "schema.json"
    _write_schema_with_type_names(schema_path, *type_names)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    def fail_if_called(*args, **kwargs):
        pytest.fail("extract_with_schema should not be called when schema type_name validation fails")

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fail_if_called)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    with pytest.raises(ValueError, match=pattern):
        main_mod.run_extract(images, schema_path, parallel_files=1)


def test_run_extract_reuses_cached_results(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "first.png", "second.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    calls: list[str] = []
    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake(calls=calls))
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)
    first_tsv = (output_dir / "Card.tsv").read_text(encoding="utf-8")
    assert sorted(calls) == ["first.png", "second.png"]

    calls.clear()
    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert calls == []
    assert (output_dir / "Card.tsv").read_text(encoding="utf-8") == first_tsv


def test_run_extract_reuses_cached_results_for_tsv_manifest_stem(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "tsv_manifest.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    calls: list[str] = []
    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake(calls=calls))
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)
    assert calls == ["tsv_manifest.png"]
    assert (output_dir / "cache" / "extract" / "tsv_manifest.json").exists()
    assert (output_dir / "cache" / "extract" / "_meta" / "tsv_manifest.json").exists()

    calls.clear()
    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert calls == []


def test_run_extract_invalidates_on_schema_change(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "first.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    calls: list[str] = []
    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake(calls=calls))
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)
    calls.clear()

    schema_path.write_text(
        '{"types":[{"type_name":"Card","fields":["name","power","rarity"]}]}',
        encoding="utf-8",
    )

    def fake_with_rarity(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        calls.append(image_path.name)
        return {
            "matched_types": [
                {
                    "type_name": "Card",
                    "items": [{"name": image_path.stem, "power": "1", "rarity": "R"}],
                }
            ],
            "unmatched_types": [],
        }

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake_with_rarity)
    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert calls == ["first.png"]
    assert "rarity" in (output_dir / "Card.tsv").read_text(encoding="utf-8")


def test_run_extract_invalidates_on_cache_version_change(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "first.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    calls: list[str] = []
    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake(calls=calls))
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)
    calls.clear()

    monkeypatch.setattr(main_mod, "CACHE_VERSION", "99")
    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert calls == ["first.png"]


def test_run_extract_invalidates_on_image_content_change(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "first.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    calls: list[str] = []
    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake(calls=calls))
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)
    calls.clear()

    images[0].write_bytes(b"different bytes")
    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert calls == ["first.png"]


def test_run_extract_invalidates_on_prompt_fingerprint_change(monkeypatch, tmp_path):
    """C1: prompt 契約版変更で自動無効化されること（CACHE_VERSION 以外で stale 防止）。"""
    images = _make_images(tmp_path, "first.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    calls: list[str] = []
    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake(calls=calls))
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)
    calls.clear()

    # C1: extract モジュール内の compute を直接差替えて prompt fp を強制変更（2 回目ミス）
    import nova_parser.extract as extract_mod

    monkeypatch.setattr(extract_mod, "_compute_extract_prompt_fingerprint", lambda: "sha256:forced-different")
    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert calls == ["first.png"]


def test_run_extract_invalidates_on_extractor_id_change(monkeypatch, tmp_path):
    """C1: extractor_id 変更で自動無効化（Custom Extractor 切替時の安全策）。"""
    images = _make_images(tmp_path, "first.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    calls: list[str] = []
    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake(calls=calls))
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)
    calls.clear()

    # C1: extract モジュール内の _build を差替（extractor_id 変更で 2 回目ミス）
    from dataclasses import replace

    import nova_parser.extract as extract_mod

    original_build = extract_mod._build_extract_fingerprints

    def fake_build(schema):
        fps = original_build(schema)
        return replace(fps, extractor_id="custom-extractor/v99")

    monkeypatch.setattr(extract_mod, "_build_extract_fingerprints", fake_build)
    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert calls == ["first.png"]


def test_run_extract_resumes_after_failure(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "first.png", "second.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    calls: list[str] = []

    def fake_fail_second(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        calls.append(image_path.name)
        if image_path.name == "second.png":
            raise RuntimeError("boom")
        return {
            "matched_types": [{"type_name": "Card", "items": [{"name": image_path.stem, "power": "1"}]}],
            "unmatched_types": [],
        }

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake_fail_second)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    with pytest.raises(RuntimeError, match="boom"):
        main_mod.run_extract(images, schema_path, parallel_files=1)

    assert "first.png" in calls and "second.png" in calls
    calls.clear()

    def fake_succeed_all(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        calls.append(image_path.name)
        return {
            "matched_types": [{"type_name": "Card", "items": [{"name": image_path.stem, "power": "2"}]}],
            "unmatched_types": [],
        }

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake_succeed_all)
    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert calls == ["second.png"]
    tsv = (output_dir / "Card.tsv").read_text(encoding="utf-8")
    assert "first\t1\tfirst.png" in tsv
    assert "second\t2\tsecond.png" in tsv


def test_run_extract_detects_duplicate_stems(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "same.png", "same.jpg")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    def fail_if_called(*args, **kwargs):
        msg = "extract_with_schema should not be called when cache stems collide"
        raise AssertionError(msg)

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fail_if_called)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    with pytest.raises(ValueError, match=r"same\.json"):
        main_mod.run_extract(images, schema_path, parallel_files=1)


def test_run_extract_ignores_corrupted_cache(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "first.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    cache_dir = output_dir / "cache" / "extract"
    cache_dir.mkdir(parents=True)
    (cache_dir / "first.json").write_text("{ not json", encoding="utf-8")

    calls: list[str] = []
    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake(calls=calls))
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert calls == ["first.png"]
    assert (output_dir / "Card.tsv").read_text(encoding="utf-8") == ("name\tpower\tsource\nfirst\t5\tfirst.png\n")


def test_run_extract_stable_row_order_parallel(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "alpha.png", "beta.png", "gamma.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    def fake(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        # 先頭ほど遅く返すことで完了順と入力順をずらす
        if image_path.name == "alpha.png":
            time.sleep(0.1)
        elif image_path.name == "beta.png":
            time.sleep(0.05)
        return {
            "matched_types": [{"type_name": "Card", "items": [{"name": image_path.stem, "power": "1"}]}],
            "unmatched_types": [],
        }

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=3)

    tsv_lines = (output_dir / "Card.tsv").read_text(encoding="utf-8").splitlines()
    assert tsv_lines[0] == "name\tpower\tsource"
    assert tsv_lines[1].endswith("\talpha.png")
    assert tsv_lines[2].endswith("\tbeta.png")
    assert tsv_lines[3].endswith("\tgamma.png")


def test_run_extract_regenerates_all_schema_type_tsvs(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "first.png")
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(
        """
{
  "types": [
    {"type_name": "Card", "fields": ["name", "power"]},
    {"type_name": "Empty", "fields": ["x"]}
  ]
}
""".strip(),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake())
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)

    empty_tsv = (output_dir / "Empty.tsv").read_text(encoding="utf-8")
    assert empty_tsv == "x\tsource\n"


def test_run_extract_tsv_overwrites_previous_run(monkeypatch, tmp_path):
    images_a = _make_images(tmp_path / "A", "a.png")
    images_b = _make_images(tmp_path / "B", "b.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake())
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images_a, schema_path, parallel_files=1)
    assert "a.png" in (output_dir / "Card.tsv").read_text(encoding="utf-8")

    main_mod.run_extract(images_b, schema_path, parallel_files=1)
    tsv = (output_dir / "Card.tsv").read_text(encoding="utf-8")
    assert "a.png" not in tsv
    assert "b.png" in tsv


def test_run_extract_sanitizes_unmatched_type_filename(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "first.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    def fake(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        return {
            "matched_types": [],
            "unmatched_types": [
                {
                    "type_name": "../weird/\u0001name",
                    "items": [{"raw": "danger"}],
                }
            ],
        }

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)

    produced = sorted(output_dir.glob("none_*.tsv"))
    assert len(produced) == 1
    assert "/" not in produced[0].name
    assert "\x01" not in produced[0].name


def test_run_extract_accepts_matched_type_name_with_slash(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "first.png")
    schema_path = tmp_path / "schema.json"
    _write_schema_with_type_names(schema_path, "リレーション/コネ")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    monkeypatch.setattr(
        documentai_mod,
        "extract_with_schema",
        _extract_fake(
            {
                "first": {
                    "matched_types": [
                        {"type_name": "リレーション/コネ", "items": [{"name": "danger"}]},
                    ],
                    "unmatched_types": [],
                }
            }
        ),
    )
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert (output_dir / "リレーション_コネ.tsv").read_text(encoding="utf-8") == "name\tsource\ndanger\tfirst.png\n"
    assert not (output_dir / "リレーション").exists()


def test_run_extract_accepts_matched_type_name_with_colon(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "first.png")
    schema_path = tmp_path / "schema.json"
    _write_schema_with_type_names(schema_path, "ユニークアイテム:武器")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    monkeypatch.setattr(
        documentai_mod,
        "extract_with_schema",
        _extract_fake(
            {
                "first": {
                    "matched_types": [
                        {"type_name": "ユニークアイテム:武器", "items": [{"name": "sword"}]},
                    ],
                    "unmatched_types": [],
                }
            }
        ),
    )
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert (output_dir / "ユニークアイテム_武器.tsv").read_text(encoding="utf-8") == "name\tsource\nsword\tfirst.png\n"


def test_run_extract_rejects_matched_type_name_with_path_traversal(monkeypatch, tmp_path):
    _assert_run_extract_rejects_schema_type_names(monkeypatch, tmp_path, ["../escape"], r"\.\./escape")


def test_run_extract_rejects_matched_type_name_with_backslash(monkeypatch, tmp_path):
    _assert_run_extract_rejects_schema_type_names(monkeypatch, tmp_path, [r"a\b"], r"バックスラッシュ")


def test_run_extract_rejects_matched_type_name_starts_with_slash(monkeypatch, tmp_path):
    _assert_run_extract_rejects_schema_type_names(monkeypatch, tmp_path, ["/absolute"], r"先頭を / にできません")


def test_run_extract_rejects_matched_type_name_with_control_char(monkeypatch, tmp_path):
    _assert_run_extract_rejects_schema_type_names(monkeypatch, tmp_path, ["a\x00b"], r"a\\x00b")


def test_run_extract_rejects_matched_type_name_with_reserved_prefix(monkeypatch, tmp_path):
    _assert_run_extract_rejects_schema_type_names(monkeypatch, tmp_path, ["none_Custom"], r"none_Custom")


def test_run_extract_rejects_matched_type_name_sanitizing_to_none_prefix(monkeypatch, tmp_path):
    _assert_run_extract_rejects_schema_type_names(monkeypatch, tmp_path, ["none/Custom"], r"sanitize 後.*none_")


def test_run_extract_rejects_matched_type_name_with_reserved_suffix(monkeypatch, tmp_path):
    _assert_run_extract_rejects_schema_type_names(monkeypatch, tmp_path, ["foo.docai"], r"foo\.docai")


def test_run_extract_rejects_matched_type_name_duplicate(monkeypatch, tmp_path):
    _assert_run_extract_rejects_schema_type_names(
        monkeypatch,
        tmp_path,
        ["Card", "Card"],
        r"schema 内で重複しています",
    )


def test_run_extract_rejects_matched_type_name_empty_or_whitespace(monkeypatch, tmp_path):
    _assert_run_extract_rejects_schema_type_names(monkeypatch, tmp_path, ["   "], r"空文字や空白だけ")


def test_run_extract_rejects_matched_type_name_sanitize_collision(monkeypatch, tmp_path):
    _assert_run_extract_rejects_schema_type_names(monkeypatch, tmp_path, ["a/b", "a_b"], r"衝突します")


def test_run_extract_cleans_stale_tsvs_using_manifest(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "only.png")
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(
        """
{
  "types": [
    {"type_name": "Card", "fields": ["name", "power"]},
    {"type_name": "Empty", "fields": ["x"]}
  ]
}
""".strip(),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    def fake_first_run(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        return {
            "matched_types": [
                {"type_name": "Card", "items": [{"name": image_path.stem, "power": "1"}]},
            ],
            "unmatched_types": [
                {"type_name": "Unknown", "items": [{"raw": "legacy"}]},
            ],
        }

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake_first_run)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert (output_dir / "Empty.tsv").exists()
    assert (output_dir / "none_Unknown.tsv").exists()
    manifest = _read_extract_tsv_manifest(output_dir)
    assert manifest["files"] == ["Card.tsv", "Empty.tsv", "none_Unknown.tsv"]

    _write_schema(schema_path)

    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake())
    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert not (output_dir / "Empty.tsv").exists()
    assert not (output_dir / "none_Unknown.tsv").exists()
    manifest = _read_extract_tsv_manifest(output_dir)
    assert manifest["files"] == ["Card.tsv"]


def test_run_extract_bootstraps_cleanup_without_manifest(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "only.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    stale_none = output_dir / "none_Old.tsv"
    stale_none.write_text("stale none\n", encoding="utf-8")
    stale_matched = output_dir / "Old.tsv"
    stale_matched.write_text("stale matched\n", encoding="utf-8")
    keep_docai = output_dir / "alpha.docai.tsv"
    keep_docai.write_text("keep docai\n", encoding="utf-8")
    keep_none_docai = output_dir / "none_alpha.docai.tsv"
    keep_none_docai.write_text("keep none docai\n", encoding="utf-8")
    keep_none_schema = output_dir / "none_alpha.schema.tsv"
    keep_none_schema.write_text("keep none schema\n", encoding="utf-8")
    keep_none_structured = output_dir / "none_alpha.structured.tsv"
    keep_none_structured.write_text("keep none structured\n", encoding="utf-8")

    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake())
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert not stale_none.exists()
    assert not stale_matched.exists()
    assert keep_docai.exists()
    assert keep_none_docai.exists()
    assert keep_none_schema.exists()
    assert keep_none_structured.exists()
    manifest = _read_extract_tsv_manifest(output_dir)
    assert manifest["files"] == ["Card.tsv"]


def test_run_extract_legacy_cleanup_removes_nested_tsv(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "only.png")
    schema_path = tmp_path / "schema.json"
    _write_schema_with_type_names(schema_path, "sub/old")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    stale_nested = output_dir / "sub" / "old.tsv"
    stale_nested.parent.mkdir(parents=True, exist_ok=True)
    stale_nested.write_text("stale nested\n", encoding="utf-8")

    monkeypatch.setattr(
        documentai_mod,
        "extract_with_schema",
        _extract_fake(
            {
                "only": {
                    "matched_types": [
                        {"type_name": "sub/old", "items": [{"name": "legacy"}]},
                    ],
                    "unmatched_types": [],
                }
            }
        ),
    )
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert not stale_nested.exists()
    assert (output_dir / "sub_old.tsv").read_text(encoding="utf-8") == "name\tsource\nlegacy\tonly.png\n"
    manifest = _read_extract_tsv_manifest(output_dir)
    assert manifest["files"] == ["sub_old.tsv"]


def test_run_extract_legacy_cleanup_preserves_unrelated_nested_tsv(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "only.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    unrelated_nested = output_dir / "reports" / "summary.tsv"
    unrelated_nested.parent.mkdir(parents=True, exist_ok=True)
    unrelated_nested.write_text("keep me\n", encoding="utf-8")

    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake())
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert unrelated_nested.read_text(encoding="utf-8") == "keep me\n"
    assert (output_dir / "Card.tsv").exists()
    manifest = _read_extract_tsv_manifest(output_dir)
    assert manifest["files"] == ["Card.tsv"]


def test_run_extract_parallel_failure_preserves_partial_cache(monkeypatch, tmp_path):
    """並列実行で一部が失敗しても、成功済み画像のキャッシュは保持される。"""
    images = _make_images(tmp_path, "good.png", "bad.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    start_barrier = threading.Barrier(2)

    def fake(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        start_barrier.wait(timeout=1.0)
        if image_path.name == "bad.png":
            msg = "boom"
            raise RuntimeError(msg)
        time.sleep(0.05)
        return {
            "matched_types": [
                {"type_name": "Card", "items": [{"name": "Alpha", "power": "1"}]},
            ],
            "unmatched_types": [],
        }

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    with pytest.raises(RuntimeError, match="boom"):
        main_mod.run_extract(images, schema_path, parallel_files=2)

    assert (output_dir / "cache" / "extract" / "good.json").exists()
    assert not (output_dir / "cache" / "extract" / "bad.json").exists()
    assert not (output_dir / "Card.tsv").exists()


def test_run_extract_resumes_after_parallel_failure(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "good.png", "bad.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    calls: list[str] = []
    start_barrier = threading.Barrier(2)

    def fake_fail_bad(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        calls.append(image_path.name)
        start_barrier.wait(timeout=1.0)
        if image_path.name == "bad.png":
            raise RuntimeError("boom")
        time.sleep(0.05)
        return {
            "matched_types": [
                {"type_name": "Card", "items": [{"name": image_path.stem, "power": "1"}]},
            ],
            "unmatched_types": [],
        }

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake_fail_bad)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)

    with pytest.raises(RuntimeError, match="boom"):
        main_mod.run_extract(images, schema_path, parallel_files=2)

    assert sorted(calls) == ["bad.png", "good.png"]
    calls.clear()

    def fake_succeed_remaining(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        calls.append(image_path.name)
        return {
            "matched_types": [
                {"type_name": "Card", "items": [{"name": image_path.stem, "power": "2"}]},
            ],
            "unmatched_types": [],
        }

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake_succeed_remaining)
    main_mod.run_extract(images, schema_path, parallel_files=2)

    assert calls == ["bad.png"]
    tsv = (output_dir / "Card.tsv").read_text(encoding="utf-8")
    assert "good\t1\tgood.png" in tsv
    assert "bad\t2\tbad.png" in tsv


def test_run_extract_cancels_pending_jobs_when_cache_save_fails(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "first.png", "second.png", "third.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    class FakeFuture:
        def __init__(self, *, result: dict | None = None, done: bool = False):
            self._result = result
            self._done = done
            self.cancel_calls = 0

        def result(self) -> dict:
            return self._result or {"matched_types": [], "unmatched_types": []}

        def done(self) -> bool:
            return self._done

        def cancel(self) -> bool:
            self.cancel_calls += 1
            return True

    first_future = FakeFuture(
        result={
            "matched_types": [
                {"type_name": "Card", "items": [{"name": "first", "power": "1"}]},
            ],
            "unmatched_types": [],
        },
        done=True,
    )
    second_future = FakeFuture()
    third_future = FakeFuture()
    submitted_futures = [first_future, second_future, third_future]

    class FakeExecutor:
        def __init__(self, futures: list[FakeFuture]):
            self._futures = futures

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, *args, **kwargs):
            return self._futures.pop(0)

    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(main_mod, "ThreadPoolExecutor", lambda max_workers: FakeExecutor(submitted_futures))
    monkeypatch.setattr(main_mod, "as_completed", lambda futures: iter([first_future]))

    def _raise_disk_full(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(main_mod, "_save_extract_cache", _raise_disk_full)

    with pytest.raises(OSError, match="disk full"):
        main_mod.run_extract(images, schema_path, parallel_files=2)

    assert second_future.cancel_calls == 1
    assert third_future.cancel_calls == 1
    assert not (output_dir / "Card.tsv").exists()


def test_run_extract_staging_failure_preserves_previous_outputs(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "only.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    old_card = output_dir / "Card.tsv"
    old_card.write_text("name\tpower\tsource\nold\t9\told.png\n", encoding="utf-8")
    old_none = output_dir / "none_Unknown.tsv"
    old_none.write_text("raw\tsource\nold\told.png\n", encoding="utf-8")
    manifest_path = output_dir / "cache" / "extract" / "_meta" / "tsv_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"manifest_version": 1, "files": ["Card.tsv", "none_Unknown.tsv"]}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    def fake(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        return {
            "matched_types": [
                {"type_name": "Card", "items": [{"name": image_path.stem, "power": "1"}]},
            ],
            "unmatched_types": [
                {"type_name": "New", "items": [{"raw": "fresh"}]},
            ],
        }

    original_atomic_write_text = main_mod._atomic_write_text

    def fail_stage_write(path: Path, text: str) -> None:
        stage_prefix = main_mod._EXTRACT_TSV_STAGE_PREFIX
        if any(part.startswith(stage_prefix) for part in path.parts) and path.name == "none_New.tsv":
            raise OSError("stage failed")
        original_atomic_write_text(path, text)

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(main_mod, "_atomic_write_text", fail_stage_write)

    with pytest.raises(OSError, match="stage failed"):
        main_mod.run_extract(images, schema_path, parallel_files=1)

    assert old_card.read_text(encoding="utf-8") == "name\tpower\tsource\nold\t9\told.png\n"
    assert old_none.read_text(encoding="utf-8") == "raw\tsource\nold\told.png\n"
    manifest = _read_extract_tsv_manifest(output_dir)
    assert manifest["files"] == ["Card.tsv", "none_Unknown.tsv"]


def test_run_extract_manifest_stage_failure_preserves_previous_outputs(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "only.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    old_card = output_dir / "Card.tsv"
    old_card.write_text("name\tpower\tsource\nold\t9\told.png\n", encoding="utf-8")
    old_none = output_dir / "none_Unknown.tsv"
    old_none.write_text("raw\tsource\nold\told.png\n", encoding="utf-8")
    manifest_path = output_dir / "cache" / "extract" / "_meta" / "tsv_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"manifest_version": 1, "files": ["Card.tsv", "none_Unknown.tsv"]}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    original_atomic_write_text = main_mod._atomic_write_text

    def fail_manifest_stage_write(path: Path, text: str) -> None:
        stage_prefix = main_mod._EXTRACT_TSV_STAGE_PREFIX
        if any(part.startswith(stage_prefix) for part in path.parts) and path.name == "tsv_manifest.json":
            raise OSError("manifest stage failed")
        original_atomic_write_text(path, text)

    monkeypatch.setattr(documentai_mod, "extract_with_schema", _extract_fake())
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(main_mod, "_atomic_write_text", fail_manifest_stage_write)

    with pytest.raises(OSError, match="manifest stage failed"):
        main_mod.run_extract(images, schema_path, parallel_files=1)

    assert old_card.read_text(encoding="utf-8") == "name\tpower\tsource\nold\t9\told.png\n"
    assert old_none.read_text(encoding="utf-8") == "raw\tsource\nold\told.png\n"
    manifest = _read_extract_tsv_manifest(output_dir)
    assert manifest["files"] == ["Card.tsv", "none_Unknown.tsv"]


def test_run_extract_stale_cleanup_failure_preserves_previous_outputs(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "only.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    old_card = output_dir / "Card.tsv"
    old_card.write_text("name\tpower\tsource\nold\t9\told.png\n", encoding="utf-8")
    old_none = output_dir / "none_Unknown.tsv"
    old_none.write_text("raw\tsource\nold\told.png\n", encoding="utf-8")
    manifest_path = output_dir / "cache" / "extract" / "_meta" / "tsv_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"manifest_version": 1, "files": ["Card.tsv", "none_Unknown.tsv"]}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    def fake(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        return {
            "matched_types": [
                {"type_name": "Card", "items": [{"name": image_path.stem, "power": "1"}]},
            ],
            "unmatched_types": [
                {"type_name": "New", "items": [{"raw": "fresh"}]},
            ],
        }

    original_replace = Path.replace

    def fail_stale_backup(self: Path, target: Path) -> Path:
        target_path = Path(target)
        backup_prefix = main_mod._EXTRACT_TSV_BACKUP_PREFIX
        if self == old_none and any(part.startswith(backup_prefix) for part in target_path.parts):
            raise OSError("stale cleanup failed")
        return original_replace(self, target)

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(Path, "replace", fail_stale_backup)

    with pytest.raises(OSError, match="stale cleanup failed"):
        main_mod.run_extract(images, schema_path, parallel_files=1)

    assert old_card.read_text(encoding="utf-8") == "name\tpower\tsource\nold\t9\told.png\n"
    assert old_none.read_text(encoding="utf-8") == "raw\tsource\nold\told.png\n"
    assert not (output_dir / "none_New.tsv").exists()
    manifest = _read_extract_tsv_manifest(output_dir)
    assert manifest["files"] == ["Card.tsv", "none_Unknown.tsv"]


def test_run_extract_rollback_secondary_failure_preserves_backup(monkeypatch, tmp_path, capsys):
    images = _make_images(tmp_path, "only.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    old_card = output_dir / "Card.tsv"
    old_card.write_text("name\tpower\tsource\nold\t9\told.png\n", encoding="utf-8")
    old_none = output_dir / "none_Unknown.tsv"
    old_none.write_text("raw\tsource\nold\told.png\n", encoding="utf-8")
    manifest_path = output_dir / "cache" / "extract" / "_meta" / "tsv_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"manifest_version": 1, "files": ["Card.tsv", "none_Unknown.tsv"]}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    def fake(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        return {
            "matched_types": [
                {"type_name": "Card", "items": [{"name": image_path.stem, "power": "1"}]},
            ],
            "unmatched_types": [
                {"type_name": "New", "items": [{"raw": "fresh"}]},
            ],
        }

    original_replace = Path.replace

    def fail_publish_and_manifest_restore(self: Path, target: Path) -> Path:
        target_path = Path(target)
        if (
            any(part.startswith(main_mod._EXTRACT_TSV_STAGE_PREFIX) for part in self.parts)
            and target_path == output_dir / "none_New.tsv"
        ):
            raise OSError("publish failed")
        if (
            any(part.startswith(main_mod._EXTRACT_TSV_BACKUP_PREFIX) for part in self.parts)
            and target_path == manifest_path
        ):
            raise OSError("manifest restore failed")
        return original_replace(self, target)

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(Path, "replace", fail_publish_and_manifest_restore)

    with pytest.raises(OSError, match="publish failed"):
        main_mod.run_extract(images, schema_path, parallel_files=1)

    backup_dirs = [
        d for d in output_dir.iterdir() if d.is_dir() and d.name.startswith(main_mod._EXTRACT_TSV_BACKUP_PREFIX)
    ]
    assert len(backup_dirs) == 1
    backup_manifest = backup_dirs[0] / "cache" / "extract" / "_meta" / "tsv_manifest.json"
    assert backup_manifest.exists()

    captured = capsys.readouterr()
    assert "rollback during TSV commit did not complete cleanly" in captured.err


def test_run_extract_retries_stale_cleanup_after_failed_commit(monkeypatch, tmp_path):
    images = _make_images(tmp_path, "only.png")
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    old_card = output_dir / "Card.tsv"
    old_card.write_text("name\tpower\tsource\nold\t9\told.png\n", encoding="utf-8")
    old_none = output_dir / "none_Unknown.tsv"
    old_none.write_text("raw\tsource\nold\told.png\n", encoding="utf-8")
    manifest_path = output_dir / "cache" / "extract" / "_meta" / "tsv_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"manifest_version": 1, "files": ["Card.tsv", "none_Unknown.tsv"]}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    def fake(
        image_path: Path,
        schema: dict,
        *,
        show_progress: bool = True,
        output_dir: Path = Path("Output"),
    ) -> dict:
        return {
            "matched_types": [
                {"type_name": "Card", "items": [{"name": image_path.stem, "power": "1"}]},
            ],
            "unmatched_types": [
                {"type_name": "New", "items": [{"raw": "fresh"}]},
            ],
        }

    original_replace = Path.replace

    def fail_stale_backup(self: Path, target: Path) -> Path:
        target_path = Path(target)
        backup_prefix = main_mod._EXTRACT_TSV_BACKUP_PREFIX
        if self == old_none and any(part.startswith(backup_prefix) for part in target_path.parts):
            raise OSError("stale cleanup failed")
        return original_replace(self, target)

    monkeypatch.setattr(documentai_mod, "extract_with_schema", fake)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(Path, "replace", fail_stale_backup)

    with pytest.raises(OSError, match="stale cleanup failed"):
        main_mod.run_extract(images, schema_path, parallel_files=1)

    monkeypatch.setattr(Path, "replace", original_replace)

    main_mod.run_extract(images, schema_path, parallel_files=1)

    assert (output_dir / "Card.tsv").read_text(encoding="utf-8") == "name\tpower\tsource\nonly\t1\tonly.png\n"
    assert not old_none.exists()
    assert (output_dir / "none_New.tsv").read_text(encoding="utf-8") == "raw\tsource\nfresh\tonly.png\n"
    manifest = _read_extract_tsv_manifest(output_dir)
    assert manifest["files"] == ["Card.tsv", "none_New.tsv"]


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
        [
            "nova-parser",
            "--mode",
            "docai",
            "--parallel-files",
            "3",
            "--output-dir",
            str(output_dir),
            str(image_path),
        ],
    )

    main_mod.main()

    assert called == {"images": [image_path], "parallel_files": 3}


def test_main_uses_output_dir_for_docai(monkeypatch, tmp_path):
    image_path = _make_images(tmp_path, "alpha.png")[0]
    output_dir = tmp_path / "custom" / "nested"

    called: dict[str, object] = {}

    def fake_run_docai(images: list[Path], *, parallel_files: int = 1) -> None:
        called["images"] = images
        called["parallel_files"] = parallel_files
        called["output_dir"] = main_mod.OUTPUT_DIR
        called["output_dir_exists"] = main_mod.OUTPUT_DIR.is_dir()

    monkeypatch.setattr(main_mod, "OUTPUT_DIR", Path("Output"))
    monkeypatch.setattr(main_mod, "resolve_images", lambda files: [image_path])
    monkeypatch.setattr(main_mod, "run_docai", fake_run_docai)
    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "docai", "--output-dir", str(output_dir), str(image_path)],
    )

    main_mod.main()

    assert called == {
        "images": [image_path],
        "parallel_files": 1,
        "output_dir": output_dir,
        "output_dir_exists": True,
    }
    assert output_dir.is_dir()
    assert main_mod.OUTPUT_DIR == Path("Output")


def test_main_output_dir_does_not_persist_between_invocations(monkeypatch, tmp_path):
    image_path = _make_images(tmp_path, "alpha.png")[0]
    custom_output = tmp_path / "custom_output"
    default_output = tmp_path / "default_output"
    observed_output_dirs: list[Path] = []

    def fake_run_docai(images: list[Path], *, parallel_files: int = 1) -> None:
        observed_output_dirs.append(main_mod.OUTPUT_DIR)

    monkeypatch.setattr(main_mod, "DEFAULT_OUTPUT_DIR", default_output)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", Path("Output"))
    monkeypatch.setattr(main_mod, "resolve_images", lambda files: [image_path])
    monkeypatch.setattr(main_mod, "run_docai", fake_run_docai)

    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "docai", "--output-dir", str(custom_output), str(image_path)],
    )
    main_mod.main()

    monkeypatch.setattr(sys, "argv", ["nova-parser", "--mode", "docai", str(image_path)])
    main_mod.main()

    assert observed_output_dirs == [custom_output, default_output]
    assert main_mod.OUTPUT_DIR == Path("Output")
    assert custom_output.is_dir()
    assert default_output.is_dir()


def test_main_restores_output_dir_when_run_fails(monkeypatch, tmp_path):
    image_path = _make_images(tmp_path, "alpha.png")[0]
    initial_output = tmp_path / "initial_output"
    custom_output = tmp_path / "custom_output"

    def fail_run_docai(images: list[Path], *, parallel_files: int = 1) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(main_mod, "OUTPUT_DIR", initial_output)
    monkeypatch.setattr(main_mod, "resolve_images", lambda files: [image_path])
    monkeypatch.setattr(main_mod, "run_docai", fail_run_docai)
    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "docai", "--output-dir", str(custom_output), str(image_path)],
    )

    with pytest.raises(RuntimeError, match="boom"):
        main_mod.main()

    assert main_mod.OUTPUT_DIR == initial_output
    assert custom_output.is_dir()


def test_main_output_dir_applies_to_schema_propose_default_input(monkeypatch, tmp_path):
    output_dir = tmp_path / "schema_output"
    output_dir.mkdir()
    (output_dir / "alpha.docai.tsv").write_text("## Card\nname\tpower\nalpha\t1\n", encoding="utf-8")

    monkeypatch.setattr(main_mod, "OUTPUT_DIR", Path("Output"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "schema_propose", "--output-dir", str(output_dir)],
    )

    main_mod.main()

    result = json.loads((output_dir / "schema_proposal.json").read_text(encoding="utf-8"))
    assert result == {
        "types": [
            {
                "type_name": "Card",
                "fields": ["name", "power"],
                "source": "alpha.docai.tsv",
            }
        ]
    }


def test_main_rejects_output_dir_file(monkeypatch, tmp_path, capsys):
    output_file = tmp_path / "not_a_dir"
    output_file.write_text("already exists\n", encoding="utf-8")

    monkeypatch.setattr(main_mod, "OUTPUT_DIR", Path("Output"))
    monkeypatch.setattr(sys, "argv", ["nova-parser", "--output-dir", str(output_file)])

    with pytest.raises(SystemExit) as excinfo:
        main_mod.main()

    captured = capsys.readouterr()
    assert excinfo.value.code == 2
    assert "出力先がディレクトリではありません" in captured.err
    assert str(output_file) in captured.err


# ---------------------------------------------------------------------------
# extract モード: --output-dir 未指定時の Output/[base name] 派生テスト
# ---------------------------------------------------------------------------


def _setup_extract_output_dir_test(monkeypatch, tmp_path):
    """extract 出力先派生テスト共通の前準備。schema パスと default Output を用意する。"""
    schema_path = tmp_path / "schema.json"
    _write_schema(schema_path)
    default_output = tmp_path / "Output"

    observed: dict[str, Path] = {}

    def fake_run_extract(
        images: list[Path],
        schema_path: Path,
        *,
        output_dir: Path | None = None,
        parallel_files: int = 1,
    ) -> None:
        # 呼び出し時に渡された output_dir（またはグローバル）を記録して検証
        observed["output_dir"] = output_dir if output_dir is not None else main_mod.OUTPUT_DIR

    monkeypatch.setattr(main_mod, "DEFAULT_OUTPUT_DIR", default_output)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", Path("Output"))
    monkeypatch.setattr(main_mod, "run_extract", fake_run_extract)
    return schema_path, default_output, observed


def test_main_extract_derives_output_subdir_for_single_directory(monkeypatch, tmp_path):
    """単一ディレクトリ入力 → Output/[ディレクトリ名] に派生する。"""
    schema_path, default_output, observed = _setup_extract_output_dir_test(monkeypatch, tmp_path)
    input_dir = tmp_path / "DX3_EA"
    _make_images(input_dir, "alpha.png")

    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "extract", "--schema", str(schema_path), str(input_dir)],
    )

    main_mod.main()

    assert observed["output_dir"] == default_output / "DX3_EA"
    assert (default_output / "DX3_EA").is_dir()


def test_main_extract_does_not_derive_for_single_file(monkeypatch, tmp_path):
    """単一ファイル入力 → 派生せず DEFAULT_OUTPUT_DIR 直下のまま。"""
    schema_path, default_output, observed = _setup_extract_output_dir_test(monkeypatch, tmp_path)
    image_path = _make_images(tmp_path / "DX3_EA", "alpha.png")[0]

    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "extract", "--schema", str(schema_path), str(image_path)],
    )

    main_mod.main()

    assert observed["output_dir"] == default_output


def test_main_extract_does_not_derive_for_multiple_args(monkeypatch, tmp_path):
    """複数引数（ディレクトリ + ファイル）→ 派生せず DEFAULT_OUTPUT_DIR 直下のまま。"""
    schema_path, default_output, observed = _setup_extract_output_dir_test(monkeypatch, tmp_path)
    input_dir = tmp_path / "DX3_EA"
    _make_images(input_dir, "alpha.png")
    extra_file = _make_images(tmp_path / "other", "beta.png")[0]

    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "extract", "--schema", str(schema_path), str(input_dir), str(extra_file)],
    )

    main_mod.main()

    assert observed["output_dir"] == default_output


def test_main_extract_does_not_derive_when_files_omitted(monkeypatch, tmp_path):
    """引数省略（Images/ 全体）→ 派生せず DEFAULT_OUTPUT_DIR 直下のまま。"""
    schema_path, default_output, observed = _setup_extract_output_dir_test(monkeypatch, tmp_path)
    # files 省略時は resolve_images が Images/ を走査するため、空にならないようモック。
    monkeypatch.setattr(main_mod, "resolve_images", lambda files: _make_images(tmp_path / "imgs", "alpha.png"))

    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "extract", "--schema", str(schema_path)],
    )

    main_mod.main()

    assert observed["output_dir"] == default_output


def test_main_extract_explicit_output_dir_takes_precedence(monkeypatch, tmp_path):
    """--output-dir 明示指定は単一ディレクトリ入力でも派生されず優先される。"""
    schema_path, _default_output, observed = _setup_extract_output_dir_test(monkeypatch, tmp_path)
    input_dir = tmp_path / "DX3_EA"
    _make_images(input_dir, "alpha.png")
    custom_output = tmp_path / "custom"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nova-parser",
            "--mode",
            "extract",
            "--schema",
            str(schema_path),
            "--output-dir",
            str(custom_output),
            str(input_dir),
        ],
    )

    main_mod.main()

    assert observed["output_dir"] == custom_output


def test_main_extract_does_not_derive_for_parent_dir_argument(monkeypatch, tmp_path):
    """末尾が `..` の単一ディレクトリ入力 → 派生せず Output/ 直下にフォールバックする。"""
    schema_path, default_output, observed = _setup_extract_output_dir_test(monkeypatch, tmp_path)
    input_dir = tmp_path / "DX3_EA"
    input_dir.mkdir()
    # DX3_EA/.. は tmp_path を指すため、画像は tmp_path 直下に置く。
    _make_images(tmp_path, "alpha.png")
    parent_arg = input_dir / ".."  # 実在し is_dir() は True だが name は ".."

    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "extract", "--schema", str(schema_path), str(parent_arg)],
    )

    main_mod.main()

    # Output/.. ではなく Output/ 直下にフォールバックする。
    assert observed["output_dir"] == default_output
    assert default_output.is_dir()


def test_main_non_extract_mode_does_not_derive_for_single_directory(monkeypatch, tmp_path):
    """extract 以外（docai）は単一ディレクトリ入力でも派生しない。"""
    default_output = tmp_path / "Output"
    input_dir = tmp_path / "DX3_EA"
    _make_images(input_dir, "alpha.png")

    observed: dict[str, Path] = {}

    def fake_run_docai(images, *, parallel_files: int = 1) -> None:
        observed["output_dir"] = main_mod.OUTPUT_DIR

    monkeypatch.setattr(main_mod, "DEFAULT_OUTPUT_DIR", default_output)
    monkeypatch.setattr(main_mod, "OUTPUT_DIR", Path("Output"))
    monkeypatch.setattr(main_mod, "run_docai", fake_run_docai)
    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "docai", str(input_dir)],
    )

    main_mod.main()

    assert observed["output_dir"] == default_output


# ---------------------------------------------------------------------------
# schema_propose ディレクトリ引数対応テスト (AC-1 〜 AC-7)
# ---------------------------------------------------------------------------


def _make_docai_tsv(path: Path, type_name: str, fields: list[str], rows: list[list[str]] | None = None) -> None:
    """テスト用の docai TSV ファイルを作成する。"""
    lines = [f"## {type_name}", "\t".join(fields)]
    if rows:
        for row in rows:
            lines.append("\t".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_schema_propose_directory_aggregates_multiple_docai_tsvs(monkeypatch, tmp_path):
    """AC-1: ディレクトリに a.docai.tsv と b.docai.tsv → 両方集約され types に両型が出る。"""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    _make_docai_tsv(input_dir / "a.docai.tsv", "TypeA", ["field1", "field2"])
    _make_docai_tsv(input_dir / "b.docai.tsv", "TypeB", ["field3", "field4"])

    monkeypatch.setattr(main_mod, "OUTPUT_DIR", Path("Output"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "schema_propose", "--output-dir", str(output_dir), str(input_dir)],
    )

    main_mod.main()

    result = json.loads((output_dir / "schema_proposal.json").read_text(encoding="utf-8"))
    type_names = {t["type_name"] for t in result["types"]}
    assert "TypeA" in type_names
    assert "TypeB" in type_names
    assert len(result["types"]) == 2


def test_schema_propose_directory_filters_non_docai_tsv(monkeypatch, tmp_path):
    """AC-2: ディレクトリに a.docai.tsv と notes.tsv → a.docai.tsv のみ対象。"""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    _make_docai_tsv(input_dir / "a.docai.tsv", "TypeA", ["field1"])
    _make_docai_tsv(input_dir / "notes.tsv", "TypeNotes", ["fieldX"])

    monkeypatch.setattr(main_mod, "OUTPUT_DIR", Path("Output"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "schema_propose", "--output-dir", str(output_dir), str(input_dir)],
    )

    main_mod.main()

    result = json.loads((output_dir / "schema_proposal.json").read_text(encoding="utf-8"))
    type_names = {t["type_name"] for t in result["types"]}
    assert "TypeA" in type_names
    assert "TypeNotes" not in type_names


def test_schema_propose_directory_with_no_docai_tsvs_exits_with_error(monkeypatch, tmp_path, capsys):
    """AC-3: 対象 *.docai*.tsv が 0 件のディレクトリ → SystemExit(1)、stderr に「docai TSV が見つかりません」。"""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "notes.tsv").write_text("unrelated\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    monkeypatch.setattr(main_mod, "OUTPUT_DIR", Path("Output"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "schema_propose", "--output-dir", str(output_dir), str(input_dir)],
    )

    with pytest.raises(SystemExit) as excinfo:
        main_mod.main()

    captured = capsys.readouterr()
    assert excinfo.value.code == 1
    assert "docai TSV が見つかりません" in captured.err


def test_schema_propose_nonexistent_path_exits_with_error(monkeypatch, tmp_path, capsys):
    """AC-4: 存在しないパス → SystemExit(1)、stderr に「パスが見つかりません」。"""
    nonexistent = tmp_path / "does_not_exist"
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    monkeypatch.setattr(main_mod, "OUTPUT_DIR", Path("Output"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "schema_propose", "--output-dir", str(output_dir), str(nonexistent)],
    )

    with pytest.raises(SystemExit) as excinfo:
        main_mod.main()

    captured = capsys.readouterr()
    assert excinfo.value.code == 1
    assert "パスが見つかりません" in captured.err


def test_schema_propose_explicit_file_processed_without_filter(monkeypatch, tmp_path):
    """AC-5: *.docai*.tsv に非マッチな明示ファイル data.tsv を直接指定 → 後方互換でフィルタされず処理される。

    resolve_docai_tsvs はファイル引数に glob フィルタを掛けないことを証明する。
    data.tsv は DOCAI_TSV_GLOB="*.docai*.tsv" に非マッチのため、
    誤って明示ファイルにもフィルタを掛ける実装では結果が空になり、このテストは失敗する。
    """
    tsv_file = tmp_path / "data.tsv"
    _make_docai_tsv(tsv_file, "DataType", ["col1", "col2"])

    # *.docai*.tsv に非マッチな data.tsv でも resolve_docai_tsvs は [tsv_file] を返す
    result = main_mod.resolve_docai_tsvs([str(tsv_file)])
    assert result == [tsv_file]


def test_schema_propose_file_and_directory_combined(monkeypatch, tmp_path):
    """AC-6: 明示ファイル + ディレクトリ混在 → 両者の和集合を処理し全型が集約される。"""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    explicit_file = tmp_path / "explicit.docai.tsv"
    _make_docai_tsv(explicit_file, "ExplicitType", ["f1"])
    _make_docai_tsv(input_dir / "dir_file.docai.tsv", "DirType", ["f2"])

    monkeypatch.setattr(main_mod, "OUTPUT_DIR", Path("Output"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "nova-parser",
            "--mode",
            "schema_propose",
            "--output-dir",
            str(output_dir),
            str(explicit_file),
            str(input_dir),
        ],
    )

    main_mod.main()

    result = json.loads((output_dir / "schema_proposal.json").read_text(encoding="utf-8"))
    type_names = {t["type_name"] for t in result["types"]}
    assert "ExplicitType" in type_names
    assert "DirType" in type_names


def test_schema_propose_directory_does_not_recurse_into_subdirectory(monkeypatch, tmp_path):
    """AC-7: ディレクトリ指定時、サブディレクトリ dir/sub/c.docai.tsv は非再帰のため対象外。"""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    sub_dir = input_dir / "sub"
    sub_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    _make_docai_tsv(input_dir / "top.docai.tsv", "TopType", ["f1"])
    _make_docai_tsv(sub_dir / "c.docai.tsv", "SubType", ["f2"])

    monkeypatch.setattr(main_mod, "OUTPUT_DIR", Path("Output"))
    monkeypatch.setattr(
        sys,
        "argv",
        ["nova-parser", "--mode", "schema_propose", "--output-dir", str(output_dir), str(input_dir)],
    )

    main_mod.main()

    result = json.loads((output_dir / "schema_proposal.json").read_text(encoding="utf-8"))
    type_names = {t["type_name"] for t in result["types"]}
    assert "TopType" in type_names
    assert "SubType" not in type_names
