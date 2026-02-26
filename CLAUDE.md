# CLAUDE.md

このファイルは、Claude Code (claude.ai/code) がこのリポジトリで作業する際のガイダンスを提供します。

## 言語

- 応答は日本語で行うこと
- ドキュメント（CLAUDE.md等）は全て日本語で記述すること

## コマンド

Python 系コマンドは全て `uv` 経由で実行すること。

```bash
# プロジェクトの実行
uv run nova-parser

# 依存パッケージの追加
uv add <package>

# lint・フォーマット
uv run task ruff
```

## アーキテクチャ

### プロジェクト概要

`nova-parser` は Python 3.14 のプロジェクトで、パッケージマネージャは `uv`。エントリポイントは `uv run nova-parser`（`pyproject.toml` の `[project.scripts]` で定義）。devcontainer は日本語ロケールの設定と Claude Code のインストールを行う。

画像から Gemini および Document AI を使って OCR・構造化抽出を行うアプリケーション。6つのモード（`plain`, `structured`, `structured_tsv`, `gamedata`, `schema`, `docai`）を提供する。`google-genai` SDK を使用し、Vertex AI Express モード（API キー認証）で動作する。環境変数は `.env` で管理（`GOOGLE_GENAI_USE_VERTEXAI`, `VERTEX_AI_API_KEY` 等）。
