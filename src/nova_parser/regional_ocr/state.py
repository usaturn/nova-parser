"""アプリ全体で共有する不変設定モデル。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.cloud import vision


@dataclass(frozen=True)
class AppState:
    """アプリ全体で共有する不変設定。FastAPI ルータには Depends で注入する。"""

    image_dir: Path
    output_dir: Path
    vision_client_factory: Callable[[], "vision.ImageAnnotatorClient"]
    language_hints: tuple[str, ...] = field(default=("ja",))
