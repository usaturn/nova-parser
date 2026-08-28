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

# 開発補助ツールの追加（dev group）
uv add --dev <package>

# lint・フォーマット
uv run task ruff
```

## アーキテクチャ

### プロジェクト概要

`nova-parser` は Python 3.14 のプロジェクトで、パッケージマネージャは `uv`。エントリポイントは `uv run nova-parser`（`pyproject.toml` の `[project.scripts]` で定義）。devcontainer は日本語ロケールの設定と Claude Code のインストールを行う。

画像から Gemini および Document AI を使って OCR・構造化抽出を行うアプリケーション。主なモードは `plain`、`structured`、`structured_tsv`、`gamedata`、`schema`、`docai`、`docai_plain`、`schema_propose`、`extract`。`google-genai` SDK を使用し、Vertex AI Express モード（API キー認証）で動作する。環境変数は `.env` で管理（`GOOGLE_GENAI_USE_VERTEXAI`, `VERTEX_AI_API_KEY` 等）。

### 基本ルール

- 配置場所を指定せずにドキュメントを書けと言われた際は、 @tmp/docs_draft/ 配下にドキュメントを作成すること。 @tmp/docs_draft/ 配下のドキュメントはレビューした上で手動で @docs/ 配下に正式ドキュメントとして配置する
- @tmp/docs_draft/ 配下のドキュメントは下書きレベルであり、誤りがある場合もあるので、あまり参考にしない。
- スキル superpowers で Spec や Plan を作成した際に絶対 commit しない
- スキル: superpowers:executing-plans, superpowers:subagent-driven-development, superpowers:writing-skills などの superpower 系スキルでリポジトリを更新する際は、remote origin の HEAD からフォークし、worktree で作業し commit を許可する。その後 PR せよ
- ローカルに `main` ブランチを作成しない
- 正とするブランチは常に `origin/main`
- `origin/main` を更新する変更は、`origin/main` から worktree を作成して feature ブランチ上で作業し、PR で取り込む。`main` 上では commit しない

## 環境

- Windows11 上の WSL2(Gentoo Linux) で Docker を起動し、Dev Containers(Ubuntu 24.04.2 LTS) のコンテナ内で動かしている

## 使用ツール

<!-- context7 -->
Use the `ctx7` CLI to fetch current documentation whenever the user asks about a library, framework, SDK, API, CLI tool, or cloud service -- even well-known ones like React, Next.js, Prisma, Express, Tailwind, Django, or Spring Boot. This includes API syntax, configuration, version migration, library-specific debugging, setup instructions, and CLI tool usage. Use even when you think you know the answer -- your training data may not reflect recent changes. Prefer this over web search for library docs.

Do not use for: refactoring, writing scripts from scratch, debugging business logic, code review, or general programming concepts.

## Steps

1. Resolve library: `npx ctx7@latest library <name> "<user's question>"` — use the official library name with proper punctuation (e.g., "Next.js" not "nextjs", "Customer.io" not "customerio", "Three.js" not "threejs")
2. Pick the best match (ID format: `/org/project`) by: exact name match, description relevance, code snippet count, source reputation (High/Medium preferred), and benchmark score (higher is better). If results don't look right, try alternate names or queries (e.g., "next.js" not "nextjs", or rephrase the question)
3. Fetch docs: `npx ctx7@latest docs <libraryId> "<user's question>"`
4. Answer using the fetched documentation

You MUST call `library` first to get a valid ID unless the user provides one directly in `/org/project` format. Use the user's full question as the query -- specific and detailed queries return better results than vague single words. Do not run more than 3 commands per question. Do not include sensitive information (API keys, passwords, credentials) in queries.

For version-specific docs, use `/org/project/version` from the `library` output (e.g., `/vercel/next.js/v14.3.0`).

If a command fails with a quota error, inform the user and suggest `npx ctx7@latest login` or setting `CONTEXT7_API_KEY` env var for higher limits. Do not silently fall back to training data.
<!-- context7 -->
