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


def test_session_put_order_preserves_latest_state_across_image_switch(tmp_path):
    """画像切替を跨いだ PUT 順序契約の回帰テスト。

    JS 側の autosave race（in-flight save と pending flush の順序）は client-only で
    Python から直接検証できないが、修正後の JS が出すであろう PUT 順序
    （image A の v1 → v2 → image B の v1）を Python から再現し、backend が
    last-write-wins で動くこと、および画像間の cross-contamination が発生しないことを
    invariant として固定する。
    """
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img_a.png", (100, 100))
    _write_png(image_dir / "img_b.png", (100, 100))
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))

    def _session_payload(image_name: str, rect_ids: list[str]) -> dict:
        return {
            "image_name": image_name,
            "image_width": 100,
            "image_height": 100,
            "regions": [
                {
                    "rectangle": {
                        "rect_id": rect_id,
                        "draw_order": idx,
                        "x": idx * 10,
                        "y": idx * 10,
                        "width": 30,
                        "height": 30,
                    },
                    "text": None,
                    "ocr_status": "pending",
                    "ocr_error": None,
                    "ocr_completed_at": None,
                }
                for idx, rect_id in enumerate(rect_ids)
            ],
            "schema_version": 1,
        }

    # 1) img_a の v1 (1 矩形): 修正後 JS の inFlightSave 相当
    r1 = client.put("/api/session/img_a.png", json=_session_payload("img_a.png", ["a-r0"]))
    assert r1.status_code == 200

    # 2) img_a の v2 (2 矩形に更新): 修正後 JS の pending flush 相当
    r2 = client.put("/api/session/img_a.png", json=_session_payload("img_a.png", ["a-r0", "a-r1"]))
    assert r2.status_code == 200

    # 3) img_b の v1 (画像切替後の新画像初期化)
    r3 = client.put("/api/session/img_b.png", json=_session_payload("img_b.png", ["b-r0"]))
    assert r3.status_code == 200

    final_a = client.get("/api/session/img_a.png").json()
    final_b = client.get("/api/session/img_b.png").json()

    assert [r["rectangle"]["rect_id"] for r in final_a["regions"]] == ["a-r0", "a-r1"], (
        "img_a が v2 (最新編集) を保持していない"
    )
    assert [r["rectangle"]["rect_id"] for r in final_b["regions"]] == ["b-r0"], (
        "img_b への書き込みが img_a に漏れ出している"
    )


# ---------------------------------------------------------------------------
# ブロック選択モード（ブロック検出 → キャッシュ → 矩形 PUT → OCR）
# ---------------------------------------------------------------------------


def test_index_html_contains_block_mode_toggle(tmp_path):
    """GET / の HTML にブロック選択トグルと粒度セレクタが含まれる。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    body = client.get("/").text

    assert "ブロック選択" in body
    assert "段組選択" not in body, "旧称が残っている"
    assert "toggleBlockMode" in body
    assert "blockGranularity" in body
    assert "縦ブロック" in body
    assert "段落" in body


def test_block_select_workflow_detect_cache_put_ocr(tmp_path):
    """blocks 取得 → 2 回目はキャッシュ → ブロック矩形を PUT → 単発 OCR で done のフルパス。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img1.png", (100, 100))
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    responses = [
        _FakeResponse(blocks=[[(10, 10), (60, 10), (60, 40), (10, 40)]]),  # document_text_detection 用
        _FakeResponse(text="段組OCR結果"),  # 段落粒度の単発 OCR (text_detection) 用
        _FakeResponse(text="縦ブロックOCR結果"),  # 縦ブロック粒度の単発 OCR 用
    ]
    fake = FakeVisionClient(responses)
    client = _make_client(image_dir, output_dir, _simple_factory(fake))

    first = client.get("/api/blocks/img1.png")
    assert first.status_code == 200
    block = first.json()["blocks"][0]
    assert block == {"x": 10, "y": 10, "width": 50, "height": 30}

    second = client.get("/api/blocks/img1.png")
    assert second.json() == first.json()
    assert len(fake.document_calls) == 1, "2 回目はキャッシュで Vision を呼ばない"

    put_resp = client.put(
        "/api/session/img1.png",
        json={
            "image_name": "img1.png",
            "image_width": 100,
            "image_height": 100,
            "regions": [
                {
                    "rectangle": {"rect_id": "blk-r0", "draw_order": 0, **block},
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

    ocr_resp = client.post("/api/ocr/img1.png/blk-r0")
    assert ocr_resp.status_code == 200
    assert ocr_resp.json()["ocr_status"] == "done"
    assert ocr_resp.json()["text"] == "段組OCR結果"

    # 縦ブロック粒度でも Region 作成 → 保存 → OCR が動く（スペック 11.5）
    vertical = first.json()["vertical_blocks"]
    assert vertical, "vertical_blocks が返っていない"
    v_block = vertical[0]
    put_v = client.put(
        "/api/session/img1.png",
        json={
            "image_name": "img1.png",
            "image_width": 100,
            "image_height": 100,
            "regions": [
                {
                    "rectangle": {"rect_id": "blk-r0", "draw_order": 0, **block},
                    "text": None,
                    "ocr_status": "pending",
                    "ocr_error": None,
                    "ocr_completed_at": None,
                },
                {
                    "rectangle": {"rect_id": "vblk-r0", "draw_order": 1, **v_block},
                    "text": None,
                    "ocr_status": "pending",
                    "ocr_error": None,
                    "ocr_completed_at": None,
                },
            ],
            "schema_version": 1,
        },
    )
    assert put_v.status_code == 200

    ocr_v = client.post("/api/ocr/img1.png/vblk-r0")
    assert ocr_v.status_code == 200
    assert ocr_v.json()["ocr_status"] == "done"


def test_index_html_contains_undone_panel_markup(tmp_path):
    """index.html に未 OCR 一覧パネル（見出し・更新ハンドラ）が含まれる。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    body = client.get("/").text

    assert "未 OCR（全画像）" in body
    assert "refreshUndone()" in body
    assert "jumpToUndone(item)" in body


def test_index_html_contains_undone_bulk_run_button(tmp_path):
    """index.html に未 OCR 一括実行ボタンが含まれる。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    body = client.get("/").text

    assert "runUndoneOcr()" in body
    assert "未 OCR を一括実行" in body


# ---------------------------------------------------------------------------
# 未 OCR 一覧 → include_errors=true 一括実行 のフルパス
# ---------------------------------------------------------------------------


def test_undone_list_then_bulk_run_completes_all_regions(tmp_path):
    """複数画像に pending + error を配置 → 一覧列挙 → include_errors=true で一括実行 → 全件 done → 一覧空。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png")
    _write_png(image_dir / "b.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    save_session(
        ImageSession(
            image_name="a.png",
            image_width=100,
            image_height=100,
            regions=[
                RegionRecord(
                    rectangle=Rectangle(rect_id="a0", draw_order=0, x=0, y=0, width=40, height=40),
                    ocr_status="pending",
                ),
                RegionRecord(
                    rectangle=Rectangle(rect_id="a1", draw_order=1, x=50, y=0, width=40, height=40),
                    ocr_status="error",
                    ocr_error="quota exceeded",
                ),
            ],
        ),
        output_dir,
    )
    save_session(
        ImageSession(
            image_name="b.png",
            image_width=100,
            image_height=100,
            regions=[
                RegionRecord(
                    rectangle=Rectangle(rect_id="b0", draw_order=0, x=0, y=0, width=40, height=40),
                    ocr_status="pending",
                ),
                RegionRecord(
                    rectangle=Rectangle(rect_id="b1", draw_order=1, x=50, y=0, width=40, height=40),
                    text="済み",
                    ocr_status="done",
                ),
            ],
        ),
        output_dir,
    )

    fake = FakeVisionClient([_FakeResponse(text="A0"), _FakeResponse(text="A1"), _FakeResponse(text="B0")])
    client = _make_client(image_dir, output_dir, _simple_factory(fake))

    # 1. 未 OCR 一覧: done (b1) を除く 3 件が画像名順 → draw_order 順で返る
    resp = client.get("/api/regions/undone")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [(i["image_name"], i["rect_id"], i["ocr_status"]) for i in items] == [
        ("a.png", "a0", "pending"),
        ("a.png", "a1", "error"),
        ("b.png", "b0", "pending"),
    ]

    # 2. include_errors=true で一括実行: error の a1 も再試行され全 3 件 done
    with client.stream("POST", "/api/ocr/batch/stream?include_errors=true") as sresp:
        assert sresp.status_code == 200
        lines = [line for line in sresp.iter_lines() if line.startswith("data: ")]
    events = [json.loads(line[len("data: ") :]) for line in lines]
    assert len(events) == 3
    assert all(e["status"] == "done" for e in events)

    # 3. 一覧が空になり、done テキストは保持される
    resp = client.get("/api/regions/undone")
    assert resp.json()["items"] == []
    session_resp = client.get("/api/session/b.png")
    by_id = {r["rectangle"]["rect_id"]: r for r in session_resp.json()["regions"]}
    assert by_id["b1"]["text"] == "済み"
