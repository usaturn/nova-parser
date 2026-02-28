# Research: Devcontainer で Spec Kit を Copilot 運用に載せる

## 決定事項

- Spec Kit は `uvx` と `uv tool` の併用で導入・常用できる。
- `specify init --here --ai copilot` で既存リポジトリへ安全に初期化できる。
- feature 開始は `create-new-feature.sh`、前提検証は `check-prerequisites.sh` で自動化できる。
- Copilot Chat の slash command 実行は VS Code UI 操作が必要で、CLI 単独では代替できない。

## 採用方針

1. Python 関連の実行は `uv` 系コマンドへ統一する。
2. 既存 `nova-parser` CLI の後方互換を維持する。
3. 各ステップに成功判定を設定し、再実行可能な手順として文書化する。

## 検証手順（定義ファイル存在確認）

- prompt 定義確認: `.github/prompts/` 配下の `speckit.*.prompt.md` を確認する。
- agent 定義確認: `.github/agents/` 配下の `speckit.*.agent.md` を確認する。
- いずれも不足時は `specify init --here --ai copilot` を再実行して再生成を確認する。

## リスク

- ネットワーク不通で導入取得が失敗する可能性。
- Copilot 側認証状態により Chat 検証が実施できない可能性。
- 既存差分と導入差分が混在し、レビューしづらくなる可能性。

## 実測ログ（2026-02-28）

- 未解決マーカー検査:
	- コマンド: `grep -nE 'NEEDS CLARIFICATION|\\[FEATURE NAME\\]|\\[###-feature-name\\]|\\[DATE\\]|\\$ARGUMENTS' specs/003-copilot-spec-kit/spec.md specs/003-copilot-spec-kit/plan.md`
	- 結果: 出力なし（未解決マーカーなし）
- 機密情報混入検査:
	- コマンド: `git --no-pager diff -- specs/003-copilot-spec-kit README.md | grep -nE 'API_KEY|SECRET|TOKEN|PASSWORD|PRIVATE KEY|BEGIN RSA|BEGIN OPENSSH'`
	- 結果: 出力なし（機密パターン検出なし）
