"""regional_ocr パッケージの公開 API。

公開関数:
- `create_app(state: AppState) -> FastAPI`: FastAPI アプリケーション・ファクトリ。

注意:
- CLI エントリポイント `main()` を直接呼び出すには、`from nova_parser.regional_ocr.main import main`
  でサブモジュールから import すること。
- `nova_parser.regional_ocr.main` 自体はサブモジュールとして属性アクセス可能であり、
  `monkeypatch.setattr("nova_parser.regional_ocr.main.uvicorn.run", ...)` での差し替えに対応する。
"""

import nova_parser.regional_ocr.main  # noqa: F401 — サブモジュール属性を保証（monkeypatch 用）
from nova_parser.regional_ocr.app import create_app as create_app

__all__ = ["create_app"]
