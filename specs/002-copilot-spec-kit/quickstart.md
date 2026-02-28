# Quickstart: Devcontainer 上で Spec Kit を Copilot 運用可能にする

## 1. 前提

- devcontainer 起動済み
- `uv` 利用可能
- VS Code で GitHub Copilot 利用可能

## 2. セットアップ

```bash
uvx --from git+https://github.com/github/spec-kit.git specify check
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify check
specify init --here --ai copilot
```

期待結果:

- `Specify CLI is ready to use!` が表示される
- `.specify/`, `.github/prompts/`, `.github/agents/` が存在する

## 3. feature 開始

```bash
bash .specify/scripts/bash/create-new-feature.sh --json "copilotでspec kit動作確認"
bash .specify/scripts/bash/check-prerequisites.sh --json --paths-only
bash .specify/scripts/bash/setup-plan.sh --json
```

期待結果:

- feature ブランチへ切り替わる
- `spec.md` と `plan.md` が生成される

## 4. Copilot Chat 連携確認

VS Code Copilot Chat で順に実行:

1. `/speckit.constitution`
2. `/speckit.specify`
3. `/speckit.plan`
4. `/speckit.tasks`

期待結果:

- 各コマンドで対応エージェントの処理が開始される
