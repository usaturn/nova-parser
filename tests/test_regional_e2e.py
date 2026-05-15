"""regional_ocr Frontend + ローカル E2E テスト（Phase D）。

テスト戦略:
- 外部 API（Cloud Vision）は FakeVisionClient でモック（conftest.py から共有）
- FastAPI は TestClient（httpx ベース）を使用
- ブラウザは起動しない。HTML/JS/CSS の配信検証 + API フルパスを pytest だけで通す
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tests.conftest import FakeVisionClient, _FakeResponse


def _write_png(path: Path, size: tuple[int, int] = (100, 100)) -> None:
    Image.new("RGB", size, color=(128, 128, 128)).save(path)


def _make_client(image_dir: Path, output_dir: Path, factory):
    from fastapi.testclient import TestClient

    from nova_parser.regional_ocr.app import create_app
    from nova_parser.regional_ocr.state import AppState

    state = AppState(image_dir=image_dir, output_dir=output_dir, vision_client_factory=factory)
    return TestClient(create_app(state), raise_server_exceptions=False)


def _simple_factory(client: FakeVisionClient):
    def _factory():
        return client

    return _factory


# ---------------------------------------------------------------------------
# D-1: 基本配信テスト
# ---------------------------------------------------------------------------


def test_index_html_loads_app_js_before_alpine_cdn(tmp_path):
    """app.js が Alpine CDN より先に <script> として出現すること（auto-init race 回避）。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    body = client.get("/").text
    idx_app = body.find("/static/app.js")
    idx_alpine = body.lower().find("alpinejs")

    assert idx_app >= 0, "app.js の <script> が見つからない"
    assert idx_alpine >= 0, "Alpine CDN の <script> が見つからない"
    assert idx_app < idx_alpine, "app.js は Alpine CDN より先に評価される必要がある"


def test_get_root_returns_html_with_alpine_script_tag(tmp_path):
    """GET / が 200、text/html、本文に alpinejs を含む。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "alpinejs" in resp.text.lower()


def test_get_static_app_js_returns_200_with_javascript_mime(tmp_path):
    """GET /static/app.js が 200 で配信され、JavaScript MIME を持つ。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/static/app.js")

    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"].lower()


def test_get_static_styles_css_returns_200_with_css_mime(tmp_path):
    """GET /static/styles.css が 200 で配信され、CSS MIME を持つ。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/static/styles.css")

    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"].lower()


def test_existing_api_routes_still_work_with_static_mount(tmp_path):
    """static mount 追加後も既存 /api/images が回帰しない。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png")
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/api/images")

    assert resp.status_code == 200
    assert "a.png" in resp.json()["images"]


# ---------------------------------------------------------------------------
# D-4: フル E2E（list → PUT → batch SSE → GET で結果反映）
# ---------------------------------------------------------------------------


def test_full_workflow_list_put_batch_stream_get(tmp_path):
    """画像配置 → 一覧 → 矩形 PUT → バッチ OCR SSE → セッション再取得で done 反映を確認。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img1.png", (100, 100))
    _write_png(image_dir / "img2.png", (100, 100))
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    responses = [
        _FakeResponse(text="OCR結果-1-0"),
        _FakeResponse(text="OCR結果-1-1"),
        _FakeResponse(text="OCR結果-2-0"),
        _FakeResponse(text="OCR結果-2-1"),
    ]
    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient(responses)))

    list_resp = client.get("/api/images")
    assert list_resp.status_code == 200
    assert set(list_resp.json()["images"]) == {"img1.png", "img2.png"}

    for image_name, prefix in [("img1.png", "p1"), ("img2.png", "p2")]:
        put_resp = client.put(
            f"/api/session/{image_name}",
            json={
                "image_name": image_name,
                "image_width": 100,
                "image_height": 100,
                "regions": [
                    {
                        "rectangle": {
                            "rect_id": f"{prefix}-r0",
                            "draw_order": 0,
                            "x": 0,
                            "y": 0,
                            "width": 40,
                            "height": 40,
                        },
                        "text": None,
                        "ocr_status": "pending",
                        "ocr_error": None,
                        "ocr_completed_at": None,
                    },
                    {
                        "rectangle": {
                            "rect_id": f"{prefix}-r1",
                            "draw_order": 1,
                            "x": 50,
                            "y": 50,
                            "width": 40,
                            "height": 40,
                        },
                        "text": None,
                        "ocr_status": "pending",
                        "ocr_error": None,
                        "ocr_completed_at": None,
                    },
                ],
                "schema_version": 1,
            },
        )
        assert put_resp.status_code == 200

    with client.stream("POST", "/api/ocr/batch/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = [line for line in resp.iter_lines() if line.startswith("data: ")]

    items = [json.loads(line[len("data: ") :]) for line in lines]
    assert len(items) == 4
    assert all(item["status"] == "done" for item in items)

    final = client.get("/api/session/img1.png").json()
    assert {r["rectangle"]["rect_id"]: r["ocr_status"] for r in final["regions"]} == {
        "p1-r0": "done",
        "p1-r1": "done",
    }
    texts = {r["rectangle"]["rect_id"]: r["text"] for r in final["regions"]}
    assert texts["p1-r0"] == "OCR結果-1-0"
    assert texts["p1-r1"] == "OCR結果-1-1"
