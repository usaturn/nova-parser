# Tasks: Devcontainer 上で Spec Kit を Copilot 運用可能にする

**Input**: `/specs/002-copilot-spec-kit/` の設計文書  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 `uvx --from git+https://github.com/github/spec-kit.git specify check` を実行し、利用可能状態を確認する
- [x] T002 `uv tool install specify-cli --from git+https://github.com/github/spec-kit.git` を実行する
- [x] T003 `specify check` を実行し、永続利用の確認結果を記録する
- [x] T004 README の Spec Kit 手順を最新状態に合わせて確認する

---

## Phase 2: Foundational (Blocking Prerequisites)

- [x] T005 `specify init --here --ai copilot` を実行し、初期化を完了する
- [x] T006 [P] `.github/prompts/` の `/speckit.*` 定義ファイルを確認する
- [x] T007 [P] `.github/agents/` の対応 agent ファイルを確認する
- [x] T008 `bash .specify/scripts/bash/check-prerequisites.sh --json --paths-only` を実行し、feature前提を確認する

---

## Phase 3: User Story 1 - セットアップ完了を再現できる (Priority: P1)

**Goal**: セットアップ手順を再現可能にする

**Independent Test**: 同一手順の再実行で同等結果を得る

- [x] T009 [US1] `specify check` の再実行で成功することを確認する
- [x] T010 [US1] `quickstart.md` に手順と期待結果を反映する

---

## Phase 4: User Story 2 - 仕様作成フローを開始できる (Priority: P2)

**Goal**: feature ブランチと仕様雛形を生成できる

**Independent Test**: feature 実行で `spec.md` と `plan.md` が作成される

- [x] T011 [US2] `create-new-feature.sh --json` を実行して feature を作成する
- [x] T012 [US2] `setup-plan.sh --json` を実行して `plan.md` を生成する
- [x] T013 [US2] `spec.md` と `plan.md` を具体化する

---

## Phase 5: User Story 3 - Copilot Chat 連携で運用できる (Priority: P3)

**Goal**: Copilot Chat から Spec Kit フローを開始できる

**Independent Test**: `/speckit.constitution` と `/speckit.specify` が応答する

- [ ] T014 [US3] Copilot Chat で `/speckit.constitution` を実行する
- [ ] T015 [US3] Copilot Chat で `/speckit.specify` を実行する
- [ ] T016 [US3] 必要に応じて `/speckit.plan` と `/speckit.tasks` を実行する

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T017 実行ログと最終差分を確認し、不要差分がないことを保証する
- [x] T018 ドキュメントが日本語で統一されていることを確認する
- [x] T019 機密情報が差分に含まれていないことを確認する

---

## Dependencies & Execution Order

- Setup（Phase 1）→ Foundational（Phase 2）→ User Stories（Phase 3〜5）→ Polish（Phase 6）
- US2/US3 は US1 完了後に進める
- [P] タスクは同フェーズ内で並行実行可能

## Notes

- Python 関連の操作は `uv` 系コマンドを使用する
- 既存 `nova-parser` の実行機能は変更しない
- Copilot Chat 実行は VS Code UI 上の手動操作が必要
