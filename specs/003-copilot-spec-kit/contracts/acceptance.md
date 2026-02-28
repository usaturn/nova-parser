# Contract: Acceptance Checks

## AC-001 導入検証

- 条件: devcontainer 起動済み
- 手順: セットアップコマンドを順に実行
- 合格: ツール利用可能かつ初期化成果物が生成される

## AC-002 feature 開始検証

- 条件: 導入検証完了
- 手順: feature 作成と前提チェックを実行
- 合格: feature ブランチと仕様/計画ファイルのパスが得られ、`check-prerequisites.sh --json --paths-only` で `FEATURE_SPEC` / `IMPL_PLAN` / `TASKS` が返る

## AC-003 Chat 連携検証

- 条件: Copilot 利用可能
- 手順: `/speckit.constitution` と `/speckit.specify` を実行（必要に応じて `/speckit.plan` `/speckit.tasks` `/speckit.implement`）
- 合格: 該当処理フローが開始され、エラー時は認証/接続の理由が表示される
