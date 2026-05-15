"""FastAPI アプリケーション・ファクトリ。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from nova_parser.regional_ocr.errors import (
    AdcNotConfiguredError,
    ImageNotFoundError,
    ImagePathTraversalError,
    OcrBackendError,
    RegionNotFoundError,
    StemCollisionError,
)
from nova_parser.regional_ocr.routes import build_router
from nova_parser.regional_ocr.state import AppState


def create_app(state: AppState) -> FastAPI:
    """AppState を受け取り FastAPI app を生成する。"""
    app = FastAPI(title="nova-parser-regional")
    app.state.app_state = state

    @app.exception_handler(ImagePathTraversalError)
    async def _traversal(_request: Request, exc: ImagePathTraversalError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ImageNotFoundError)
    async def _image_not_found(_request: Request, exc: ImageNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(RegionNotFoundError)
    async def _region_not_found(_request: Request, exc: RegionNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(StemCollisionError)
    async def _stem_collision(_request: Request, exc: StemCollisionError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(AdcNotConfiguredError)
    async def _adc(_request: Request, exc: AdcNotConfiguredError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(OcrBackendError)
    async def _ocr_backend(_request: Request, exc: OcrBackendError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(build_router())
    return app
