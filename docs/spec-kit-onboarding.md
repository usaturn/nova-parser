# Spec Kit 5分オンボーディング（nova-parser）

このページは、初参加メンバーが最短で Spec Kit を使い始めるための手順です。

## 0. 前提

- devcontainer 起動済み
- `uv` が使える
- VS Code で GitHub Copilot が利用可能

## 1. セットアップ（約2分）

```bash
uvx --from git+https://github.com/github/spec-kit.git specify check
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify check
specify init --here --ai copilot
```

確認:

- `Specify CLI is ready to use!` が表示される
- `.specify/`, `.github/prompts/`, `.github/agents/` が存在する

## 2. feature 開始（約2分）

```bash
bash .specify/scripts/bash/create-new-feature.sh --json "機能概要"
bash .specify/scripts/bash/check-prerequisites.sh --json --paths-only
bash .specify/scripts/bash/setup-plan.sh --json
```

確認:

- `NNN-short-name` ブランチが作成される
- `FEATURE_SPEC`, `IMPL_PLAN`, `TASKS` が JSON で返る

## 3. Copilot Chat 実行（約1分）

実行順:

1. `/speckit.constitution`
2. `/speckit.specify`
3. `/speckit.plan`
4. `/speckit.tasks`
5. `/speckit.implement`

## 4. クローズ判定

- `tasks.md` の未完了が 0
- `spec.md` / `plan.md` / `tasks.md` に未解決マーカーがない
- 検証ログ（前提チェック・機密チェック）が残っている

## 5. つまずきやすい点

- `specify --version` が失敗する場合は `specify version` を使う
- `Not on a feature branch` は `create-new-feature.sh` を先に実行する
- `init` の確認待ちは `printf 'y\n' | specify init --here --ai copilot` で非対話化できる
