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

`.env` ファイルを作成し、必要な変数を設定してください。

| 変数名 | 説明 | 必須 |
|--------|------|------|
| `VERTEX_AI_API_KEY` | Gemini / Pydantic AI / Gemini Vision 用の Vertex AI API キー | `plain` / `structured` / `structured_tsv` / `gamedata` / `schema` / `docai` / `extract` / `crop` で必要 |
| `DOCUMENT_AI_PROCESSOR` | Document AI OCR プロセッサのリソース名 | `docai` / `docai_plain` / `extract` で必須、`crop` の Document AI フォールバックでも使用 |
| `GOOGLE_APPLICATION_CREDENTIALS` | Document AI 用サービスアカウントキーのパス | 任意 |

Document AI の認証は `GOOGLE_APPLICATION_CREDENTIALS`、`.secrets/docai-sa.json`、または ADC の順で解決されます。詳細は [docs/usage.md](docs/usage.md) を参照してください。

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

# 確定スキーマに従って型別 TSV を並列抽出
uv run nova-parser --mode extract --parallel-files 4 --schema Output/schema.json Images/dx3/DX3_EA

# 特定のファイルを指定して処理
uv run nova-parser path/to/image.png
uv run nova-parser path/to/document.pdf
```

`Output/` ディレクトリに各ファイルに対応する `.plain.md`、`.structured.json`、`.structured.tsv`、`.gamedata.json`、`.schema.tsv`、`.docai_plain.md`、`.docai.tsv`、型別 TSV、`.crop.json`、`.crop_001.png` などが出力されます。`docai` / `extract` など一部モードでは、実行時に標準出力へ性能サマリーも表示されます。

## ドキュメント

- [使い方の詳細](docs/usage.md) — CLI オプション、並列実行、サポート形式、ログ、出力仕様
- [Document AI 期待値最適化ガイド](docs/documentai-expected-output.md) — 入力品質、processor 選定、レスポンス診断、`docai` モードへの適用
- [MCP サーバー設定](docs/mcp-servers.md) — Claude Code 用の外部ドキュメント検索設定
- [Context7 を Codex CLI + Skills で使う](docs/context7-codex-cli-skills.md) — Codex CLI 向けの `ctx7 setup --codex --cli --project` 手順と使い方
- [Codex CLI Subagents（マルチエージェント）運用ガイド](docs/codex-subagents.md) — Subagents の基本、カスタム agent 定義、推奨運用
- [Claude Code Agent Teams 運用ガイド](docs/agent-teams.md) — Agent Teams の有効化、標準 Team 設計、運用手順
- [Claude Code feature-dev 詳解ガイド](docs/feature-dev.md) — 7 フェーズの詳細、補助エージェントの役割、導入と基本的な使い方
- [Claude Code feature-dev インストール復旧手順](docs/feature-dev-install-recovery.md) — 壊れた marketplace キャッシュや古いパス参照を修正する手順

## 開発

```bash
# lint & format
uv run task ruff
```
