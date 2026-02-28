# nova-parser

書籍からゲームデータを Gemini / Document AI で抽出する OCR アプリケーション。

`Images/` ディレクトリに配置した画像を Gemini または Document AI で処理し、Markdown テキスト、構造化 JSON、TSV として `Output/` に出力します。

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
| `DOCUMENT_AI_PROCESSOR` | Document AI OCR プロセッサのリソース名 | docai モードのみ |

## クイックスタート

```bash
# Images/ 内の全画像を OCR（Markdown 出力）
uv run nova-parser

# 構造化抽出モード（JSON 出力）
uv run nova-parser --mode structured Images/NAN_067.tif

# 構造化抽出モード（TSV 出力）
uv run nova-parser --mode structured_tsv Images/NAN_067.tif

# ゲームデータ動的抽出モード（JSON 出力）
uv run nova-parser --mode gamedata Images/TNX_OFC_020.tif

# スキーマ抽出モード（型名・フィールド名のみ、TSV 出力）
uv run nova-parser --mode schema Images/TNX_OFC_020.tif

# Document AI OCR + 構造化 TSV 出力
uv run nova-parser --mode docai Images/NAN_067.tif

# 特定のファイルを指定して処理
uv run nova-parser path/to/image.png
```

`Output/` ディレクトリに各画像に対応する `.plain.md`、`.structured.json`、`.structured.tsv`、`.gamedata.json`、`.schema.tsv`、`.docai.tsv` ファイルが出力されます。

## ドキュメント

- [使い方の詳細](docs/usage.md) — CLI オプション、サポート形式、出力仕様
- [MCP サーバー設定](docs/mcp-servers.md) — Claude Code 用の外部ドキュメント検索設定
- [Spec Kit 5分オンボーディング](docs/spec-kit-onboarding.md) — 最短手順で導入・起票を始めるためのクイックガイド
- [Spec Kit 利用ガイド（詳細版）](docs/spec-kit-guide-detailed.md) — 日常運用向けの手順、コマンド、クローズ基準、トラブル対応
- [Spec Kit ガイド入口](docs/spec-kit-guide.md) — オンボーディング版・詳細版・実装記録への導線
- [Spec Kit 実装記録](docs/spec-kit-implementation.md) — devcontainer + Copilot での導入手順、成果物、検証、クローズ基準

## 開発

```bash
# lint & format
uv run task ruff
```

## Spec Kit（GitHub Copilot）

このリポジトリでは Spec Kit を `uv` 経由で利用します。

```bash
# 単発実行
uvx --from git+https://github.com/github/spec-kit.git specify check

# 永続インストール
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify check
```

初期化（既存リポジトリにマージ）:

```bash
specify init --here --ai copilot
```

初期化後は VS Code の Copilot Chat で以下を順に実行します。

- `/speckit.constitution`
- `/speckit.specify`
- `/speckit.plan`
- `/speckit.tasks`
- `/speckit.implement`
