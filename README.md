# nova-parser

Gemini と Document AI を使って、書籍やゲーム資料の画像/PDF から OCR・構造化抽出を行う CLI ツールです。

入力は `Images/` 配下のファイル、または CLI で指定した画像/PDF/ディレクトリです。結果はデフォルトで `Output/` 配下に Markdown、JSON、TSV、クロップ画像として保存され、`--output-dir` で変更できます。

## セットアップ

### 前提条件

- Python 3.14
- [uv](https://docs.astral.sh/uv/)

### インストール

```bash
uv sync
```

ローカル実行は `uv run nova-parser ...`、インストール済み環境では `nova-parser ...` を使えます。

### 環境変数

`.env` を作成し、必要な値を設定します。

| 変数名 | 用途 | 必要なモード |
|--------|------|--------------|
| `GEMINI_API_KEY` | Google AI Studio の API キー（優先利用） | `plain` / `structured` / `structured_tsv` / `gamedata` / `schema` / `docai` / `extract` / `crop` |
| `VERTEX_AI_API_KEY` | Vertex AI Express モードの API キー（AI Studio が 429 を返した時のフォールバック先） | 同上 |
| `DOCUMENT_AI_PROCESSOR` | Document AI OCR プロセッサのリソース名 | `docai` / `docai_plain` / `extract` / `crop` の Document AI フォールバック |
| `GOOGLE_APPLICATION_CREDENTIALS` | Document AI 用サービスアカウントキーのパス | 任意 |

Gemini バックエンドは `GEMINI_API_KEY` が設定されていれば AI Studio を優先し、レート制限（HTTP 429）を観測した時点で **同一プロセス内 sticky** に Vertex AI へ切り替えます。AI Studio キーが未設定なら起動時から `VERTEX_AI_API_KEY` のみで動作します。両方未設定の場合は起動時にエラーで停止します。

Document AI の認証は `GOOGLE_APPLICATION_CREDENTIALS`、`.secrets/docai-sa.json`、ADC の順で解決されます。

## クイックスタート

```bash
# Images/ 直下の対応ファイルを Gemini OCR で Markdown 出力
uv run nova-parser

# Pydantic AI で構造化抽出して JSON 出力
uv run nova-parser --mode structured Images/NAN_067.tif

# 構造化抽出を TSV 出力
uv run nova-parser --mode structured_tsv Images/NAN_067.tif

# 画像内容から動的に型を発見して JSON 出力
uv run nova-parser --mode gamedata Images/TNX_OFC_020.tif

# 型名とフィールド名だけを TSV 出力
uv run nova-parser --mode schema Images/TNX_OFC_020.tif

# Document AI OCR を Markdown 出力
uv run nova-parser --mode docai_plain Images/NAN_067.tif

# Document AI OCR + Gemini 構造化抽出を TSV 出力
uv run nova-parser --mode docai --parallel-files 4 Images/dx3/DX3_EA

# 出力先を指定
uv run nova-parser --output-dir Results --mode docai Images/TNX_OFC_020.tif

# docai TSV からスキーマ提案を生成
uv run nova-parser --mode schema_propose
uv run nova-parser --mode schema_propose Output/TNX_OFC_020.docai.tsv

# 確定スキーマに従って型別 TSV を抽出
uv run nova-parser --mode extract --schema Output/schema.json Images/TNX_OFC_020.tif
uv run nova-parser --mode extract --parallel-files 4 --schema Output/schema.json Images/dx3/DX3_EA

# Gemini Vision でカード領域を切り出し
uv run nova-parser --mode crop --min-card-area 0.03 --max-card-area 0.60 --padding 20 Images/sample.png
```

- 対応入力形式は `.png`、`.jpg`、`.jpeg`、`.gif`、`.bmp`、`.webp`、`.tiff`、`.tif`、`.pdf`
- ディレクトリを指定した場合は直下の対応ファイルだけを処理
- `schema_propose` は画像ではなく `*.docai.tsv` を入力として扱う
- `extract` では `--schema` が必須
- `crop` は PDF 非対応

## 出力と挙動

主な出力は次の通りです。

`Output/` は未指定時の既定出力先です。`--output-dir Results` を指定した場合は、以下の `Output/` を `Results/` に読み替えてください。

- `plain`: `Output/*.plain.md`
- `structured`: `Output/*.structured.json`
- `structured_tsv`: `Output/*.structured.tsv`
- `gamedata`: `Output/*.gamedata.json`
- `schema`: `Output/*.schema.tsv`
- `docai_plain`: `Output/*.docai_plain.md`
- `docai`: `Output/*.docai.tsv`
- `schema_propose`: `Output/schema_proposal.json`
- `extract`: `Output/*.tsv`、`Output/none_*.tsv`、`Output/cache/extract/*.json`
- `crop`: `Output/*.crop.json`、`Output/*.crop_001.png` など

Gemini が不正な JSON や想定外形状を返した場合は、調査用の `*.gemini_json_error.json` を `Output/` に保存します。`extract` は画像内容とスキーマハッシュが一致する場合に `Output/cache/extract/*.json` を再利用します。一部モードでは既存の出力ファイルをスキップし、`plain` / `docai_plain` / `docai` / `extract` では標準出力に性能サマリーも表示されます。

詳細な CLI オプション、ログ、出力仕様は [docs/usage.md](docs/usage.md) を参照してください。

## 開発

```bash
# tests
uv run pytest -q

# lint & format
uv run task ruff
```
