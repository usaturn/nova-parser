# Tasks: Devcontainer で Spec Kit を Copilot 運用に載せる

**Input**: Design documents from `/specs/003-copilot-spec-kit/`  
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 実行環境と導入手順の土台を揃える

- [x] T001 Spec Kit 前提条件を検証するコマンド手順を `specs/003-copilot-spec-kit/quickstart.md` に定義する
- [x] T002 `uvx` と `uv tool` の導入手順を `README.md` に反映する
- [x] T003 初期化コマンド `specify init --here --ai copilot` の運用手順を `specs/003-copilot-spec-kit/quickstart.md` に反映する

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 全ユーザーストーリーの前提となる共通条件を確立する

**⚠️ CRITICAL**: このフェーズ完了前にユーザーストーリー実装へ進まない

- [x] T004 feature 前提チェックの期待結果を `specs/003-copilot-spec-kit/contracts/acceptance.md` に定義する
- [x] T005 Copilot 用 prompt 定義の存在確認手順を `specs/003-copilot-spec-kit/research.md` に記録する
- [x] T006 Copilot 用 agent 定義の存在確認手順を `specs/003-copilot-spec-kit/research.md` に記録する
- [x] T007 共通ガバナンス要件（uv統一・機密管理）との整合結果を `specs/003-copilot-spec-kit/plan.md` に反映する

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - セットアップを完了できる (Priority: P1) 🎯 MVP

**Goal**: 開発者が devcontainer で Spec Kit セットアップを再現できる状態にする

**Independent Test**: `specs/003-copilot-spec-kit/quickstart.md` の手順だけで導入と利用可能確認が完結する

- [x] T008 [US1] セットアップ前提（devcontainer・uv・Copilot）を `specs/003-copilot-spec-kit/quickstart.md` に明記する
- [x] T009 [US1] セットアップ実行コマンドと期待出力を `specs/003-copilot-spec-kit/quickstart.md` に明記する
- [x] T010 [US1] 再実行時の確認観点（同等結果の判定基準）を `specs/003-copilot-spec-kit/spec.md` に反映する

**Checkpoint**: User Story 1 が単独で実行・検証可能

---

## Phase 4: User Story 2 - feature 仕様を起票できる (Priority: P2)

**Goal**: feature 起票フローを実行し、仕様・計画作成へ接続できる状態にする

**Independent Test**: feature 作成手順でブランチと `spec.md` / `plan.md` の生成条件を確認できる

- [x] T011 [US2] feature 作成手順と成功条件を `specs/003-copilot-spec-kit/quickstart.md` に反映する
- [x] T012 [US2] feature 識別情報（番号・短縮名・パス）を `specs/003-copilot-spec-kit/data-model.md` に反映する
- [x] T013 [US2] 起票後の前提チェック手順を `specs/003-copilot-spec-kit/contracts/acceptance.md` に反映する
- [x] T014 [US2] 仕様起票の運用境界（対象/非対象）を `specs/003-copilot-spec-kit/spec.md` に反映する

**Checkpoint**: User Story 2 が単独で実行・検証可能

---

## Phase 5: User Story 3 - Copilot Chat で実行できる (Priority: P3)

**Goal**: Copilot Chat の slash command から Spec Kit 運用を開始できる状態にする

**Independent Test**: Chat 実行手順のみで `/speckit.constitution` と `/speckit.specify` の開始条件を確認できる

- [x] T015 [US3] slash command 実行順序を `specs/003-copilot-spec-kit/quickstart.md` に定義する
- [x] T016 [US3] Chat 実行の受け入れ条件を `specs/003-copilot-spec-kit/contracts/acceptance.md` に反映する
- [x] T017 [US3] Chat 実行時の制約（UI 手動操作・認証依存）を `specs/003-copilot-spec-kit/research.md` に反映する

**Checkpoint**: User Story 3 が単独で実行・検証可能

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 横断品質を最終確認する

- [x] T018 仕様・計画文書の未解決マーカー検査結果を `specs/003-copilot-spec-kit/research.md` に追記する
- [x] T019 機密情報混入チェック結果を `specs/003-copilot-spec-kit/research.md` に追記する
- [x] T020 実行時の最終運用手順を `README.md` と `specs/003-copilot-spec-kit/quickstart.md` で整合させる

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: 依存なし
- **Phase 2 (Foundational)**: Phase 1 完了後に実施（全ストーリーのブロッカー）
- **Phase 3-5 (User Stories)**: Phase 2 完了後に開始
- **Phase 6 (Polish)**: すべての対象ストーリー完了後に実施

### User Story Dependencies

- **US1 (P1)**: Foundation 完了後に開始、他ストーリーへの依存なし
- **US2 (P2)**: Foundation 完了後に開始、US1の成果を参照可能だが独立検証可能
- **US3 (P3)**: Foundation 完了後に開始、US1/US2と独立検証可能

### Dependency Graph

- Setup → Foundational → {US1, US2, US3} → Polish
- 優先実行順は MVP 重視で **US1 → US2 → US3**

---

## Parallel Opportunities

- **User Story 2**: T012 と T013 は並行可能（`data-model.md` と `contracts/acceptance.md` でファイル分離）
- **User Story 3**: T016 と T017 は並行可能（`contracts/acceptance.md` と `research.md` でファイル分離）

### Parallel Example: User Story 2

```bash
Task: T012 [US2] Feature識別情報を data-model に反映
Task: T013 [US2] 起票後前提チェック手順を contracts に反映
```

### Parallel Example: User Story 3

```bash
Task: T016 [US3] Chat受け入れ条件を contracts に反映
Task: T017 [US3] Chat実行制約を research に反映
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup
2. Phase 2: Foundational
3. Phase 3: User Story 1
4. US1 の独立検証を実施し、導入再現性を確定

### Incremental Delivery

1. Setup + Foundational を完了
2. US1 を完了して MVP として運用開始
3. US2 を追加して起票導線を確立
4. US3 を追加して Copilot Chat 導線を確立
5. Polish で横断品質を確認

### Suggested MVP Scope

- **User Story 1 (P1) のみ**を MVP として先行完了し、導入再現性を最初に確保する
