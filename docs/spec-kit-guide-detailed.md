# Spec Kit 利用ガイド（詳細版 / nova-parser）

このガイドは、`nova-parser` で Spec Kit を継続運用するための詳細手順です。

## 1. 目的

- 仕様駆動開発の標準フローを定着させる
- Copilot Chat と CLI の両方で同じ成果物を再現できるようにする
- 手順・検証・クローズ基準をチームで共通化する

## 2. 利用全体像

1. 憲章: `/speckit.constitution`
2. 仕様: `/speckit.specify`
3. 計画: `/speckit.plan`
4. タスク: `/speckit.tasks`
5. 実装: `/speckit.implement`

## 3. 環境前提

- Python 3.14
- `uv` ベース運用（`uvx`, `uv tool`, `uv run`）
- devcontainer
- VS Code + GitHub Copilot

## 4. 初回導入手順

### 4.1 導入確認（単発）

```bash
uvx --from git+https://github.com/github/spec-kit.git specify check
```

### 4.2 永続導入

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify check
specify version
```

### 4.3 リポジトリ初期化

```bash
specify init --here --ai copilot
```

非対話:

```bash
printf 'y\n' | specify init --here --ai copilot
```

### 4.4 生成物確認

```bash
ls -la .specify
ls -la .github/prompts
ls -la .github/agents
```

## 5. feature 運用フロー

### 5.1 起票

```bash
bash .specify/scripts/bash/create-new-feature.sh --json "機能概要"
```

### 5.2 前提チェック

```bash
bash .specify/scripts/bash/check-prerequisites.sh --json --paths-only
```

確認するキー:

- `FEATURE_SPEC`
- `IMPL_PLAN`
- `TASKS`

### 5.3 plan 初期化

```bash
bash .specify/scripts/bash/setup-plan.sh --json
```

### 5.4 Chat 実行

1. `/speckit.constitution`
2. `/speckit.specify`
3. `/speckit.plan`
4. `/speckit.tasks`
5. `/speckit.implement`

補足:

- Chat 実行は UI 依存のため、CLI テストと分離して記録する

## 6. 成果物構成

- `.specify/`: 記憶・スクリプト・テンプレート
- `.github/prompts/`: slash command 用 prompt
- `.github/agents/`: 各コマンドのエージェント定義
- `specs/NNN-short-name/`: feature ごとの spec / plan / tasks と補助文書

## 7. コマンドリファレンス

| 目的 | コマンド |
|---|---|
| 単発チェック | `uvx --from git+https://github.com/github/spec-kit.git specify check` |
| 永続導入 | `uv tool install specify-cli --from git+https://github.com/github/spec-kit.git` |
| 利用確認 | `specify check` |
| バージョン確認 | `specify version` |
| 初期化 | `specify init --here --ai copilot` |
| feature 起票 | `bash .specify/scripts/bash/create-new-feature.sh --json "..."` |
| 前提チェック | `bash .specify/scripts/bash/check-prerequisites.sh --json --paths-only` |
| plan 生成 | `bash .specify/scripts/bash/setup-plan.sh --json` |

## 8. クローズ基準

- `tasks.md` 未完了 0
- `spec.md` / `plan.md` / `tasks.md` に未解決マーカーなし
- 前提チェック・機密チェック結果が記録済み
- README と docs の手順整合済み

## 9. トラブルシューティング

### 9.1 `specify --version` が使えない

- 対応: `specify version`

### 9.2 `Not on a feature branch`

- 対応: `create-new-feature.sh` を先に実行

### 9.3 `init` が確認待ちで止まる

- 対応: `printf 'y\n' | specify init --here --ai copilot`

### 9.4 Copilot Chat が反応しない

- Copilot 有効化を確認
- `.github/prompts/` と `.github/agents/` の存在確認
- 必要なら `specify init --here --ai copilot` 再実行

## 10. 関連文書

- 実装の実測ログと履歴: [Spec Kit 実装記録](spec-kit-implementation.md)
- 最短手順のみ確認したい場合: [5分オンボーディング](spec-kit-onboarding.md)
