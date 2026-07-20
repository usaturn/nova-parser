"""regional_ocr FastAPI ルート層のテスト（AC-C-01〜AC-C-20）。

テスト戦略:
- 外部 API（Cloud Vision）は FakeVisionClient でモック（conftest.py から共有）
- FastAPI は TestClient（httpx ベース）を使用
- SSE ストリームは client.stream() + iter_lines() で受信
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tests.conftest import FakeVisionClient, _FakeResponse

# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _write_png(path: Path, size: tuple[int, int] = (100, 100)) -> None:
    """テスト用 PNG を tmp_path 下に生成する。"""
    Image.new("RGB", size, color=(128, 128, 128)).save(path)


def _make_client(image_dir: Path, output_dir: Path, factory):
    """create_app + TestClient を組み立てて返す。"""
    from fastapi.testclient import TestClient

    from nova_parser.regional_ocr.app import create_app
    from nova_parser.regional_ocr.state import AppState

    state = AppState(image_dir=image_dir, output_dir=output_dir, vision_client_factory=factory)
    return TestClient(create_app(state), raise_server_exceptions=False)


def _simple_factory(client: FakeVisionClient):
    """vision_client_factory として使うシンプルな callable。"""

    def _factory():
        return client

    return _factory


# ---------------------------------------------------------------------------
# AC-C-01: GET /api/images — PNG 2 件存在時に 200 + images に 2 件
# ---------------------------------------------------------------------------


def test_get_images_returns_200_and_two_filenames_when_two_pngs_exist(tmp_path):
    """AC-C-01: GET /api/images を、image_dir に PNG ファイルが 2 件存在する AppState を持つ
    TestClient で呼び出したとき、HTTP 200 かつレスポンス JSON の images フィールドに
    2 件のファイル名が含まれる。
    """
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png")
    _write_png(image_dir / "b.png")
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/api/images")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["images"]) == 2
    assert "a.png" in data["images"]
    assert "b.png" in data["images"]


# ---------------------------------------------------------------------------
# AC-C-02: GET /api/images — stem 衝突時に 200 + warnings に 'stem collision: '
# ---------------------------------------------------------------------------


def test_get_images_returns_warnings_on_stem_collision(tmp_path):
    """AC-C-02: GET /api/images を、image_dir に stem 衝突（foo.png と foo.webp）が存在する
    AppState で呼び出したとき、HTTP 200 かつレスポンス JSON の warnings フィールドに
    'stem collision: ' を含む文字列が 1 件以上存在する。
    """
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "foo.png")
    Image.new("RGB", (50, 50)).save(image_dir / "foo.webp")
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/api/images")

    assert resp.status_code == 200
    data = resp.json()
    assert any("stem collision: " in w for w in data["warnings"])


# ---------------------------------------------------------------------------
# AC-C-03: GET /api/image/{name} — 存在する PNG で 200 + image_width/image_height/mime_type
# ---------------------------------------------------------------------------


def test_get_image_meta_returns_200_with_width_height_and_png_mime(tmp_path):
    """AC-C-03: GET /api/image/{name} を、name に実在する PNG ファイル名を渡した TestClient で
    呼び出したとき、HTTP 200 かつレスポンス JSON に image_width, image_height, mime_type が存在し、
    mime_type が 'image/png' である。
    """
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "test.png", size=(200, 150))
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/api/image/test.png")

    assert resp.status_code == 200
    data = resp.json()
    assert data["image_width"] == 200
    assert data["image_height"] == 150
    assert data["mime_type"] == "image/png"


# ---------------------------------------------------------------------------
# AC-C-04: GET /api/image/{name} — 存在しないファイル名で 404
# ---------------------------------------------------------------------------


def test_get_image_meta_returns_404_for_nonexistent_file(tmp_path):
    """AC-C-04: GET /api/image/{name} を、image_dir に存在しないファイル名で呼び出したとき、
    HTTP 404 が返る。
    """
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/api/image/nonexistent.png")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC-C-05: GET /api/image/{name} — name='../etc/passwd' で 400
# ---------------------------------------------------------------------------


def test_get_image_meta_returns_400_for_path_traversal(tmp_path):
    """AC-C-05: name に '..' セグメントを含むパス（URL エンコード）で 400 が返る。

    '/api/image/../etc/passwd' は httpx が RFC 準拠で '/api/etc/passwd' に正規化するため、
    ルート '/api/image/{name}' にマッチしなくなる。また '%2F' を含むパスは Starlette の
    単一セグメント {name} コンバータがマッチさせない（スラッシュを含むセグメントは不可）。

    回避策: '..' を '%2E%2E' と URL エンコードし、'/api/image/%2E%2E' として送信する。
    FastAPI はパスパラメータを自動デコードするため、ハンドラには name='..' が渡り、
    resolve_image() の segment == ".." チェックで ImagePathTraversalError が raise → 400。
    """
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    # '..' を %2E%2E でエンコードして httpx の path 正規化と Starlette のルートマッチング制約を回避する
    resp = client.get("/api/image/%2E%2E")

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# AC-C-06: GET /api/image/{name}/raw — Content-Type が 'image/png'、PNG シグネチャ一致
# ---------------------------------------------------------------------------


def test_get_image_raw_returns_png_content_type_and_png_signature(tmp_path):
    """AC-C-06: GET /api/image/{name}/raw を呼び出したとき、Content-Type が 'image/png'、
    ボディ先頭 8 バイトが PNG シグネチャと一致する。
    """
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "photo.png")
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/api/image/photo.png/raw")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    png_signature = b"\x89PNG\r\n\x1a\n"
    assert resp.content[:8] == png_signature


# ---------------------------------------------------------------------------
# AC-C-07: GET /api/session/{name} — 未保存状態で regions が空リスト
# ---------------------------------------------------------------------------


def test_get_session_returns_empty_regions_when_no_session_saved(tmp_path):
    """AC-C-07: GET /api/session/{name} を未保存状態で呼び出したとき regions が空リスト。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/api/session/img.png")

    assert resp.status_code == 200
    data = resp.json()
    assert data["regions"] == []


# ---------------------------------------------------------------------------
# AC-C-08: GET /api/session/{name} — 保存済み状態で RegionRecord が 1 件含まれる
# ---------------------------------------------------------------------------


def test_get_session_returns_saved_region_record(tmp_path):
    """AC-C-08: GET /api/session/{name} を保存済み状態で呼び出したとき RegionRecord が 1 件含まれる。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)

    rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
    record = RegionRecord(rectangle=rect, ocr_status="pending")
    session = ImageSession(image_name="img.png", image_width=100, image_height=100, regions=[record])
    save_session(session, output_dir)

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/api/session/img.png")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["regions"]) == 1
    assert data["regions"][0]["rectangle"]["rect_id"] == "r1"


# ---------------------------------------------------------------------------
# AC-C-09: PUT /api/session/{name} — pending 1 件を含む body で regions.json 生成
# ---------------------------------------------------------------------------


def test_put_session_creates_regions_json_with_pending_record(tmp_path):
    """AC-C-09: PUT /api/session/{name} に pending RegionRecord 1 件を含む body で呼び出すと、
    output_dir に {stem}.regions.json が生成され regions[0].ocr_status が 'pending'。
    """
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))

    body = {
        "image_name": "img.png",
        "image_width": 100,
        "image_height": 100,
        "regions": [
            {
                "rectangle": {"rect_id": "r1", "draw_order": 0, "x": 0, "y": 0, "width": 50, "height": 50},
                "ocr_status": "pending",
            }
        ],
    }
    resp = client.put("/api/session/img.png", json=body)

    assert resp.status_code == 200
    json_path = output_dir / "img.regions.json"
    assert json_path.exists()
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["regions"][0]["ocr_status"] == "pending"


# ---------------------------------------------------------------------------
# AC-C-10: PUT /api/session/{name} — done レコードの保護ロジック
# ---------------------------------------------------------------------------


def test_put_session_preserves_done_record_when_pending_request_sent(tmp_path):
    """AC-C-10: PUT /api/session/{name} で既存 done レコードがあるとき、
    同 rect_id の pending リクエストに対して text/ocr_status='done'/ocr_completed_at が保持される。
    """
    import datetime

    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)

    completed_at = datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
    done_record = RegionRecord(
        rectangle=rect, text="OCR完了テキスト", ocr_status="done", ocr_completed_at=completed_at
    )
    session = ImageSession(image_name="img.png", image_width=100, image_height=100, regions=[done_record])
    save_session(session, output_dir)

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))

    # 同じ rect_id を pending で PUT
    body = {
        "image_name": "img.png",
        "image_width": 100,
        "image_height": 100,
        "regions": [
            {
                "rectangle": {"rect_id": "r1", "draw_order": 0, "x": 0, "y": 0, "width": 50, "height": 50},
                "ocr_status": "pending",
            }
        ],
    }
    resp = client.put("/api/session/img.png", json=body)

    assert resp.status_code == 200
    data = resp.json()
    region = data["regions"][0]
    # done が保護される
    assert region["ocr_status"] == "done"
    assert region["text"] == "OCR完了テキスト"
    assert region["ocr_completed_at"] is not None


# ---------------------------------------------------------------------------
# AC-C-11: PUT 保護ロジック — rectangle 座標はリクエスト側を採用
# ---------------------------------------------------------------------------


def test_put_session_adopts_request_rectangle_coordinates_even_for_done_record(tmp_path):
    """AC-C-11: PUT 保護ロジックで rectangle 座標はリクエスト側を採用する。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)

    rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
    done_record = RegionRecord(rectangle=rect, text="text", ocr_status="done")
    session = ImageSession(image_name="img.png", image_width=100, image_height=100, regions=[done_record])
    save_session(session, output_dir)

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))

    # 新しい座標でリクエスト（x=10, y=20, width=60, height=70）
    body = {
        "image_name": "img.png",
        "image_width": 100,
        "image_height": 100,
        "regions": [
            {
                "rectangle": {"rect_id": "r1", "draw_order": 0, "x": 10, "y": 20, "width": 60, "height": 70},
                "ocr_status": "pending",
            }
        ],
    }
    resp = client.put("/api/session/img.png", json=body)

    assert resp.status_code == 200
    data = resp.json()
    rect_data = data["regions"][0]["rectangle"]
    # リクエスト側の座標が採用される
    assert rect_data["x"] == 10
    assert rect_data["y"] == 20
    assert rect_data["width"] == 60
    assert rect_data["height"] == 70


# ---------------------------------------------------------------------------
# AC-C-11b: PUT /api/session/{name} — URL name と body image_name が異なる → 400
# ---------------------------------------------------------------------------


def test_put_session_returns_400_when_url_name_and_body_image_name_differ(tmp_path):
    """AC-C-11b: PUT /api/session/{name} で URL の name と body.image_name が異なる場合、
    400 (ValueError ハンドラ経由) が返り detail に不整合メッセージが含まれる。
    """
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "photo.png", (100, 100))
    _write_png(image_dir / "other.png", (100, 100))
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    body = {
        "image_name": "other.png",  # URL の name="photo.png" と一致しない
        "image_width": 100,
        "image_height": 100,
        "regions": [],
        "schema_version": 1,
    }
    resp = client.put("/api/session/photo.png", json=body)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "image_name" in detail or "一致しません" in detail


# ---------------------------------------------------------------------------
# AC-C-12: POST /api/ocr/{name}/{rect_id} — FakeVisionClient が text='OCR結果' → 200 + done
# ---------------------------------------------------------------------------


def test_post_ocr_returns_200_with_done_status_and_text(tmp_path):
    """AC-C-12: POST /api/ocr/{name}/{rect_id} で FakeVisionClient が text='OCR結果' を返す状態のとき、
    200 + text='OCR結果'/ocr_status='done'。
    """
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)

    rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
    record = RegionRecord(rectangle=rect, ocr_status="pending")
    session = ImageSession(image_name="img.png", image_width=100, image_height=100, regions=[record])
    save_session(session, output_dir)

    fake_client = FakeVisionClient(_FakeResponse(text="OCR結果"))
    client = _make_client(image_dir, output_dir, _simple_factory(fake_client))

    resp = client.post("/api/ocr/img.png/r1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "OCR結果"
    assert data["ocr_status"] == "done"


# ---------------------------------------------------------------------------
# AC-C-13: POST /api/ocr/{name}/{rect_id} — OcrBackendError 相当 → 200 + status='error'
# ---------------------------------------------------------------------------


def test_post_ocr_returns_200_with_error_status_when_vision_returns_error_message(tmp_path):
    """AC-C-13: POST /api/ocr/{name}/{rect_id} で OcrBackendError 相当（FakeVisionClient が
    error_message を返す）なら 200 + ocr_status='error' + ocr_error 非空。
    """
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)

    rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
    record = RegionRecord(rectangle=rect, ocr_status="pending")
    session = ImageSession(image_name="img.png", image_width=100, image_height=100, regions=[record])
    save_session(session, output_dir)

    fake_client = FakeVisionClient(_FakeResponse(error_message="backend error"))
    client = _make_client(image_dir, output_dir, _simple_factory(fake_client))

    resp = client.post("/api/ocr/img.png/r1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ocr_status"] == "error"
    assert data["ocr_error"]  # 非空


# ---------------------------------------------------------------------------
# AC-C-14: POST /api/ocr/{name}/{rect_id} — AdcNotConfiguredError → 502
# ---------------------------------------------------------------------------


def test_post_ocr_returns_502_when_adc_not_configured(tmp_path):
    """AC-C-14: POST /api/ocr/{name}/{rect_id} で vision_client_factory が
    AdcNotConfiguredError を raise → 502 + detail に 'gcloud auth application-default login' を含む。
    """
    from nova_parser.regional_ocr.errors import AdcNotConfiguredError
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)

    rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
    record = RegionRecord(rectangle=rect, ocr_status="pending")
    session = ImageSession(image_name="img.png", image_width=100, image_height=100, regions=[record])
    save_session(session, output_dir)

    def _adc_fail_factory():
        raise AdcNotConfiguredError("gcloud auth application-default login が必要です")

    client = _make_client(image_dir, output_dir, _adc_fail_factory)

    resp = client.post("/api/ocr/img.png/r1")

    assert resp.status_code == 502
    data = resp.json()
    assert "gcloud auth application-default login" in data.get("detail", "")


# ---------------------------------------------------------------------------
# AC-C-15: POST /api/ocr/{name}/{rect_id} — rect_id が session に存在しない → 404
# ---------------------------------------------------------------------------


def test_post_ocr_returns_404_when_rect_id_not_found(tmp_path):
    """AC-C-15: POST /api/ocr/{name}/{rect_id} で rect_id が session に存在しない → 404。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)

    rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
    record = RegionRecord(rectangle=rect, ocr_status="pending")
    session = ImageSession(image_name="img.png", image_width=100, image_height=100, regions=[record])
    save_session(session, output_dir)

    fake_client = FakeVisionClient(_FakeResponse(text="text"))
    client = _make_client(image_dir, output_dir, _simple_factory(fake_client))

    resp = client.post("/api/ocr/img.png/nonexistent_rect")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC-C-16: POST /api/ocr/batch/stream — stem 衝突あり → 409
# ---------------------------------------------------------------------------


def test_post_ocr_batch_stream_returns_409_on_stem_collision(tmp_path):
    """AC-C-16: POST /api/ocr/batch/stream で stem 衝突あり → 409。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "foo.png")
    Image.new("RGB", (50, 50)).save(image_dir / "foo.webp")
    output_dir = tmp_path / "output"

    fake_client = FakeVisionClient(_FakeResponse(text="text"))
    client = _make_client(image_dir, output_dir, _simple_factory(fake_client))

    resp = client.post("/api/ocr/batch/stream")

    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# AC-C-17: POST /api/ocr/batch/stream — 2 画像 × 矩形 2 個 → SSE 4 イベント (draw_order 昇順)
# ---------------------------------------------------------------------------


def test_post_ocr_batch_stream_emits_four_sse_events_in_draw_order(tmp_path):
    """AC-C-17: 2 画像 × 矩形 2 個（pending 4 件）を draw_order 昇順で push、
    各イベントの status='done' であり、同一画像内では draw_order=0 が draw_order=1 より先に来る。
    """
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img_a.png", (100, 100))
    _write_png(image_dir / "img_b.png", (100, 100))
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # FakeVisionClient は 4 回呼ばれる
    responses = [
        _FakeResponse(text="A0"),
        _FakeResponse(text="A1"),
        _FakeResponse(text="B0"),
        _FakeResponse(text="B1"),
    ]
    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient(responses)))

    # 各画像に 2 個ずつ region (draw_order=1 と draw_order=0、保存順は逆) を PUT
    for image_name, prefix in [("img_a.png", "a"), ("img_b.png", "b")]:
        client.put(
            f"/api/session/{image_name}",
            json={
                "image_name": image_name,
                "image_width": 100,
                "image_height": 100,
                "regions": [
                    {
                        "rectangle": {
                            "rect_id": f"{prefix}1",
                            "draw_order": 1,
                            "x": 50,
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
                            "rect_id": f"{prefix}0",
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
                ],
                "schema_version": 1,
            },
        )

    with client.stream("POST", "/api/ocr/batch/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = [line for line in resp.iter_lines() if line.startswith("data: ")]

    items = [json.loads(line[len("data: ") :]) for line in lines]
    assert len(items) == 4
    assert all(item["status"] == "done" for item in items)

    # 同一画像内では draw_order 0 → 1 の順
    a_items = [i for i in items if i["image_name"] == "img_a.png"]
    b_items = [i for i in items if i["image_name"] == "img_b.png"]
    assert len(a_items) == 2 and len(b_items) == 2
    assert a_items[0]["rect_id"] == "a0"
    assert a_items[1]["rect_id"] == "a1"
    assert b_items[0]["rect_id"] == "b0"
    assert b_items[1]["rect_id"] == "b1"


# ---------------------------------------------------------------------------
# AC-C-18: POST /api/ocr/batch/stream — vision_client_factory の呼び出しが正確に 1 回
# ---------------------------------------------------------------------------


def test_post_ocr_batch_stream_calls_vision_client_factory_exactly_once(tmp_path):
    """AC-C-18: POST /api/ocr/batch/stream で vision_client_factory の呼び出しが正確に 1 回。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session
    from tests.conftest import make_fake_factory

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img1.png")
    _write_png(image_dir / "img2.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)

    for img_name in ["img1.png", "img2.png"]:
        rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
        record = RegionRecord(rectangle=rect, ocr_status="pending")
        session = ImageSession(image_name=img_name, image_width=100, image_height=100, regions=[record])
        save_session(session, output_dir)

    fake_client = FakeVisionClient([_FakeResponse(text="t1"), _FakeResponse(text="t2")])
    factory = make_fake_factory(fake_client)

    from fastapi.testclient import TestClient

    from nova_parser.regional_ocr.app import create_app
    from nova_parser.regional_ocr.state import AppState

    state = AppState(image_dir=image_dir, output_dir=output_dir, vision_client_factory=factory)
    client = TestClient(create_app(state), raise_server_exceptions=False)

    with client.stream("POST", "/api/ocr/batch/stream") as resp:
        assert resp.status_code == 200
        list(resp.iter_lines())  # consume all

    assert factory.calls["calls"] == 1


# ---------------------------------------------------------------------------
# AC-C-19: POST /api/ocr/batch/stream — 1 件 error_message → status='error'、後続継続
# ---------------------------------------------------------------------------


def test_post_ocr_batch_stream_continues_after_one_error(tmp_path):
    """AC-C-19: POST /api/ocr/batch/stream で 1 件 error_message → 該当 item status='error'、後続継続。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img1.png")
    _write_png(image_dir / "img2.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)

    for img_name in ["img1.png", "img2.png"]:
        rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
        record = RegionRecord(rectangle=rect, ocr_status="pending")
        session = ImageSession(image_name=img_name, image_width=100, image_height=100, regions=[record])
        save_session(session, output_dir)

    # 最初の画像はエラー、2 番目は成功
    fake_client = FakeVisionClient([_FakeResponse(error_message="backend error"), _FakeResponse(text="ok")])
    client = _make_client(image_dir, output_dir, _simple_factory(fake_client))

    with client.stream("POST", "/api/ocr/batch/stream") as resp:
        assert resp.status_code == 200
        lines = [line for line in resp.iter_lines() if line.startswith("data: ")]
        items = [json.loads(line[len("data: ") :]) for line in lines]

    assert len(items) == 2
    statuses = {item["status"] for item in items}
    assert "error" in statuses
    assert "done" in statuses


# ---------------------------------------------------------------------------
# AC-C-10b: PUT /api/session/{name} — rect_id 重複 body → 422
# ---------------------------------------------------------------------------


def test_put_session_returns_422_when_rect_ids_duplicate(tmp_path):
    """AC-C-10: PUT /api/session/{name} で rect_id が重複する body → 422 (Pydantic ValidationError)。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "photo.png", (200, 150))
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    body = {
        "image_name": "photo.png",
        "image_width": 200,
        "image_height": 150,
        "regions": [
            {
                "rectangle": {"rect_id": "r1", "draw_order": 0, "x": 0, "y": 0, "width": 50, "height": 50},
                "text": None,
                "ocr_status": "pending",
                "ocr_error": None,
                "ocr_completed_at": None,
            },
            {
                "rectangle": {"rect_id": "r1", "draw_order": 1, "x": 60, "y": 0, "width": 50, "height": 50},
                "text": None,
                "ocr_status": "pending",
                "ocr_error": None,
                "ocr_completed_at": None,
            },
        ],
        "schema_version": 1,
    }
    resp = client.put("/api/session/photo.png", json=body)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AC-C-15b: POST /api/ocr/{name}/{rect_id} 成功後 .regions.json と .regions.md 更新
# ---------------------------------------------------------------------------


def test_post_ocr_writes_regions_json_and_md_after_success(tmp_path):
    """AC-C-15: POST /api/ocr/{name}/{rect_id} 成功後、output_dir 配下に
    {stem}.regions.json と {stem}.regions.md が更新される。
    """
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "photo.png", (100, 100))
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # 事前に session を PUT で作成（pending 状態の region を 1 件）
    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient([_FakeResponse(text="OCR結果")])))
    put_body = {
        "image_name": "photo.png",
        "image_width": 100,
        "image_height": 100,
        "regions": [
            {
                "rectangle": {"rect_id": "r1", "draw_order": 0, "x": 0, "y": 0, "width": 50, "height": 50},
                "text": None,
                "ocr_status": "pending",
                "ocr_error": None,
                "ocr_completed_at": None,
            },
        ],
        "schema_version": 1,
    }
    client.put("/api/session/photo.png", json=put_body)

    # OCR 実行
    resp = client.post("/api/ocr/photo.png/r1")
    assert resp.status_code == 200

    # サイドカ JSON と Markdown が作成されている
    assert (output_dir / "photo.regions.json").exists()
    assert (output_dir / "photo.regions.md").exists()
    assert "OCR結果" in (output_dir / "photo.regions.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# AC-C-20: create_app(state) が FastAPI を返し routes に必要なパスが含まれる
# ---------------------------------------------------------------------------


def test_create_app_returns_fastapi_with_required_routes(tmp_path):
    """AC-C-20: create_app(state) が FastAPI を返し、routes に
    '/api/images', '/api/image/{name}', '/api/image/{name}/raw',
    '/api/session/{name}', '/api/ocr/{name}/{rect_id}', '/api/ocr/batch/stream' が含まれる。
    """
    from fastapi import FastAPI

    from nova_parser.regional_ocr.app import create_app
    from nova_parser.regional_ocr.state import AppState

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"
    factory = _simple_factory(FakeVisionClient())
    state = AppState(image_dir=image_dir, output_dir=output_dir, vision_client_factory=factory)
    app = create_app(state)

    assert isinstance(app, FastAPI)

    # FastAPI のバージョンによっては include_router のルートが _IncludedRouter に
    # ネストされ、app.routes のトップレベルに path が現れないため、再帰的に収集する。
    def _collect_route_paths(routes) -> set[str]:
        paths: set[str] = set()
        for route in routes:
            path = getattr(route, "path", None)
            if path is not None:
                paths.add(path)
            sub = getattr(route, "routes", None)
            if sub is None:
                # _IncludedRouter は routes を持たず original_router 経由で保持する
                sub = getattr(getattr(route, "original_router", None), "routes", None)
            if sub:
                paths.update(_collect_route_paths(sub))
        return paths

    route_paths = _collect_route_paths(app.routes)
    assert "/api/images" in route_paths
    assert "/api/image/{name}" in route_paths
    assert "/api/image/{name}/raw" in route_paths
    assert "/api/session/{name}" in route_paths
    assert "/api/ocr/{name}/{rect_id}" in route_paths
    assert "/api/ocr/batch/stream" in route_paths


# ---------------------------------------------------------------------------
# GET /api/blocks/{name} — 段組ブロック検出＋キャッシュ
# ---------------------------------------------------------------------------


def test_get_blocks_detects_and_persists_on_first_call(tmp_path):
    """初回 GET /api/blocks/{name} は document_text_detection を 1 回呼び、結果を {stem}.blocks.json に保存する。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png", (100, 100))
    output_dir = tmp_path / "output"

    fake = FakeVisionClient(_FakeResponse(blocks=[[(10, 10), (60, 10), (60, 40), (10, 40)]]))
    client = _make_client(image_dir, output_dir, _simple_factory(fake))

    resp = client.get("/api/blocks/a.png")

    assert resp.status_code == 200
    data = resp.json()
    assert data["image_name"] == "a.png"
    assert data["image_width"] == 100
    assert data["image_height"] == 100
    assert data["blocks"] == [{"x": 10, "y": 10, "width": 50, "height": 30}]
    assert data["schema_version"] == 1
    assert (output_dir / "a.blocks.json").exists()
    assert len(fake.document_calls) == 1


def test_get_blocks_uses_cache_on_second_call(tmp_path):
    """2 回目の GET /api/blocks/{name} はキャッシュを返し、Vision API を呼ばない。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png", (100, 100))
    output_dir = tmp_path / "output"

    fake = FakeVisionClient(_FakeResponse(blocks=[[(10, 10), (60, 10), (60, 40), (10, 40)]]))
    client = _make_client(image_dir, output_dir, _simple_factory(fake))

    first = client.get("/api/blocks/a.png")
    second = client.get("/api/blocks/a.png")

    assert second.status_code == 200
    assert second.json() == first.json()
    assert len(fake.document_calls) == 1, "キャッシュヒット時は Vision を呼ばない"


def test_get_blocks_returns_404_for_unknown_image(tmp_path):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/api/blocks/missing.png")

    assert resp.status_code == 404


def test_get_blocks_returns_502_when_vision_reports_error(tmp_path):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png")
    output_dir = tmp_path / "output"

    fake = FakeVisionClient(_FakeResponse(error_message="vision down"))
    client = _make_client(image_dir, output_dir, _simple_factory(fake))
    resp = client.get("/api/blocks/a.png")

    assert resp.status_code == 502
    assert "vision down" in resp.json()["detail"]
    assert not (output_dir / "a.blocks.json").exists(), "エラー時はキャッシュを残さない"


def test_get_blocks_returns_409_on_stem_collision(tmp_path):
    """同 stem・別拡張子の画像がある場合、GET /api/blocks/{name} は 409 を返す（キャッシュ誤用防止）。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png")
    Image.new("RGB", (200, 150), color=(10, 20, 30)).save(image_dir / "a.webp")
    output_dir = tmp_path / "output"

    fake = FakeVisionClient(_FakeResponse(blocks=[[(10, 10), (60, 10), (60, 40), (10, 40)]]))
    client = _make_client(image_dir, output_dir, _simple_factory(fake))
    resp = client.get("/api/blocks/a.png")

    assert resp.status_code == 409
    assert not (output_dir / "a.blocks.json").exists(), "衝突時は検出・キャッシュ生成しない"


def test_get_blocks_redetects_when_cache_belongs_to_replaced_extension(tmp_path):
    """stem 衝突解消後（a.png 削除→別寸法 a.webp 配置）、GET /api/blocks/a.webp は
    旧 a.png キャッシュを返さず再検出し、a.webp の image_name と新寸法を返す（L-1）。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png", (100, 100))
    output_dir = tmp_path / "output"

    fake = FakeVisionClient(_FakeResponse(blocks=[[(10, 10), (60, 10), (60, 40), (10, 40)]]))
    client = _make_client(image_dir, output_dir, _simple_factory(fake))

    # a.png で a.blocks.json キャッシュを生成（image_name="a.png", 100x100）
    first = client.get("/api/blocks/a.png")
    assert first.status_code == 200
    assert first.json()["image_name"] == "a.png"
    assert len(fake.document_calls) == 1

    # 入力を別寸法の a.webp へ置換（a.png を削除）。a.blocks.json は残る。
    (image_dir / "a.png").unlink()
    Image.new("RGB", (200, 150), color=(10, 20, 30)).save(image_dir / "a.webp")

    resp = client.get("/api/blocks/a.webp")

    assert resp.status_code == 200
    data = resp.json()
    assert data["image_name"] == "a.webp", "旧 a.png キャッシュを返してはいけない"
    assert data["image_width"] == 200
    assert data["image_height"] == 150
    assert len(fake.document_calls) == 2, "不一致キャッシュは再検出する"
    # キャッシュが a.webp の内容で上書きされている
    from nova_parser.regional_ocr.blocks import load_blocks

    reloaded = load_blocks(output_dir, "a.webp")
    assert reloaded is not None
    assert reloaded.image_name == "a.webp"


def test_get_blocks_returns_vertical_blocks_merged_from_paragraphs(tmp_path):
    """レスポンスに blocks と vertical_blocks の両方が含まれ、縦に並ぶ段落は統合される。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png", (100, 100))
    output_dir = tmp_path / "output"

    fake = FakeVisionClient(
        _FakeResponse(
            blocks=[
                [(10, 10), (60, 10), (60, 40), (10, 40)],
                [(10, 45), (60, 45), (60, 75), (10, 75)],
            ]
        )
    )
    client = _make_client(image_dir, output_dir, _simple_factory(fake))
    resp = client.get("/api/blocks/a.png")

    assert resp.status_code == 200
    data = resp.json()
    # 段落矩形は Vision 由来のまま（意味を変えない）
    assert data["blocks"] == [
        {"x": 10, "y": 10, "width": 50, "height": 30},
        {"x": 10, "y": 45, "width": 50, "height": 30},
    ]
    # 縦ブロックは 2 段落を統合した 1 矩形 + 余白（PAD_*_RATIO=0.006 → 100px 画像で ±1px 程度）
    assert data["vertical_blocks"] == [{"x": 9, "y": 9, "width": 52, "height": 67}]


def test_get_blocks_returns_horizontal_blocks_merged_from_paragraphs(tmp_path):
    """レスポンスに horizontal_blocks が含まれ、Y プロファイルが揃う横並び段落は統合される。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png", (100, 100))
    output_dir = tmp_path / "output"

    fake = FakeVisionClient(
        _FakeResponse(
            blocks=[
                [(10, 10), (40, 10), (40, 80), (10, 80)],
                [(50, 10), (80, 10), (80, 80), (50, 80)],
            ]
        )
    )
    client = _make_client(image_dir, output_dir, _simple_factory(fake))
    resp = client.get("/api/blocks/a.png")

    assert resp.status_code == 200
    data = resp.json()
    # 横ブロックは横並び 2 段落を統合した 1 矩形 + 余白（PAD_*_RATIO=0.006 → 100px 画像で ±1px 程度）
    assert data["horizontal_blocks"] == [{"x": 9, "y": 9, "width": 72, "height": 72}]


def test_cache_file_stores_only_paragraph_blocks(tmp_path):
    """{stem}.blocks.json には vertical_blocks を保存しない（スペック 6.3）。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png", (100, 100))
    output_dir = tmp_path / "output"

    fake = FakeVisionClient(_FakeResponse(blocks=[[(10, 10), (60, 10), (60, 40), (10, 40)]]))
    client = _make_client(image_dir, output_dir, _simple_factory(fake))
    client.get("/api/blocks/a.png")

    raw = json.loads((output_dir / "a.blocks.json").read_text(encoding="utf-8"))
    assert "vertical_blocks" not in raw
    assert "horizontal_blocks" not in raw
    assert raw["schema_version"] == 1


def test_cache_hit_regenerates_vertical_blocks_without_vision_call(tmp_path):
    """キャッシュヒット時も縦ブロックを生成し、Vision API は呼ばない（スペック 11.4）。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png", (100, 100))
    output_dir = tmp_path / "output"

    fake = FakeVisionClient(_FakeResponse(blocks=[[(10, 10), (60, 10), (60, 40), (10, 40)]]))
    client = _make_client(image_dir, output_dir, _simple_factory(fake))

    first = client.get("/api/blocks/a.png")
    second = client.get("/api/blocks/a.png")

    assert len(fake.document_calls) == 1
    assert second.json()["vertical_blocks"] == first.json()["vertical_blocks"]
    assert second.json()["vertical_blocks"], "キャッシュヒット時に縦ブロックが空になってはいけない"
    assert second.json()["horizontal_blocks"] == first.json()["horizontal_blocks"]
    assert second.json()["horizontal_blocks"], "キャッシュヒット時に横ブロックが空になってはいけない"


def test_schema_version_1_cache_without_vertical_blocks_is_served(tmp_path):
    """既存 schema_version=1 キャッシュ（vertical_blocks キーなし）を読み込み、縦・横ブロックを再生成する。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png", (100, 100))
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    cache = {
        "image_name": "a.png",
        "image_width": 100,
        "image_height": 100,
        "blocks": [{"x": 10, "y": 10, "width": 50, "height": 30}],
        "detected_at": "2026-01-01T00:00:00Z",
        "schema_version": 1,
    }
    (output_dir / "a.blocks.json").write_text(json.dumps(cache), encoding="utf-8")

    fake = FakeVisionClient(_FakeResponse(blocks=[[(0, 0), (9, 0), (9, 9), (0, 9)]]))
    client = _make_client(image_dir, output_dir, _simple_factory(fake))
    resp = client.get("/api/blocks/a.png")

    assert resp.status_code == 200
    assert len(fake.document_calls) == 0, "既存キャッシュで Vision を呼んではいけない"
    assert resp.json()["blocks"] == [{"x": 10, "y": 10, "width": 50, "height": 30}]
    # 単一段落でも finalize 余白が付く（PAD_*_RATIO=0.006 → 100px 画像で ±1px 程度）
    assert resp.json()["vertical_blocks"] == [{"x": 9, "y": 9, "width": 52, "height": 32}]
    assert resp.json()["horizontal_blocks"] == [{"x": 9, "y": 9, "width": 52, "height": 32}]


def test_get_blocks_paragraph_mode_matches_fixture_order(tmp_path):
    """段落モード（blocks）は fixture の元矩形と座標・順序が一致する（スペック 11.3）。"""
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "regional_layout" / "ANGEL_GEAR2_p022.json").read_text(encoding="utf-8")
    )
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "p.png", (fixture["image_width"], fixture["image_height"]))
    output_dir = tmp_path / "output"

    vertices = [
        [
            (b["x"], b["y"]),
            (b["x"] + b["width"], b["y"]),
            (b["x"] + b["width"], b["y"] + b["height"]),
            (b["x"], b["y"] + b["height"]),
        ]
        for b in fixture["paragraph_blocks"]
    ]
    fake = FakeVisionClient(_FakeResponse(blocks=vertices))
    client = _make_client(image_dir, output_dir, _simple_factory(fake))
    resp = client.get("/api/blocks/p.png")

    assert resp.status_code == 200
    assert resp.json()["blocks"] == fixture["paragraph_blocks"], "段落矩形に変換・並び替えを適用してはいけない"


# ---------------------------------------------------------------------------
# GET /api/regions/undone — 全画像横断の未 OCR リージョン一覧
# ---------------------------------------------------------------------------


def test_get_regions_undone_returns_empty_items_when_no_sessions(tmp_path):
    """セッション未作成なら items は空、warnings も空で 200 を返す。"""
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png")
    output_dir = tmp_path / "output"

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/api/regions/undone")

    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["warnings"] == []


def test_get_regions_undone_excludes_done_and_orders_by_image_then_draw_order(tmp_path):
    """done を除外し、画像名順 → draw_order 昇順で列挙する。error の ocr_error も引き継ぐ。"""
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
                    rectangle=Rectangle(rect_id="a1", draw_order=1, x=50, y=0, width=40, height=40),
                    ocr_status="pending",
                ),
                RegionRecord(
                    rectangle=Rectangle(rect_id="a0", draw_order=0, x=0, y=0, width=40, height=40),
                    text="済み",
                    ocr_status="done",
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
                    rectangle=Rectangle(rect_id="b1", draw_order=1, x=50, y=0, width=40, height=40),
                    ocr_status="pending",
                ),
                RegionRecord(
                    rectangle=Rectangle(rect_id="b0", draw_order=0, x=0, y=0, width=40, height=40),
                    ocr_status="error",
                    ocr_error="quota exceeded",
                ),
            ],
        ),
        output_dir,
    )

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/api/regions/undone")

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [(i["image_name"], i["rect_id"], i["ocr_status"]) for i in items] == [
        ("a.png", "a1", "pending"),
        ("b.png", "b0", "error"),
        ("b.png", "b1", "pending"),
    ]
    assert items[1]["ocr_error"] == "quota exceeded"


def test_get_regions_undone_excludes_collided_stems_with_warning(tmp_path):
    """stem 衝突画像は items から除外し、warnings に 'stem collision: ' を含めて 200 を返す。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "foo.png")
    Image.new("RGB", (50, 50)).save(image_dir / "foo.webp")
    _write_png(image_dir / "solo.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    for name in ["foo.png", "solo.png"]:
        save_session(
            ImageSession(
                image_name=name,
                image_width=100,
                image_height=100,
                regions=[
                    RegionRecord(
                        rectangle=Rectangle(rect_id="r0", draw_order=0, x=0, y=0, width=40, height=40),
                        ocr_status="pending",
                    ),
                ],
            ),
            output_dir,
        )

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))
    resp = client.get("/api/regions/undone")

    assert resp.status_code == 200
    data = resp.json()
    assert [i["image_name"] for i in data["items"]] == ["solo.png"]
    assert any("stem collision: " in w for w in data["warnings"])


def test_get_regions_undone_does_not_call_vision_client_factory(tmp_path):
    """未 OCR 一覧の集計で vision_client_factory を一度も呼ばない（課金ゼロ）。"""
    from tests.conftest import make_fake_factory

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "a.png")
    output_dir = tmp_path / "output"

    factory = make_fake_factory(FakeVisionClient())
    client = _make_client(image_dir, output_dir, factory)
    resp = client.get("/api/regions/undone")

    assert resp.status_code == 200
    assert factory.calls["calls"] == 0


# ---------------------------------------------------------------------------
# POST /api/ocr/batch/stream — include_errors パラメータ
# ---------------------------------------------------------------------------


def _seed_pending_and_error_session(image_dir, output_dir):
    """error(draw_order=0) + pending(draw_order=1) を持つ 1 画像セッションを配置する。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    _write_png(image_dir / "img1.png")
    save_session(
        ImageSession(
            image_name="img1.png",
            image_width=100,
            image_height=100,
            regions=[
                RegionRecord(
                    rectangle=Rectangle(rect_id="r_err", draw_order=0, x=0, y=0, width=40, height=40),
                    ocr_status="error",
                    ocr_error="quota exceeded",
                ),
                RegionRecord(
                    rectangle=Rectangle(rect_id="r_pend", draw_order=1, x=50, y=0, width=40, height=40),
                    ocr_status="pending",
                ),
            ],
        ),
        output_dir,
    )


def test_post_ocr_batch_stream_with_include_errors_retries_error_regions(tmp_path):
    """include_errors=true で error リージョンも draw_order 順に再試行され done になる。"""
    from nova_parser.regional_ocr.sessions import load_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    _seed_pending_and_error_session(image_dir, output_dir)

    fake = FakeVisionClient([_FakeResponse(text="RETRY_OK"), _FakeResponse(text="PEND_OK")])
    client = _make_client(image_dir, output_dir, _simple_factory(fake))

    with client.stream("POST", "/api/ocr/batch/stream?include_errors=true") as resp:
        assert resp.status_code == 200
        lines = [line for line in resp.iter_lines() if line.startswith("data: ")]

    items = [json.loads(line[len("data: ") :]) for line in lines]
    assert [(i["rect_id"], i["status"]) for i in items] == [("r_err", "done"), ("r_pend", "done")]

    session = load_session(output_dir, "img1.png", image_width=100, image_height=100)
    assert all(r.ocr_status == "done" for r in session.regions)


def test_post_ocr_batch_stream_default_still_skips_error_regions(tmp_path):
    """パラメータ省略時は現行どおり pending のみ処理し、error は残る（回帰）。"""
    from nova_parser.regional_ocr.sessions import load_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    _seed_pending_and_error_session(image_dir, output_dir)

    fake = FakeVisionClient([_FakeResponse(text="PEND_OK")])
    client = _make_client(image_dir, output_dir, _simple_factory(fake))

    with client.stream("POST", "/api/ocr/batch/stream") as resp:
        assert resp.status_code == 200
        lines = [line for line in resp.iter_lines() if line.startswith("data: ")]

    items = [json.loads(line[len("data: ") :]) for line in lines]
    assert [(i["rect_id"], i["status"]) for i in items] == [("r_pend", "done")]

    session = load_session(output_dir, "img1.png", image_width=100, image_height=100)
    by_id = {r.rectangle.rect_id: r for r in session.regions}
    assert by_id["r_err"].ocr_status == "error"
    assert by_id["r_pend"].ocr_status == "done"


def test_post_ocr_batch_stream_include_errors_keeps_error_on_retry_failure(tmp_path):
    """include_errors=true の再試行が再度失敗したら error のまま ocr_error を更新する。"""
    from nova_parser.regional_ocr.sessions import load_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    _seed_pending_and_error_session(image_dir, output_dir)

    fake = FakeVisionClient([_FakeResponse(error_message="still broken"), _FakeResponse(text="PEND_OK")])
    client = _make_client(image_dir, output_dir, _simple_factory(fake))

    with client.stream("POST", "/api/ocr/batch/stream?include_errors=true") as resp:
        assert resp.status_code == 200
        lines = [line for line in resp.iter_lines() if line.startswith("data: ")]

    items = [json.loads(line[len("data: ") :]) for line in lines]
    assert [(i["rect_id"], i["status"]) for i in items] == [("r_err", "error"), ("r_pend", "done")]

    session = load_session(output_dir, "img1.png", image_width=100, image_height=100)
    by_id = {r.rectangle.rect_id: r for r in session.regions}
    assert by_id["r_err"].ocr_status == "error"
    assert "still broken" in (by_id["r_err"].ocr_error or "")


# ---------------------------------------------------------------------------
# GET /api/regions/undone — セッション未作成画像の画像オープン省略（レビュー修正 gemini L-1）
# ---------------------------------------------------------------------------


def test_get_regions_undone_skips_image_open_for_sessionless_images(tmp_path, monkeypatch):
    """セッション JSON が無い画像では PIL.Image.open を呼ばない（IO 削減）。応答は従来と同一。"""
    from PIL import Image as PILImage

    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "nosess.png")
    _write_png(image_dir / "withsess.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    save_session(
        ImageSession(
            image_name="withsess.png",
            image_width=100,
            image_height=100,
            regions=[
                RegionRecord(
                    rectangle=Rectangle(rect_id="r0", draw_order=0, x=0, y=0, width=40, height=40),
                    ocr_status="pending",
                ),
            ],
        ),
        output_dir,
    )

    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))

    opened: list[str] = []
    real_open = PILImage.open

    def counting_open(fp, *args, **kwargs):
        opened.append(str(fp))
        return real_open(fp, *args, **kwargs)

    monkeypatch.setattr(PILImage, "open", counting_open)

    resp = client.get("/api/regions/undone")

    assert resp.status_code == 200
    assert [i["image_name"] for i in resp.json()["items"]] == ["withsess.png"]
    assert all("nosess" not in p for p in opened), (
        f"セッション JSON が無い画像をオープンしてはいけない (opened: {opened})"
    )


# ---------------------------------------------------------------------------
# OCR 系エンドポイントの画像オープン回数（レビュー修正 gemini I-1）
# ---------------------------------------------------------------------------


def _count_pil_opens(monkeypatch):
    """PIL.Image.open をラップして呼び出しパスを記録するリストを返す。"""
    from PIL import Image as PILImage

    opened: list[str] = []
    real_open = PILImage.open

    def counting_open(fp, *args, **kwargs):
        opened.append(str(fp))
        return real_open(fp, *args, **kwargs)

    monkeypatch.setattr(PILImage, "open", counting_open)
    return opened


def test_post_ocr_batch_stream_opens_image_file_only_once(tmp_path, monkeypatch):
    """バッチ OCR は 1 画像につき画像ファイルを 1 回だけオープンする。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    save_session(
        ImageSession(
            image_name="img.png",
            image_width=100,
            image_height=100,
            regions=[
                RegionRecord(
                    rectangle=Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50),
                    ocr_status="pending",
                ),
            ],
        ),
        output_dir,
    )
    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient(_FakeResponse(text="T"))))
    opened = _count_pil_opens(monkeypatch)

    with client.stream("POST", "/api/ocr/batch/stream") as resp:
        assert resp.status_code == 200
        list(resp.iter_lines())

    img_opens = [p for p in opened if p.endswith("img.png")]
    assert len(img_opens) == 1, f"画像ファイルは 1 回だけオープンする (actual: {len(img_opens)})"


def test_post_ocr_single_opens_image_file_only_once(tmp_path, monkeypatch):
    """単発 OCR も画像ファイルを 1 回だけオープンする。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    save_session(
        ImageSession(
            image_name="img.png",
            image_width=100,
            image_height=100,
            regions=[
                RegionRecord(
                    rectangle=Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50),
                    ocr_status="pending",
                ),
            ],
        ),
        output_dir,
    )
    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient(_FakeResponse(text="T"))))
    opened = _count_pil_opens(monkeypatch)

    resp = client.post("/api/ocr/img.png/r1")

    assert resp.status_code == 200
    img_opens = [p for p in opened if p.endswith("img.png")]
    assert len(img_opens) == 1, f"画像ファイルは 1 回だけオープンする (actual: {len(img_opens)})"


# ---------------------------------------------------------------------------
# バッチ OCR — 並行編集の lost-update 防止（レビュー修正 gemini M-1）
# ---------------------------------------------------------------------------


def test_post_ocr_batch_stream_preserves_concurrent_put_edits(tmp_path, monkeypatch):
    """OCR（外部 API）実行中に保存された別リージョンの追加が、バッチの保存で失われない。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import load_session, save_session, upsert_region

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
    save_session(
        ImageSession(
            image_name="img.png",
            image_width=100,
            image_height=100,
            regions=[RegionRecord(rectangle=rect, ocr_status="pending")],
        ),
        output_dir,
    )

    def fake_ocr(client, image, rectangle, *, language_hints):
        # OCR 実行中のユーザー並行編集（別リージョン追加の PUT 保存）を注入する
        current = load_session(output_dir, "img.png", image_width=100, image_height=100)
        added = RegionRecord(
            rectangle=Rectangle(rect_id="r_new", draw_order=1, x=50, y=0, width=40, height=40),
            ocr_status="pending",
        )
        save_session(upsert_region(current, added), output_dir)
        return "OCR結果"

    monkeypatch.setattr("nova_parser.regional_ocr.routes.ocr_rectangle", fake_ocr)
    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))

    with client.stream("POST", "/api/ocr/batch/stream") as resp:
        assert resp.status_code == 200
        list(resp.iter_lines())

    session = load_session(output_dir, "img.png", image_width=100, image_height=100)
    by_id = {r.rectangle.rect_id: r for r in session.regions}
    assert by_id["r1"].ocr_status == "done", "OCR 結果は保存される"
    assert "r_new" in by_id, "OCR 中に追加された並行編集リージョンが失われてはいけない"
    assert by_id["r_new"].ocr_status == "pending"


def test_post_ocr_batch_stream_respects_deletion_during_ocr(tmp_path, monkeypatch):
    """OCR 実行中に対象リージョンが削除されたら、保存も SSE 配信もせず削除を尊重する。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import load_session, save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
    save_session(
        ImageSession(
            image_name="img.png",
            image_width=100,
            image_height=100,
            regions=[RegionRecord(rectangle=rect, ocr_status="pending")],
        ),
        output_dir,
    )

    def fake_ocr(client, image, rectangle, *, language_hints):
        # OCR 実行中に対象リージョンが削除された状況を注入する
        save_session(
            ImageSession(image_name="img.png", image_width=100, image_height=100, regions=[]),
            output_dir,
        )
        return "OCR結果"

    monkeypatch.setattr("nova_parser.regional_ocr.routes.ocr_rectangle", fake_ocr)
    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))

    with client.stream("POST", "/api/ocr/batch/stream") as resp:
        assert resp.status_code == 200
        lines = [line for line in resp.iter_lines() if line.startswith("data: ")]

    assert lines == [], "削除済みリージョンの SSE item は配信しない"
    session = load_session(output_dir, "img.png", image_width=100, image_height=100)
    assert session.regions == [], "削除済みリージョンを復活させてはいけない"


# ---------------------------------------------------------------------------
# 単発 OCR — 並行編集の lost-update 防止（gemini M-1 の水平展開）
# ---------------------------------------------------------------------------


def test_post_ocr_single_preserves_concurrent_put_edits(tmp_path, monkeypatch):
    """単発 OCR 実行中に保存された別リージョンの追加が、OCR 結果の保存で失われない。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import load_session, save_session, upsert_region

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
    save_session(
        ImageSession(
            image_name="img.png",
            image_width=100,
            image_height=100,
            regions=[RegionRecord(rectangle=rect, ocr_status="pending")],
        ),
        output_dir,
    )

    def fake_ocr(client, image, rectangle, *, language_hints):
        current = load_session(output_dir, "img.png", image_width=100, image_height=100)
        added = RegionRecord(
            rectangle=Rectangle(rect_id="r_new", draw_order=1, x=50, y=0, width=40, height=40),
            ocr_status="pending",
        )
        save_session(upsert_region(current, added), output_dir)
        return "OCR結果"

    monkeypatch.setattr("nova_parser.regional_ocr.routes.ocr_rectangle", fake_ocr)
    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))

    resp = client.post("/api/ocr/img.png/r1")

    assert resp.status_code == 200
    session = load_session(output_dir, "img.png", image_width=100, image_height=100)
    by_id = {r.rectangle.rect_id: r for r in session.regions}
    assert by_id["r1"].ocr_status == "done"
    assert "r_new" in by_id, "OCR 中に追加された並行編集リージョンが失われてはいけない"


def test_post_ocr_single_returns_404_when_region_deleted_mid_ocr(tmp_path, monkeypatch):
    """単発 OCR 実行中に対象リージョンが削除されたら 404 を返し、復活させない。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import load_session, save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    rect = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
    save_session(
        ImageSession(
            image_name="img.png",
            image_width=100,
            image_height=100,
            regions=[RegionRecord(rectangle=rect, ocr_status="pending")],
        ),
        output_dir,
    )

    def fake_ocr(client, image, rectangle, *, language_hints):
        save_session(
            ImageSession(image_name="img.png", image_width=100, image_height=100, regions=[]),
            output_dir,
        )
        return "OCR結果"

    monkeypatch.setattr("nova_parser.regional_ocr.routes.ocr_rectangle", fake_ocr)
    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))

    resp = client.post("/api/ocr/img.png/r1")

    assert resp.status_code == 404
    session = load_session(output_dir, "img.png", image_width=100, image_height=100)
    assert session.regions == [], "削除済みリージョンを復活させてはいけない"


# ---------------------------------------------------------------------------
# OCR 中の同一リージョン形状変更 — stale 結果を破棄（再レビュー F2）
# ---------------------------------------------------------------------------


def test_post_ocr_batch_stream_skips_save_when_geometry_changed_during_ocr(tmp_path, monkeypatch):
    """OCR 実行中に同一 rect の形状が変わったら、stale OCR を保存・SSE せず新形状を維持する。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import load_session, save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    original = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
    save_session(
        ImageSession(
            image_name="img.png",
            image_width=100,
            image_height=100,
            regions=[RegionRecord(rectangle=original, ocr_status="pending")],
        ),
        output_dir,
    )

    resized = Rectangle(rect_id="r1", draw_order=0, x=10, y=10, width=80, height=80)

    def fake_ocr(client, image, rectangle, *, language_hints):
        # OCR 実行中にユーザーが同一 rect をリサイズして保存した状況を注入
        save_session(
            ImageSession(
                image_name="img.png",
                image_width=100,
                image_height=100,
                regions=[RegionRecord(rectangle=resized, ocr_status="pending")],
            ),
            output_dir,
        )
        return "STALE_OCR_TEXT"

    monkeypatch.setattr("nova_parser.regional_ocr.routes.ocr_rectangle", fake_ocr)
    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))

    with client.stream("POST", "/api/ocr/batch/stream") as resp:
        assert resp.status_code == 200
        lines = [line for line in resp.iter_lines() if line.startswith("data: ")]

    assert lines == [], "形状変更後の stale OCR は SSE 配信しない"
    session = load_session(output_dir, "img.png", image_width=100, image_height=100)
    assert len(session.regions) == 1
    r = session.regions[0]
    assert r.rectangle.x == 10 and r.rectangle.y == 10
    assert r.rectangle.width == 80 and r.rectangle.height == 80
    assert r.ocr_status == "pending"
    assert r.text is None, "旧 crop の text を新形状に載せてはいけない"


def test_post_ocr_single_returns_409_when_geometry_changed_during_ocr(tmp_path, monkeypatch):
    """単発 OCR 実行中に同一 rect の形状が変わったら 409 を返し、ディスクを更新しない。"""
    from nova_parser.regional_ocr.models import ImageSession, Rectangle, RegionRecord
    from nova_parser.regional_ocr.sessions import load_session, save_session

    image_dir = tmp_path / "images"
    image_dir.mkdir()
    _write_png(image_dir / "img.png")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    original = Rectangle(rect_id="r1", draw_order=0, x=0, y=0, width=50, height=50)
    save_session(
        ImageSession(
            image_name="img.png",
            image_width=100,
            image_height=100,
            regions=[RegionRecord(rectangle=original, ocr_status="pending")],
        ),
        output_dir,
    )

    resized = Rectangle(rect_id="r1", draw_order=0, x=20, y=20, width=60, height=60)

    def fake_ocr(client, image, rectangle, *, language_hints):
        save_session(
            ImageSession(
                image_name="img.png",
                image_width=100,
                image_height=100,
                regions=[RegionRecord(rectangle=resized, ocr_status="pending")],
            ),
            output_dir,
        )
        return "STALE_OCR_TEXT"

    monkeypatch.setattr("nova_parser.regional_ocr.routes.ocr_rectangle", fake_ocr)
    client = _make_client(image_dir, output_dir, _simple_factory(FakeVisionClient()))

    resp = client.post("/api/ocr/img.png/r1")

    assert resp.status_code == 409
    session = load_session(output_dir, "img.png", image_width=100, image_height=100)
    assert len(session.regions) == 1
    r = session.regions[0]
    assert (r.rectangle.x, r.rectangle.y, r.rectangle.width, r.rectangle.height) == (20, 20, 60, 60)
    assert r.ocr_status == "pending"
    assert r.text is None
