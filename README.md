# nova-parser

書籍からゲームデータを Gemini / Document AI で抽出する OCR アプリケーション。

`Images/` ディレクトリに配置した画像や PDF を Gemini または Document AI で処理し、Markdown テキスト、構造化 JSON、TSV として `Output/` に出力します。

## セットアップ

### 前提条件

- Python 3.14
- [uv](https://docs.astral.sh/uv/)

### インストール

```bash
uv sync
```

### 環境変数

`.env` ファイルを作成し、以下の変数を設定してください。

| 変数名 | 説明 | 必須 |
|--------|------|------|
| `GOOGLE_GENAI_USE_VERTEXAI` | `true` に設定 | Yes |
| `VERTEX_AI_API_KEY` | Vertex AI API キー | Yes |
| `DOCUMENT_AI_PROCESSOR` | Document AI OCR プロセッサのリソース名 | docai / docai_plain モードのみ |

## クイックスタート

```bash
# Images/ 内の全画像・PDF を OCR（Markdown 出力）
uv run nova-parser

# 構造化抽出モード（JSON 出力）
uv run nova-parser --mode structured Images/NAN_067.tif

# 構造化抽出モード（TSV 出力）
uv run nova-parser --mode structured_tsv Images/NAN_067.tif

# ゲームデータ動的抽出モード（JSON 出力）
uv run nova-parser --mode gamedata Images/TNX_OFC_020.tif

# スキーマ抽出モード（型名・フィールド名のみ、TSV 出力）
uv run nova-parser --mode schema Images/TNX_OFC_020.tif

# Document AI OCR（Markdown 出力）
uv run nova-parser --mode docai_plain Images/NAN_067.tif

# Document AI OCR + 構造化 TSV 出力
uv run nova-parser --mode docai Images/NAN_067.tif

# 特定のファイルを指定して処理
uv run nova-parser path/to/image.png
uv run nova-parser path/to/document.pdf
```

`Output/` ディレクトリに各ファイルに対応する `.plain.md`、`.structured.json`、`.structured.tsv`、`.gamedata.json`、`.schema.tsv`、`.docai_plain.md`、`.docai.tsv` ファイルが出力されます。

## ドキュメント

- [使い方の詳細](docs/usage.md) — CLI オプション、サポート形式、出力仕様
- [Document AI 期待値最適化ガイド](docs/documentai-expected-output.md) — 入力品質、processor 選定、レスポンス診断、`docai` モードへの適用
- [MCP サーバー設定](docs/mcp-servers.md) — Claude Code 用の外部ドキュメント検索設定
- [Codex CLI Subagents（マルチエージェント）運用ガイド](docs/codex-subagents.md) — Subagents の基本、カスタム agent 定義、推奨運用
- [Claude Code Agent Teams 運用ガイド](docs/agent-teams.md) — Agent Teams の有効化、標準 Team 設計、運用手順
- [Claude Code feature-dev 詳解ガイド](docs/feature-dev.md) — 7 フェーズの詳細、補助エージェントの役割、導入と基本的な使い方
- [Claude Code feature-dev インストール復旧手順](docs/feature-dev-install-recovery.md) — 壊れた marketplace キャッシュや古いパス参照を修正する手順

## 開発

```bash
# lint & format
uv run task ruff
```
