# Quickstart: Devcontainer で Spec Kit を Copilot 運用に載せる

## 前提

- devcontainer 起動済み
- `uv` 利用可能
- VS Code で GitHub Copilot 利用可能

## 1. セットアップ

```bash
uvx --from git+https://github.com/github/spec-kit.git specify check
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify check
specify init --here --ai copilot
```

期待結果:

- `Specify CLI is ready to use!` が表示される
- `.specify/`, `.github/prompts/`, `.github/agents/` が存在する

## 2. feature 開始

```bash
bash .specify/scripts/bash/create-new-feature.sh --json "copilotでspec kit動作確認"
bash .specify/scripts/bash/check-prerequisites.sh --json --paths-only
bash .specify/scripts/bash/setup-plan.sh --json
```

期待結果:

- feature ブランチが作成される
- `spec.md` と `plan.md` が作成される
- `check-prerequisites.sh --json --paths-only` で `FEATURE_SPEC` / `IMPL_PLAN` / `TASKS` が返る

## 3. Copilot Chat 連携

Copilot Chat で順に実行:

1. `/speckit.constitution`
2. `/speckit.specify`
3. `/speckit.plan`
4. `/speckit.tasks`
5. `/speckit.implement`

期待結果:

- 各コマンドで対応フローが開始される

## 再実行判定基準

- 同じ手順を再実行しても `specify check` が成功する
- 既存の Spec Kit 関連ファイルが破壊されず、必要ファイルが維持される
