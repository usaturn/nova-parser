"""FastAPI ルータ定義（全 /api/* エンドポイント）。"""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image

from nova_parser.regional_ocr.blocks import load_blocks, save_blocks
from nova_parser.regional_ocr.errors import (
    OcrBackendError,
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
from nova_parser.regional_ocr.markdown import write_markdown
from nova_parser.regional_ocr.models import (
    BatchOcrItemResult,
    BlockDetectionResponse,
    BlockDetectionResult,
    ImageListResponse,
    ImageMetaResponse,
    ImageSession,
    RegionRecord,
)
from nova_parser.regional_ocr.ocr_client import detect_blocks, ocr_rectangle
from nova_parser.regional_ocr.sessions import load_session, save_session, upsert_region
from nova_parser.regional_ocr.state import AppState


def get_app_state(request: Request) -> AppState:
    return request.app.state.app_state


AppStateDep = Annotated[AppState, Depends(get_app_state)]


def _to_blocks_response(result: BlockDetectionResult) -> BlockDetectionResponse:
    """キャッシュモデルへ、ローカル生成した縦ブロックを付与する（毎回再生成、スペック 6.3）。"""
    vertical = compute_vertical_blocks(result.image_width, result.image_height, result.blocks)
    return BlockDetectionResponse(**result.model_dump(), vertical_blocks=vertical)


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
    def api_ocr_batch_stream(state: AppStateDep) -> StreamingResponse:
        listing = list_images(state.image_dir)
        if listing.warnings:
            raise StemCollisionError("; ".join(listing.warnings))

        client = state.vision_client_factory()

        def _generate() -> Iterator[str]:
            for image_name in listing.images:
                path = resolve_image(state.image_dir, image_name)
                with Image.open(path) as raw:
                    width, height = raw.size
                image = open_pil(path)
                session = load_session(state.output_dir, image_name, image_width=width, image_height=height)
                pending = sorted(
                    [r for r in session.regions if r.ocr_status == "pending"],
                    key=lambda r: r.rectangle.draw_order,
                )
                for target in pending:
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
                    session = upsert_region(session, updated)
                    save_session(session, state.output_dir)
                    write_markdown(session, state.output_dir, Path(image_name).stem)
                    yield f"data: {item.model_dump_json()}\n\n"

        return StreamingResponse(_generate(), media_type="text/event-stream")

    @router.post("/api/ocr/{name}/{rect_id}", response_model=RegionRecord)
    def api_ocr_single(name: str, rect_id: str, state: AppStateDep) -> RegionRecord:
        path = resolve_image(state.image_dir, name)
        with Image.open(path) as raw:
            width, height = raw.size
        session = load_session(state.output_dir, name, image_width=width, image_height=height)
        target = next((r for r in session.regions if r.rectangle.rect_id == rect_id), None)
        if target is None:
            raise RegionNotFoundError(f"rect_id が見つかりません: {rect_id}")

        client = state.vision_client_factory()
        image = open_pil(path)
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

        session = upsert_region(session, updated)
        save_session(session, state.output_dir)
        write_markdown(session, state.output_dir, Path(name).stem)
        return updated

    return router
