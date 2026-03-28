# CLAUDE.md

## 基本

- ユーザの入力が曖昧な場合は積極的に質問して解像度を上げる
- 実装速度よりコード品質、保守性、テスト容易性を優先する
- 計画や設計が必要な変更では、十分に検討してから実装に入る

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

画像から Gemini および Document AI を使って OCR・構造化抽出を行うアプリケーション。主なモードは `plain`、`structured`、`structured_tsv`、`gamedata`、`schema`、`docai`、`docai_plain`、`schema_propose`、`extract`。`google-genai` SDK を使用し、Vertex AI Express モード（API キー認証）で動作する。環境変数は `.env` で管理（`GOOGLE_GENAI_USE_VERTEXAI`, `VERTEX_AI_API_KEY` 等）。
