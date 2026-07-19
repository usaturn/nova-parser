"""regional_ocr パッケージ固有の例外クラス定義。"""

from __future__ import annotations


class RegionalOcrError(Exception):
    """regional_ocr パッケージの基底例外クラス。"""


class ImageNotFoundError(RegionalOcrError):
    """指定された画像ファイルが見つからない場合の例外。"""


class RegionNotFoundError(RegionalOcrError):
    """指定されたリージョンが見つからない場合の例外。"""


class ImagePathTraversalError(RegionalOcrError):
    """パストラバーサル攻撃を検出した場合の例外。"""


class OcrBackendError(RegionalOcrError):
    """OCR バックエンドに関連する例外の基底クラス。"""


class StemCollisionError(RegionalOcrError):
    """同一ステムを持つ複数の画像ファイルが存在する場合の例外。

    Phase A の `list_images` は衝突を `ImageListResponse.warnings` に文字列として
    記録するのみで本例外を raise しない。Phase C の API 層（バッチ OCR）で
    衝突がある場合に 409 でリクエストをブロックする際に raise する想定。
    """


class RegionGeometryChangedError(RegionalOcrError):
    """OCR 実行中に対象リージョンの形状（座標・サイズ）が変更された場合の例外。

    単発 OCR 完了時に再ロードした矩形が開始時と異なる場合に raise し、
    stale な OCR 結果の保存を拒否する（HTTP 409）。
    """


class AdcNotConfiguredError(OcrBackendError):
    """Application Default Credentials が設定されていない場合の例外。"""
