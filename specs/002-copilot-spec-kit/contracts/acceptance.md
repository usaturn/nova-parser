# Contract: Acceptance Checks

## AC-001 セットアップ完了
- 入力: devcontainer 起動直後の環境
- 手順: セットアップコマンドを順に実行
- 合格条件: ツールチェック成功と初期化成果物の存在

## AC-002 feature 開始
- 入力: セットアップ完了環境
- 手順: feature 作成と前提チェックを実行
- 合格条件: feature ブランチ作成と spec/plan のパス取得

## AC-003 Copilot 連携
- 入力: VS Code + Copilot 利用可能状態
- 手順: `/speckit.constitution` と `/speckit.specify` を実行
- 合格条件: 該当エージェント処理の応答が開始される
