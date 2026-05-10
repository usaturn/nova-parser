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


class ImageListResponse(BaseModel):
    """画像一覧の取得結果を表すモデル。"""

    images: list[str]
    warnings: list[str] = Field(default_factory=list)
