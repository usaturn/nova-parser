"""FastAPI ルータ定義（全 /api/* エンドポイント）。"""

from __future__ import annotations

import datetime
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image

from nova_parser.regional_ocr.blocks import load_blocks, save_blocks
from nova_parser.regional_ocr.errors import (
    OcrBackendError,
    RegionGeometryChangedError,
    RegionNotFoundError,
    StemCollisionError,
)
from nova_parser.regional_ocr.images import (
    IMAGE_MIME_TYPES,
    list_images,
    open_pil,
    resolve_image,
)
from nova_parser.regional_ocr.layout import compute_vertical_blocks
from nova_parser.regional_ocr.layout_horizontal import compute_horizontal_blocks
from nova_parser.regional_ocr.markdown import write_markdown
from nova_parser.regional_ocr.models import (
    BatchOcrItemResult,
    BlockDetectionResponse,
    BlockDetectionResult,
    ImageListResponse,
    ImageMetaResponse,
    ImageSession,
    Rectangle,
    RegionRecord,
    UndoneRegionItem,
    UndoneRegionsResponse,
)
from nova_parser.regional_ocr.ocr_client import detect_blocks, ocr_rectangle
from nova_parser.regional_ocr.sessions import load_session, save_session, session_path, upsert_region
from nova_parser.regional_ocr.state import AppState


def _same_geometry(a: Rectangle, b: Rectangle) -> bool:
    """OCR crop に影響する幾何が一致するか（draw_order は無視）。"""
    return (a.x, a.y, a.width, a.height) == (b.x, b.y, b.width, b.height)


def get_app_state(request: Request) -> AppState:
    return request.app.state.app_state


AppStateDep = Annotated[AppState, Depends(get_app_state)]


def _to_blocks_response(result: BlockDetectionResult) -> BlockDetectionResponse:
    """キャッシュモデルへ、ローカル生成した縦・横ブロックを付与する（毎回再生成、スペック 6.3）。"""
    vertical = compute_vertical_blocks(result.image_width, result.image_height, result.blocks)
    horizontal = compute_horizontal_blocks(result.image_width, result.image_height, result.blocks)
    return BlockDetectionResponse(**result.model_dump(), vertical_blocks=vertical, horizontal_blocks=horizontal)


def build_router() -> APIRouter:
    router = APIRouter()
    static_dir = Path(__file__).parent / "static"

    @router.get("/", include_in_schema=False)
    def serve_index() -> FileResponse:
        return FileResponse(static_dir / "index.html", media_type="text/html; charset=utf-8")

    @router.get("/api/images", response_model=ImageListResponse)
    def api_list_images(state: AppStateDep) -> ImageListResponse:
        return list_images(state.image_dir)

    @router.get("/api/image/{name}", response_model=ImageMetaResponse)
    def api_image_meta(name: str, state: AppStateDep) -> ImageMetaResponse:
        path = resolve_image(state.image_dir, name)
        with Image.open(path) as img:
            width, height = img.size
        mime = IMAGE_MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")
        return ImageMetaResponse(image_width=width, image_height=height, mime_type=mime)

    @router.get("/api/image/{name}/raw")
    def api_image_raw(name: str, state: AppStateDep) -> Response:
        path = resolve_image(state.image_dir, name)
        mime = IMAGE_MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")
        return Response(content=path.read_bytes(), media_type=mime)

    @router.get("/api/blocks/{name}", response_model=BlockDetectionResponse)
    def api_get_blocks(name: str, state: AppStateDep) -> BlockDetectionResponse:
        path = resolve_image(state.image_dir, name)
        # {stem}.blocks.json キャッシュは stem 単位のため、foo.png と foo.webp のような
        # stem 衝突があると別画像間でキャッシュを共有し誤った段組を返す。バッチ OCR と
        # 同様に、要求画像の stem が衝突する場合は 409 で拒否する。
        siblings = sorted(
            p.name
            for p in state.image_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_MIME_TYPES and p.stem == path.stem
        )
        if len(siblings) >= 2:
            raise StemCollisionError(f"stem collision: {', '.join(siblings)}")
        cached = load_blocks(state.output_dir, name)
        # {stem}.blocks.json は stem 単位のため、a.png のキャッシュ生成後に a.png を削除して
        # 同 stem・別拡張子の a.webp へ置き換えると、要求名と異なる画像のキャッシュがヒットしうる。
        # image_name が一致する場合のみ再利用し、不一致は cache miss として再検出・上書きする。
        if cached is not None and cached.image_name == name:
            return _to_blocks_response(cached)
        image = open_pil(path)
        client = state.vision_client_factory()
        blocks = detect_blocks(client, image, language_hints=state.language_hints)
        result = BlockDetectionResult(
            image_name=name,
            image_width=image.width,
            image_height=image.height,
            blocks=blocks,
            detected_at=datetime.datetime.now(datetime.UTC),
        )
        save_blocks(result, state.output_dir)
        return _to_blocks_response(result)

    @router.get("/api/regions/undone", response_model=UndoneRegionsResponse)
    def api_regions_undone(state: AppStateDep) -> UndoneRegionsResponse:
        listing = list_images(state.image_dir)
        # stem 衝突画像はセッションファイル（{stem}.regions.json）を別画像間で共有してしまい
        # 同一リージョンを重複列挙するため、items から除外して listing.warnings で知らせる。
        # 読み取り専用のため batch と違い 409 にはしない。
        stem_counts = Counter(Path(name).stem for name in listing.images)
        items: list[UndoneRegionItem] = []
        for image_name in listing.images:
            if stem_counts[Path(image_name).stem] > 1:
                continue
            # セッション JSON が無い画像は未 OCR リージョンも存在し得ないため、
            # 画像オープン（サイズ取得）まで進まずスキップして IO を抑える
            if not session_path(state.output_dir, image_name).exists():
                continue
            path = resolve_image(state.image_dir, image_name)
            with Image.open(path) as img:
                width, height = img.size
            session = load_session(state.output_dir, image_name, image_width=width, image_height=height)
            undone = sorted(
                (r for r in session.regions if r.ocr_status != "done"),
                key=lambda r: r.rectangle.draw_order,
            )
            items.extend(
                UndoneRegionItem(
                    image_name=image_name,
                    rect_id=r.rectangle.rect_id,
                    draw_order=r.rectangle.draw_order,
                    ocr_status=r.ocr_status,
                    ocr_error=r.ocr_error,
                )
                for r in undone
            )
        return UndoneRegionsResponse(items=items, warnings=listing.warnings)

    @router.get("/api/session/{name}", response_model=ImageSession)
    def api_get_session(name: str, state: AppStateDep) -> ImageSession:
        path = resolve_image(state.image_dir, name)
        with Image.open(path) as img:
            width, height = img.size
        return load_session(state.output_dir, name, image_width=width, image_height=height)

    @router.put("/api/session/{name}", response_model=ImageSession)
    def api_put_session(name: str, session: ImageSession, state: AppStateDep) -> ImageSession:
        resolve_image(state.image_dir, name)
        if session.image_name != name:
            raise ValueError(f"URL の name ({name}) と body の image_name ({session.image_name}) が一致しません")
        # バッチ／単発 OCR の保存と競合しないよう load→merge→save をロックで直列化
        with state.session_lock:
            existing = load_session(
                state.output_dir,
                name,
                image_width=session.image_width,
                image_height=session.image_height,
            )
            existing_by_id = {r.rectangle.rect_id: r for r in existing.regions}
            merged_regions: list[RegionRecord] = []
            for incoming in session.regions:
                prev = existing_by_id.get(incoming.rectangle.rect_id)
                if prev is not None and prev.ocr_status == "done":
                    merged_regions.append(
                        RegionRecord(
                            rectangle=incoming.rectangle,
                            text=prev.text,
                            ocr_status="done",
                            ocr_error=None,
                            ocr_completed_at=prev.ocr_completed_at,
                        )
                    )
                else:
                    merged_regions.append(incoming)
            merged = ImageSession(
                image_name=session.image_name,
                image_width=session.image_width,
                image_height=session.image_height,
                regions=merged_regions,
            )
            save_session(merged, state.output_dir)
        return merged

    @router.post("/api/ocr/batch/stream")
    def api_ocr_batch_stream(state: AppStateDep, include_errors: bool = False) -> StreamingResponse:
        listing = list_images(state.image_dir)
        if listing.warnings:
            raise StemCollisionError("; ".join(listing.warnings))

        client = state.vision_client_factory()

        def _generate() -> Iterator[str]:
            for image_name in listing.images:
                path = resolve_image(state.image_dir, image_name)
                image = open_pil(path)
                width, height = image.size
                session = load_session(state.output_dir, image_name, image_width=width, image_height=height)
                targets = sorted(
                    [
                        r
                        for r in session.regions
                        if r.ocr_status == "pending" or (include_errors and r.ocr_status == "error")
                    ],
                    key=lambda r: r.rectangle.draw_order,
                )
                for target in targets:
                    try:
                        text = ocr_rectangle(client, image, target.rectangle, language_hints=state.language_hints)
                        updated = RegionRecord(
                            rectangle=target.rectangle,
                            text=text,
                            ocr_status="done",
                            ocr_error=None,
                            ocr_completed_at=datetime.datetime.now(datetime.UTC),
                        )
                        item = BatchOcrItemResult(
                            image_name=image_name,
                            rect_id=target.rectangle.rect_id,
                            status="done",
                            text=text,
                        )
                    except OcrBackendError as exc:
                        updated = RegionRecord(
                            rectangle=target.rectangle,
                            text=None,
                            ocr_status="error",
                            ocr_error=str(exc),
                            ocr_completed_at=datetime.datetime.now(datetime.UTC),
                        )
                        item = BatchOcrItemResult(
                            image_name=image_name,
                            rect_id=target.rectangle.rect_id,
                            status="error",
                            error=str(exc),
                        )
                    # OCR（外部 API）中の並行編集を失わないよう、保存直前に最新セッションを
                    # ロック内で再ロードする。
                    # - rect_id が消えていればユーザーの削除を尊重（保存・SSE スキップ）
                    # - 幾何（x/y/width/height）が開始時と異なれば stale OCR を破棄
                    #   （旧 crop の text を新形状に載せない。クライアントは終了時の一覧再取得で整合）
                    rect_id = target.rectangle.rect_id
                    with state.session_lock:
                        session = load_session(state.output_dir, image_name, image_width=width, image_height=height)
                        existing = next((r for r in session.regions if r.rectangle.rect_id == rect_id), None)
                        if existing is None:
                            continue
                        if not _same_geometry(existing.rectangle, target.rectangle):
                            continue
                        session = upsert_region(session, updated)
                        save_session(session, state.output_dir)
                        write_markdown(session, state.output_dir, Path(image_name).stem)
                    yield f"data: {item.model_dump_json()}\n\n"

        return StreamingResponse(_generate(), media_type="text/event-stream")

    @router.post("/api/ocr/{name}/{rect_id}", response_model=RegionRecord)
    def api_ocr_single(name: str, rect_id: str, state: AppStateDep) -> RegionRecord:
        path = resolve_image(state.image_dir, name)
        image = open_pil(path)
        width, height = image.size
        session = load_session(state.output_dir, name, image_width=width, image_height=height)
        target = next((r for r in session.regions if r.rectangle.rect_id == rect_id), None)
        if target is None:
            raise RegionNotFoundError(f"rect_id が見つかりません: {rect_id}")

        client = state.vision_client_factory()
        try:
            text = ocr_rectangle(client, image, target.rectangle, language_hints=state.language_hints)
            updated = RegionRecord(
                rectangle=target.rectangle,
                text=text,
                ocr_status="done",
                ocr_error=None,
                ocr_completed_at=datetime.datetime.now(datetime.UTC),
            )
        except OcrBackendError as exc:
            updated = RegionRecord(
                rectangle=target.rectangle,
                text=None,
                ocr_status="error",
                ocr_error=str(exc),
                ocr_completed_at=datetime.datetime.now(datetime.UTC),
            )

        # OCR（外部 API）中の並行編集を失わないよう、保存直前に最新セッションを
        # ロック内で再ロードする。
        # - rect_id が消えていれば 404
        # - 幾何が開始時と異なれば 409（stale OCR を保存しない）
        with state.session_lock:
            session = load_session(state.output_dir, name, image_width=width, image_height=height)
            existing = next((r for r in session.regions if r.rectangle.rect_id == rect_id), None)
            if existing is None:
                raise RegionNotFoundError(f"rect_id が見つかりません: {rect_id}")
            if not _same_geometry(existing.rectangle, target.rectangle):
                raise RegionGeometryChangedError(f"OCR 実行中にリージョンの形状が変更されました: {rect_id}")
            session = upsert_region(session, updated)
            save_session(session, state.output_dir)
            write_markdown(session, state.output_dir, Path(name).stem)
        return updated

    return router
