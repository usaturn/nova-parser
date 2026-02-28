# nova-parser Constitution

## Core Principles

### I. CLI First
すべての機能は `uv run nova-parser` の CLI から実行可能でなければならない。新機能追加時は `--mode` などの既存導線を優先し、別実行系を乱立させない。

### II. Japanese-First Documentation
プロジェクト内の運用ドキュメントと利用ガイドは日本語で記述しなければならない。新しい挙動・オプション・前提条件を追加した場合、同一PR内でドキュメント更新を行う。

### III. Safe Defaults for OCR Output
構造化出力では欠損値を安全に扱うことを必須とする。`None` / `null` の文字列混入は禁止し、空値は空文字で統一する。

### IV. Reproducible Toolchain
Python関連の実行・検証は `uv` 経由で行わなければならない。lint/format は `uv run task ruff` を標準ゲートとし、提出前に必ず実行する。

### V. Incremental Delivery with Spec Kit
機能追加は `spec.md` → `plan.md` → `tasks.md` → 実装の順で進め、成果物の整合性を維持する。MVPは User Story 1 から独立テスト可能な単位で完了させる。

## Additional Constraints

- ランタイムは Python 3.14 以上を前提とする
- OCR/抽出の外部依存（Gemini, Document AI）の失敗は利用者が原因を判別できるエラーで返す
- 機密情報（鍵・認証情報）はリポジトリへコミットしない

## Development Workflow

1. feature ブランチ作成後に `spec.md` を確定する
2. `plan.md` と設計成果物（research/data-model/quickstart）を作成する
3. `tasks.md` を実行可能な粒度で作成する
4. 実装後は `uv run task ruff` を通し、必要ドキュメントを更新する

## Governance

- この憲章は仕様・計画・タスクより優先される
- 原則の追加・変更は憲章バージョンを更新し、理由を明記する
- すべてのPRで憲章遵守を確認する

**Version**: 1.0.0 | **Ratified**: 2026-02-28 | **Last Amended**: 2026-02-28
