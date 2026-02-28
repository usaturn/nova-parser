<!--
Sync Impact Report
- Version change: 1.0.1 -> 1.0.2
- Modified principles: なし（文意変更なし）
- Added sections: なし
- Removed sections: なし
- Templates requiring updates:
	- ✅ .specify/templates/plan-template.md
	- ✅ .specify/templates/spec-template.md
	- ✅ .specify/templates/tasks-template.md
	- ⚠ .specify/templates/commands/*.md (対象ディレクトリ未作成のため更新対象なし)
	- ✅ README.md
- Follow-up TODOs: なし
-->

# nova-parser Constitution

## Core Principles

### I. uv 統一実行
Python 関連コマンドは必ず `uv` 経由で実行する。実行・依存追加・lint/format は `uv run` / `uv add` / `uv run task ruff` に統一し、手順の再現性を保証する。

### II. 既存CLI互換性の維持
エントリポイント `uv run nova-parser` の利用体験を壊さない。新機能追加時も既存モード（plain/structured/structured_tsv/gamedata/schema/docai）の後方互換を優先する。

### III. 小さく検証可能な変更
変更は最小差分で行い、作業後に実行可能な検証コマンドを必ず残す。失敗時は原因と再現手順を記録し、未検証の推測で完了扱いにしない。

### IV. ドキュメント日本語化
リポジトリ内ドキュメントは日本語で記述する。利用者が同じ手順を再現できるよう、コマンド・前提条件・期待結果を明示する。

### V. 認証情報の安全管理
APIキー等の秘匿情報は `.env` と devcontainer の環境注入で管理し、平文の認証情報をコミットしない。機密漏えいの可能性がある生成物は `.gitignore` で保護する。

## 追加制約

- ランタイムは Python 3.14 を前提とする。
- OCR/LLM 関連の外部API利用時は、ネットワーク可用性と認証済み状態を前提条件として明示する。
- 出力フォーマット（Markdown/JSON/TSV）を変更する場合は既存の `Output/` 互換を考慮する。

## 開発ワークフロー

1. 変更前に対象範囲を明確化し、影響ファイルを限定する。
2. 実装後は対象機能に最も近い単位から順に検証する。
3. 破壊的変更や運用変更がある場合は README もしくは docs を更新する。
4. 生成AI連携機能の追加時は、認証前提と手動操作箇所を明示する。

## Governance

本 Constitution は開発手順上の最上位ルールとして扱う。改訂時は以下を必須とする。

1. 改訂提案に目的・影響範囲・移行方針を記録する。
2. 版数はセマンティックバージョニング（MAJOR/MINOR/PATCH）で更新する。
3. 依存テンプレート（plan/spec/tasks）とランタイム文書（README/docs）への反映有無を確認する。
4. レビュー時は本ファイルへの準拠確認を必須ゲートとする。

**Version**: 1.0.2 | **Ratified**: 2026-02-28 | **Last Amended**: 2026-02-28
