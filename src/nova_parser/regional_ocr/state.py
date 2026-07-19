"""アプリ全体で共有する設定と共有ランタイム資源のモデル。"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.cloud import vision


@dataclass(frozen=True)
class AppState:
    """アプリ全体で共有する不変設定と共有ランタイム資源。FastAPI ルータには Depends で注入する。

    session_lock はセッション JSON の load→変更→save を直列化するプロセス内ロック。
    FastAPI の sync エンドポイントと StreamingResponse の sync ジェネレータは
    同一プロセスの threadpool で動くため threading.Lock で足りる。
    """

    image_dir: Path
    output_dir: Path
    vision_client_factory: Callable[[], "vision.ImageAnnotatorClient"]
    language_hints: tuple[str, ...] = field(default=("ja",))
    session_lock: threading.Lock = field(default_factory=threading.Lock, compare=False)
