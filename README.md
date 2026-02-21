# nova-parser

書籍からゲームデータを Gemini で抽出する OCR アプリケーション。

`Images/` ディレクトリに配置した画像を Gemini (`gemini-3.1-pro-preview`) で OCR し、Markdown 形式で `Output/` に出力します。

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

## クイックスタート

```bash
# Images/ 内の全画像を処理
uv run nova-parser

# 特定のファイルを指定して処理
uv run nova-parser path/to/image.png
```

`Output/` ディレクトリに各画像に対応する Markdown ファイルが出力されます。

## ドキュメント

- [使い方の詳細](docs/usage.md) — CLI オプション、サポート形式、出力仕様

## 開発

```bash
# lint & format
uv run task ruff
```
