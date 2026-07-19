"""regional_ocr パッケージの Pydantic モデル定義。"""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Rectangle(BaseModel):
    """画像内の矩形領域を表すモデル。"""

    rect_id: str = Field(min_length=1)
    draw_order: int = Field(ge=0)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @property
    def left(self) -> int:
        """矩形の左端 X 座標。"""
        return self.x

    @property
    def top(self) -> int:
        """矩形の上端 Y 座標。"""
        return self.y

    @property
    def right(self) -> int:
        """矩形の右端 X 座標。"""
        return self.x + self.width

    @property
    def bottom(self) -> int:
        """矩形の下端 Y 座標。"""
        return self.y + self.height


class RegionRecord(BaseModel):
    """画像内の 1 つの矩形領域とその OCR 結果を表すモデル。"""

    rectangle: Rectangle
    text: str | None = None
    ocr_status: Literal["pending", "done", "error"] = "pending"
    ocr_error: str | None = None
    ocr_completed_at: datetime.datetime | None = None


class ImageSession(BaseModel):
    """1 枚の画像に対するすべてのリージョン情報をまとめたセッションモデル。"""

    image_name: str = Field(min_length=1)
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    regions: list[RegionRecord] = Field(default_factory=list)
    schema_version: int = 1

    @model_validator(mode="after")
    def _validate_uniqueness(self) -> "ImageSession":
        """rect_id と draw_order の一意性を検証する。"""
        rect_ids = [r.rectangle.rect_id for r in self.regions]
        if len(rect_ids) != len(set(rect_ids)):
            raise ValueError("rect_id が重複しています")
        draw_orders = [r.rectangle.draw_order for r in self.regions]
        if len(draw_orders) != len(set(draw_orders)):
            raise ValueError("draw_order が重複しています")
        return self


class BlockRect(BaseModel):
    """検出されたテキストブロックの矩形（画像自然座標）。"""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @property
    def left(self) -> int:
        """矩形の左端 X 座標。"""
        return self.x

    @property
    def top(self) -> int:
        """矩形の上端 Y 座標。"""
        return self.y

    @property
    def right(self) -> int:
        """矩形の右端 X 座標。"""
        return self.x + self.width

    @property
    def bottom(self) -> int:
        """矩形の下端 Y 座標。"""
        return self.y + self.height


class BlockDetectionResult(BaseModel):
    """1 枚の画像に対するブロック検出結果のキャッシュ形式（`{stem}.blocks.json`）。

    `blocks` は Cloud Vision が返した段落矩形のみ。縦ブロックは含まない。
    API レスポンスは `BlockDetectionResponse`（本モデル + `vertical_blocks`）を使う。
    """

    image_name: str = Field(min_length=1)
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    blocks: list[BlockRect]
    detected_at: datetime.datetime
    schema_version: int = 1


class BlockDetectionResponse(BlockDetectionResult):
    """GET /api/blocks/{name} のレスポンス。キャッシュ形式へローカル生成の縦ブロックを加える。

    vertical_blocks はキャッシュへ保存せず、API 要求ごとに layout.compute_vertical_blocks で再生成する。
    """

    vertical_blocks: list[BlockRect] = Field(default_factory=list)


class ImageListResponse(BaseModel):
    """画像一覧の取得結果を表すモデル。"""

    images: list[str]
    warnings: list[str] = Field(default_factory=list)


class ImageMetaResponse(BaseModel):
    """画像メタ情報の取得結果を表すモデル。"""

    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    mime_type: str = Field(min_length=1)


class BatchOcrItemResult(BaseModel):
    """バッチ OCR ストリームの 1 件分の結果を表すモデル。"""

    image_name: str = Field(min_length=1)
    rect_id: str = Field(min_length=1)
    status: Literal["done", "error"]
    text: str | None = None
    error: str | None = None


class UndoneRegionItem(BaseModel):
    """未 OCR リージョン一覧（GET /api/regions/undone）の 1 件分。"""

    image_name: str = Field(min_length=1)
    rect_id: str = Field(min_length=1)
    draw_order: int = Field(ge=0)
    ocr_status: Literal["pending", "error"]
    ocr_error: str | None = None


class UndoneRegionsResponse(BaseModel):
    """GET /api/regions/undone のレスポンス。"""

    items: list[UndoneRegionItem]
    warnings: list[str] = Field(default_factory=list)
