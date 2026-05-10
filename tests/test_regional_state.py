"""regional_ocr.state のユニットテスト（AC-B-01, AC-B-02, AC-B-03）。"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# AC-B-01: AppState の正常構築とデフォルト値確認
# ---------------------------------------------------------------------------


def test_appstate_builds_without_error_and_default_language_hints():
    """AC-B-01: AppState を image_dir=Path('/img'), output_dir=Path('/out'),
    vision_client_factory=lambda: None で構築したとき、
    ValidationError や TypeError が発生せず、language_hints フィールドの
    デフォルト値が ('ja',) となる。
    """
    from nova_parser.regional_ocr.state import AppState  # type: ignore[import]

    state = AppState(
        image_dir=Path("/img"),
        output_dir=Path("/out"),
        vision_client_factory=lambda: None,
    )
    assert state.language_hints == ("ja",)


# ---------------------------------------------------------------------------
# AC-B-02: AppState は frozen=True で再代入不可
# ---------------------------------------------------------------------------


def test_appstate_raises_frozen_instance_error_on_field_reassignment():
    """AC-B-02: AppState インスタンスの image_dir フィールドに再代入しようとしたとき、
    dataclasses.FrozenInstanceError が raise される。
    """
    from nova_parser.regional_ocr.state import AppState  # type: ignore[import]

    state = AppState(
        image_dir=Path("/img"),
        output_dir=Path("/out"),
        vision_client_factory=lambda: None,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.image_dir = Path("/other")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AC-B-03: AppState.vision_client_factory は callable を保持できる
# ---------------------------------------------------------------------------


def test_appstate_vision_client_factory_accepts_callable_and_is_callable():
    """AC-B-03: AppState.vision_client_factory フィールドに任意の callable（lambda を含む）を
    設定でき、callable(state.vision_client_factory) が True を返す。
    """
    from nova_parser.regional_ocr.state import AppState  # type: ignore[import]

    factory = lambda: None  # noqa: E731

    state = AppState(
        image_dir=Path("/img"),
        output_dir=Path("/out"),
        vision_client_factory=factory,
    )
    assert callable(state.vision_client_factory)
