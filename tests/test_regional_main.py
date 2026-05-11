"""regional_ocr.main CLI エントリポイントのテスト（AC-C-21〜AC-C-25）。

テスト戦略:
- uvicorn.run は monkeypatch.setattr で差し替えて実際には起動しない
- main() の引数パースと AppState 構築が正しいことを確認
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# AC-C-21: from nova_parser.regional_ocr import create_app, main が ImportError なし
# ---------------------------------------------------------------------------


def test_import_create_app_and_main_from_regional_ocr_no_import_error():
    """AC-C-21: from nova_parser.regional_ocr import create_app, main が ImportError なし。"""
    from nova_parser.regional_ocr import create_app, main  # noqa: F401


# ---------------------------------------------------------------------------
# AC-C-22: main(argv=[image_dir]) で uvicorn.run が host='127.0.0.1', port=8000
# ---------------------------------------------------------------------------


def test_main_default_host_and_port(tmp_path, monkeypatch):
    """AC-C-22: main(argv=[image_dir]) で uvicorn.run が host='127.0.0.1', port=8000 で呼ばれる。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()

    captured = {}

    def _fake_uvicorn_run(app, *, host, port):
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("nova_parser.regional_ocr.main.uvicorn.run", _fake_uvicorn_run)

    from nova_parser.regional_ocr.main import main

    main(argv=[str(image_dir)])

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000


# ---------------------------------------------------------------------------
# AC-C-23: main(argv=[image_dir, '--host', '0.0.0.0', '--port', '9000']) で正しいバインド
# ---------------------------------------------------------------------------


def test_main_custom_host_and_port(tmp_path, monkeypatch):
    """AC-C-23: main(argv=[image_dir, '--host', '0.0.0.0', '--port', '9000']) で
    uvicorn.run が host='0.0.0.0', port=9000。
    """
    image_dir = tmp_path / "images"
    image_dir.mkdir()

    captured = {}

    def _fake_uvicorn_run(app, *, host, port):
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("nova_parser.regional_ocr.main.uvicorn.run", _fake_uvicorn_run)

    from nova_parser.regional_ocr.main import main

    main(argv=[str(image_dir), "--host", "0.0.0.0", "--port", "9000"])

    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9000


# ---------------------------------------------------------------------------
# AC-C-24: main(argv=[image_dir, '--output-dir', tmp_output]) で output_dir が resolve() 済み
# ---------------------------------------------------------------------------


def test_main_output_dir_is_resolved(tmp_path, monkeypatch):
    """AC-C-24: main(argv=[image_dir, '--output-dir', tmp_output]) で
    uvicorn.run の app.state.app_state.output_dir == tmp_output.resolve()。
    """
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    tmp_output = tmp_path / "custom_output"

    captured = {}

    def _fake_uvicorn_run(app, *, host, port):
        captured["app"] = app

    monkeypatch.setattr("nova_parser.regional_ocr.main.uvicorn.run", _fake_uvicorn_run)

    from nova_parser.regional_ocr.main import main

    main(argv=[str(image_dir), "--output-dir", str(tmp_output)])

    app = captured["app"]
    assert app.state.app_state.output_dir == tmp_output.resolve()


# ---------------------------------------------------------------------------
# AC-C-20b: main(argv=[image_dir]) で create_app に渡される AppState の image_dir.name が一致
# ---------------------------------------------------------------------------


def test_main_passes_image_dir_to_app_state(tmp_path, monkeypatch):
    """AC-C-20: main(argv=[image_dir]) を呼ぶと、create_app に渡される AppState の
    image_dir.name が argv で指定したディレクトリ名と一致する。
    """
    captured: dict = {}

    def _fake_uvicorn_run(app, *, host: str = "127.0.0.1", port: int = 8000) -> None:
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("nova_parser.regional_ocr.main.uvicorn.run", _fake_uvicorn_run)

    image_dir = tmp_path / "my_images"
    image_dir.mkdir()
    from nova_parser.regional_ocr.main import main

    main(argv=[str(image_dir)])

    assert captured["app"].state.app_state.image_dir.name == "my_images"


# ---------------------------------------------------------------------------
# AC-C-25: pyproject.toml に nova-parser-regional スクリプト・fastapi/uvicorn 依存・httpx dev 依存
# ---------------------------------------------------------------------------


def test_pyproject_toml_has_required_scripts_and_dependencies():
    """AC-C-25: pyproject.toml に nova-parser-regional スクリプト、fastapi/uvicorn 依存、
    httpx dev 依存が定義されている。
    """
    import tomllib

    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    # nova-parser-regional スクリプトの確認
    scripts = pyproject.get("project", {}).get("scripts", {})
    assert "nova-parser-regional" in scripts, "nova-parser-regional スクリプトが定義されていない"

    # fastapi と uvicorn が project.dependencies に含まれているか
    dependencies = pyproject.get("project", {}).get("dependencies", [])
    dep_names = [d.split(">=")[0].split("==")[0].split("[")[0].lower() for d in dependencies]
    assert "fastapi" in dep_names, f"fastapi が project.dependencies にない: {dep_names}"
    assert "uvicorn" in dep_names, f"uvicorn が project.dependencies にない: {dep_names}"

    # httpx が dev dependencies に含まれているか
    dev_deps = pyproject.get("dependency-groups", {}).get("dev", [])
    dev_dep_names = [d.split(">=")[0].split("==")[0].split("[")[0].lower() for d in dev_deps]
    assert "httpx" in dev_dep_names, f"httpx が dev dependencies にない: {dev_dep_names}"
