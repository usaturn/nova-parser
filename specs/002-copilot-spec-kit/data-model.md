# Data Model: Devcontainer 上で Spec Kit を Copilot 運用可能にする

## Entity: SpecKitWorkspaceState

- purpose: セットアップ後の作業状態を保持する
- attributes:
  - tool_available: ツール利用可否（true/false）
  - initialized: リポジトリ初期化済みか
  - prerequisite_status: 前提チェック結果（pass/fail）
  - notes: 実行時の補足メモ

## Entity: FeatureDefinition

- purpose: feature ごとの識別と成果物パスを管理する
- attributes:
  - feature_number: 連番（例: 002）
  - short_name: 短縮名（例: copilot-spec-kit）
  - branch_name: ブランチ名
  - spec_file: 仕様ファイルパス
  - plan_file: 計画ファイルパス
  - tasks_file: タスクファイルパス

## Entity: CopilotCommandMapping

- purpose: Chat コマンドと処理単位の対応を表す
- attributes:
  - command_name: `/speckit.*` コマンド名
  - prompt_file: prompt ファイルパス
  - agent_file: agent ファイルパス
  - expected_output: 実行後に得る成果物の種別
