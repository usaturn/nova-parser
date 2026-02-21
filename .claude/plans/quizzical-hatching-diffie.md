# Gemini OCR アプリケーション開発環境セットアップ

## コンテキスト

`nova-parser` リポジトリに、`Images/` ディレクトリ内の画像を Gemini（Vertex AI Express モード、API キー認証）で OCR する Python アプリケーションの開発環境を整える。アプリケーションの具体的な要件は今後定義するため、今回は開発基盤のみを構築する。

`.env` に Vertex AI Express モードの API キー設定は既に存在する。

## 変更内容

### 1. 依存パッケージの追加

```bash
uv add google-genai
```

- `google-genai` SDK を追加（`.env` の `GOOGLE_GENAI_USE_VERTEXAI=true` と連携して Vertex AI 経由で動作）

### 2. `Images/` ディレクトリの作成

- `Images/` ディレクトリを作成し、`.gitkeep` を配置（ディレクトリ自体は Git 管理対象とする）
- `.gitignore` に `Images/*` と `!Images/.gitkeep` を追加（画像ファイルは Git 管理外、ディレクトリ構造は保持）
- 既存の `images/`（小文字）のエントリはそのまま残す

### 3. `main.py` の更新

Gemini API への接続確認ができる最小限のスケルトンに更新する：
- `google.genai` クライアントの初期化
- `Images/` ディレクトリから画像を読み込む基本構造
- 環境変数（`GOOGLE_GENAI_USE_VERTEXAI`, `VERTEX_AI_API_KEY`）による認証
- 具体的な OCR ロジックはプレースホルダーとし、要件定義後に実装

### 4. `CLAUDE.md` の更新

- プロジェクト概要を OCR アプリケーションに更新
- `google-genai` SDK の使用と Vertex AI Express モードについて記載
- `Images/` ディレクトリの用途を記載

## 対象ファイル

| ファイル | 操作 |
|---------|------|
| `pyproject.toml` | `uv add` で自動更新 |
| `uv.lock` | `uv add` で自動生成 |
| `Images/.gitkeep` | 新規作成 |
| `.gitignore` | 編集（Images パターン追加） |
| `main.py` | 編集（スケルトン実装） |
| `CLAUDE.md` | 編集（プロジェクト情報更新） |

## 検証方法

```bash
# 依存パッケージが正しくインストールされているか確認
uv run python -c "import google.genai; print('google-genai OK')"

# main.py が構文エラーなく動作するか確認
uv run python main.py
```
