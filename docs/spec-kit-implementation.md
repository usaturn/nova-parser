# Spec Kit 実装記録（GitHub Copilot / devcontainer）

このドキュメントは、`nova-parser` リポジトリに対して実施した Spec Kit 導入・運用整備・検証内容を詳細に記録したものです。

## 1. 実装の目的

- devcontainer 環境で Spec Kit を再現可能に導入する
- GitHub Copilot（VS Code）で `/speckit.*` フローを開始できる状態にする
- 仕様駆動開発の成果物（`spec.md` / `plan.md` / `tasks.md`）をテンプレート運用に沿って生成・具体化する
- 導入手順・検証結果・完了条件をドキュメントとして固定化する

## 2. 前提条件

- Python 3.14
- `uv` が利用可能
- VS Code 上で GitHub Copilot が利用可能
- devcontainer で作業していること

## 3. 実行したセットアップ

以下は、今回この devcontainer で実際に通した導入手順をそのまま再現できる形で記載しています。

### 3.0 実行前の確認

```bash
pwd
uv --version
uv run python --version
```

確認ポイント:

- 作業ディレクトリがリポジトリ直下（`/workspaces/nova-parser`）であること
- `uv` が利用可能であること
- Python が 3.14 系であること

### 3.1 Spec Kit 導入確認（単発）

```bash
uvx --from git+https://github.com/github/spec-kit.git specify check
```

確認内容:

- Spec Kit CLI が起動し、利用可能であること
- ツールチェックが完了すること

補足:

- `specify --version` は CLI バージョンによっては未サポートの場合があるため、`specify check` を一次判定に使用した

### 3.2 Spec Kit 常用化（永続）

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify check
```

確認内容:

- `specify` コマンドが常用可能であること

追加確認（実施済み）:

```bash
specify version
```

確認ポイント:

- `CLI Version` / `Template Version` / 実行環境情報が表示されること

### 3.3 リポジトリ初期化

```bash
specify init --here --ai copilot
```

既存ファイルがあるため確認プロンプトが出る場合は、以下のように非対話実行も可能:

```bash
printf 'y\n' | specify init --here --ai copilot
```

確認内容:

- `.specify/` が生成される
- `.github/prompts/` と `.github/agents/` の `speckit.*` 定義が生成される

生成確認（実施済み）:

```bash
ls -la .github/prompts
ls -la .github/agents
```

### 3.4 feature フロー起動確認

導入完了後、Spec Kit の標準フローへ接続できることを確認した。

```bash
bash .specify/scripts/bash/create-new-feature.sh --json "copilotでspec kit動作確認"
bash .specify/scripts/bash/check-prerequisites.sh --json --paths-only
bash .specify/scripts/bash/setup-plan.sh --json
```

確認ポイント:

- feature ブランチが作成されること
- `FEATURE_SPEC` / `IMPL_PLAN` / `TASKS` のパスが JSON で返ること
- `plan.md` が生成されること

### 3.5 導入後の再実行性確認

同一環境で手順を再実行しても壊れないことを確認した。

```bash
specify check
```

確認ポイント:

- 再実行でも `Specify CLI is ready to use!` が得られること
- 既存の Spec Kit 定義ファイルが維持されること

## 4. 実装で作成・更新した主な成果物

### 4.1 共通運用基盤

- `.specify/memory/constitution.md`
- `.specify/templates/plan-template.md`
- `.specify/templates/spec-template.md`
- `.specify/templates/tasks-template.md`
- `README.md`（Spec Kit セクション）

### 4.2 feature 仕様駆動成果物

#### `specs/001-copilot-spec-kit`

- 初回検証用の feature 作成・spec 生成

#### `specs/002-copilot-spec-kit`

- `spec` / `plan` / `tasks` と補助成果物の作成
- 実装タスクの実行と完了判定

#### `specs/003-copilot-spec-kit`

- 最終運用版として `spec` / `plan` / `tasks` を具体化
- `research` / `data-model` / `quickstart` / `contracts` を整備
- `tasks.md` の 20 タスクを完了状態へ反映

## 5. 実行フロー（最終版）

### 5.1 仕様フロー開始

```bash
bash .specify/scripts/bash/create-new-feature.sh --json "copilotでspec kit動作確認"
bash .specify/scripts/bash/check-prerequisites.sh --json --paths-only
bash .specify/scripts/bash/setup-plan.sh --json
```

### 5.2 Copilot Chat 実行順

1. `/speckit.constitution`
2. `/speckit.specify`
3. `/speckit.plan`
4. `/speckit.tasks`
5. `/speckit.implement`

## 6. 検証で実施したこと

### 6.1 前提チェック

- `check-prerequisites.sh --json --paths-only` の JSON 出力確認
- `FEATURE_SPEC` / `IMPL_PLAN` / `TASKS` の解決を確認

追加実施:

- `.github/prompts/` と `.github/agents/` の `speckit.*` ファイル存在確認
- `specify check` の再実行確認

### 6.2 未解決マーカー検査

- `NEEDS CLARIFICATION`
- テンプレートプレースホルダー（`[FEATURE NAME]` など）

検査結果:

- 対象成果物で未解決マーカーは検出なし

### 6.3 機密情報混入検査

- `API_KEY` / `SECRET` / `TOKEN` / `PASSWORD` などを差分から検査

検査結果:

- 対象差分で機密パターン検出なし

## 7. クローズ基準

この作業での「クローズ」は、以下を全て満たした状態を指します。

- `tasks.md` の未完了が 0
- `spec.md` / `plan.md` / `tasks.md` に未解決マーカーがない
- 前提チェックと検証ログが記録されている
- 運用手順が README と docs で整合している

`specs/003-copilot-spec-kit/tasks.md` は上記基準で完了状態です。

## 8. 現在の運用ルール（要点）

- Python 関連は `uv` 経由で実行する
- 既存 `nova-parser` CLI の後方互換を維持する
- 変更後は検証コマンドと結果を残す
- ドキュメントは日本語で更新する
- 機密情報を差分へ含めない

## 9. 今後の運用

- 新規 feature は `create-new-feature.sh` で起票し、`spec` → `plan` → `tasks` の順で進める
- 実行不可のチェック（Chat UI 依存など）は、CLI 検証と分離して記録する
- マージ前に `tasks.md` 完了状態と検証ログを確認する

## 10. トラブルシューティング（今回実際に遭遇した論点）

### 10.1 `specify --version` が失敗する

- 症状: `No such option: --version`
- 対応: `specify version` を使用する

### 10.2 既存リポジトリで `init` が停止する

- 症状: `Current directory is not empty` の確認プロンプトで待機する
- 対応: 手動で `y` 入力、または `printf 'y\n' | specify init --here --ai copilot`

### 10.3 `check-prerequisites.sh` が feature ブランチ要求で失敗する

- 症状: `Not on a feature branch`
- 対応: 先に `create-new-feature.sh` で `NNN-short-name` ブランチを作成する
