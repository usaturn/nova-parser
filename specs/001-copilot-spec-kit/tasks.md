# Tasks: Copilot で Spec Kit をセットアップし実行試験する

**Input**: `/specs/001-copilot-spec-kit/` の設計文書  
**Prerequisites**: plan.md, spec.md

## Phase 1: Setup

- [x] T001 `uvx --from git+https://github.com/github/spec-kit.git specify check` を実行し CLI 疎通を確認する
- [x] T002 `uv tool install specify-cli --from git+https://github.com/github/spec-kit.git` を実行し永続化する
- [x] T003 `specify version` と `specify check` で利用可能状態を確認する

## Phase 2: Foundation

- [x] T004 `specify init --here --ai copilot` を実行し Spec Kit を初期化する
- [x] T005 `.github/prompts/` と `.github/agents/` の `speckit.*` ファイル生成を確認する
- [x] T006 `.specify/scripts/bash/` の実行権限とスクリプト存在を確認する

## Phase 3: User Story 1 (P1) 導入完了確認

- [x] T007 `create-new-feature.sh --json "copilotでspec kit動作確認"` を実行する
- [x] T008 `specs/001-copilot-spec-kit/spec.md` の生成を確認する

## Phase 4: User Story 2 (P2) ワークフロー進行確認

- [x] T009 `check-prerequisites.sh --json --paths-only` を実行し `FEATURE_SPEC` / `IMPL_PLAN` / `TASKS` を取得する
- [x] T010 `setup-plan.sh --json` を実行し `plan.md` を生成する

## Phase 5: User Story 3 (P3) Copilot 実行接続

- [ ] T011 VS Code Copilot Chat で `/speckit.constitution` を実行する
- [ ] T012 続けて `/speckit.specify` を実行し、仕様更新フローが開始することを確認する
- [ ] T013 必要に応じて `/speckit.plan` と `/speckit.tasks` を実行し、成果物生成を確認する

## Notes

- T011 以降は VS Code UI 上の手動操作が必要。
- 既存の未コミット差分があるため、コミット前に `git status` で差分を確認する。
