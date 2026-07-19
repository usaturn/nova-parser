# 対話的領域 OCR ツール (`nova-parser-regional`)

`nova-parser-regional` は、画像をブラウザに表示し、マウスで矩形領域を描いて Cloud Vision API で OCR をかける Web ツールです。OCR 結果は画像ごとに `*.regions.json` と `*.regions.md` として保存されます。

CLI 系の主要モード（`plain` / `structured` / `docai` / `extract` 等）の使い方は [usage.md](usage.md) を参照してください。本書は Web UI 専用の手順をまとめています。

## 概要

- 入力: 画像ディレクトリ（`.png` / `.jpg` / `.jpeg` / `.gif` / `.bmp` / `.webp` / `.tiff` / `.tif`）
- OCR エンジン: Google Cloud Vision (`text_detection`)
- 認証: Application Default Credentials (ADC)
- 出力: 画像 stem ごとに `{stem}.regions.json`（セッション）と `{stem}.regions.md`（Markdown）
- UI: Vanilla HTML + Alpine.js (CDN) を FastAPI が同梱する `static/` から配信

## 前提条件

- Python 3.14
- [uv](https://docs.astral.sh/uv/)
- Google Cloud のプロジェクトと Cloud Vision API の有効化
- ADC が設定済みであること

ADC 設定例:

```bash
gcloud auth application-default login
```

## 起動

```bash
uv run nova-parser-regional Images/ --output-dir Output --host 127.0.0.1 --port 8000
```

| オプション | 既定値 | 説明 |
|---|---|---|
| `image_dir`（必須） | — | 画像ディレクトリ |
| `--output-dir` | `Output/<画像ディレクトリ名>` | セッション JSON / Markdown の保存先。未指定時は CWD 配下の `Output/<image_dir.name>/` を自動採用 |
| `--host` | `127.0.0.1` | バインドホスト |
| `--port` | `8000` | バインドポート |

ブラウザで `http://127.0.0.1:8000/` を開くと UI が表示されます。

## UI 操作

1. **画像選択**: 左サイドバーの一覧から画像をクリック
2. **矩形作成**: 画像上をマウスでドラッグ。閾値（5px）未満のドラッグは破棄
3. **ブロック選択モード**: ズームツールバーの「ブロック選択」トグルを ON にすると、初回のみ Cloud Vision `document_text_detection` で段落矩形を検出する（画像ごとに 1 回課金）。以降はマウスを乗せたブロックが点線でハイライトされ、クリックするとそのブロックの矩形が `pending` 領域として作成される。検出した段落は `{stem}.blocks.json` にキャッシュされ、再起動後も再課金されない（再検出したい場合はこのファイルを削除する）
4. **ブロック粒度**: ブロック選択 ON 時に表示されるセレクタで粒度を切り替える
   - **縦ブロック**（既定）: 段落からローカル生成した縦方向の結合矩形をハイライト対象にする
   - **段落**: Cloud Vision が返した段落矩形をそのままハイライト対象にする
5. **矩形編集**:
   - 矩形をクリックして選択 → 四隅・四辺のハンドルでリサイズ
   - 選択中の矩形右上の `×` ボタンで削除
6. **自動保存**: 編集後 500ms の debounce で `PUT /api/session/{name}` が走り、`Output/{stem}.regions.json` が更新される（ステータスバーに「保存中…」表示）
7. **個別 OCR**: 右ペインの各リージョンカードの `OCR` ボタンで単発実行
8. **バッチ OCR**: 右ペイン上部の `バッチ OCR 実行` ボタンで全画像の `pending` 領域を `draw_order` 順に処理。SSE で結果が逐次反映される
9. **未 OCR 一覧（全画像）**: 右ペイン上部の「未 OCR（全画像）」セクションに、全画像の `done` になっていない領域（`pending` / `error`）が一覧表示される。行クリックで該当画像・該当領域へジャンプできる。「未 OCR を一括実行」ボタンは実行前に未保存の編集をサーバへ反映した上で、`error` の領域も含めて全件を OCR する（`error` は再試行）
10. **中止**: バッチ実行・一括実行中の `中止` ボタンで `AbortController.abort()` を呼んでサーバ接続を切断

## 出力ファイル

- `{output_dir}/{stem}.regions.json` — セッション全体（`ImageSession`）。 `pending` / `done` / `error` の状態を含む
- `{output_dir}/{stem}.regions.md` — `done` の領域を `draw_order` 順に書き出した Markdown
- `{output_dir}/{stem}.blocks.json` — ブロック選択モードの段落検出キャッシュ（`BlockDetectionResult`）。段落矩形（`blocks`）のみを保存し、`vertical_blocks` はキャッシュしない

`done` 状態の領域は、その後の `PUT /api/session/{name}` でもサーバ側でテキストを保護してマージされます（再 OCR したい場合は領域を一旦削除してから再描画）。

## API リファレンス

| メソッド | パス | 役割 |
|---|---|---|
| GET | `/` | `static/index.html` を配信 |
| GET | `/static/{file}` | 静的ファイル（`app.js`、`styles.css`、`index.html`） |
| GET | `/api/images` | 画像一覧と stem 衝突警告 |
| GET | `/api/image/{name}` | 画像メタ（width / height / mime_type） |
| GET | `/api/image/{name}/raw` | 画像バイナリ |
| GET | `/api/blocks/{name}` | ブロック検出。`blocks`（段落）と `vertical_blocks`（リクエストごとにローカル再生成）を返す。段落は初回のみ Cloud Vision を呼び `{stem}.blocks.json` にキャッシュ |
| GET | `/api/regions/undone` | 全画像の未 OCR 領域（`pending` / `error`）を集計して返す。Vision は呼ばない（課金なし）。stem 衝突画像は `items` から除外し `warnings` で警告 |
| GET | `/api/session/{name}` | セッション取得（`pending` 領域含む） |
| PUT | `/api/session/{name}` | セッション upsert。`done` レコードは保護 |
| POST | `/api/ocr/{name}/{rect_id}` | 単発 OCR |
| POST | `/api/ocr/batch/stream` | 全画像 × `pending` 領域を SSE で OCR。`?include_errors=true` で `error` 領域も再試行対象に含める |

`POST /api/ocr/batch/stream` のレスポンスは `text/event-stream` で、`data: <BatchOcrItemResult JSON>\n\n` の繰り返し。各行は `image_name` / `rect_id` / `status` (`done` | `error`) / `text` / `error` を含みます。

## ローカル E2E テスト

ブラウザを起動せず、pytest だけで配信と API フローを検証できます。

```bash
uv run pytest -q tests/test_regional_e2e.py
```

検証内容（`tests/test_regional_e2e.py`）:

- `GET /` が `text/html` で Alpine.js を含む HTML を返す
- `GET /static/app.js` / `GET /static/styles.css` が正しい MIME で返る
- `GET /api/images` が静的マウント追加後も動作する（回帰確認）
- 「画像 2 枚配置 → 一覧 → 矩形 2 個ずつ PUT → バッチ OCR SSE 受信 → セッション再取得で全件 `done`」のフルパス

Cloud Vision はテスト内では `tests/conftest.py` の `FakeVisionClient` で差し替えられるため、実際の課金は発生しません。

## トラブルシュート

- **`ADC が未設定です` (HTTP 502)**: `gcloud auth application-default login` で ADC をセットアップ。サービスアカウントを使う場合は `GOOGLE_APPLICATION_CREDENTIALS` を設定。
- **`stem collision: ...` 警告**: 拡張子違いの同 stem 画像（例 `foo.png` と `foo.webp`）が同居している。どちらかをリネームまたは別ディレクトリに移動。
- **SSE が途中で切れる**: ブラウザのタブを閉じる / 別画像を選択する / 「中止」を押すと `AbortController.abort()` でサーバ接続を解除する仕様。再実行で続行できる（既に `done` のレコードは保護される）。
- **ブラウザに JS が反映されない**: ブラウザのキャッシュをクリア。`Alpine.js` は CDN 読み込みのためオフライン環境では動作しない（オフライン同梱は将来課題）。
- **wheel に `static/` が含まれない**: `uv build` 後に確認。

  ```bash
  uv build
  unzip -l dist/*.whl | grep static/
  ```

  3 ファイル（`index.html`、`app.js`、`styles.css`）が見えなければ `pyproject.toml` の hatch 設定（`[tool.hatch.build.targets.wheel.force-include]`）の追加を検討。
