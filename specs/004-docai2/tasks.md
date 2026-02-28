# Tasks: docai2の出力品質改善

**Input**: Design documents from `/specs/004-docai2/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 featureブランチとspec初期化を実施（`specs/004-docai2/spec.md`）
- [X] T002 Spec Kit初期化と関連ディレクトリ作成を実施（`.specify/`, `.github/prompts/`, `.github/agents/`）
- [X] T003 planテンプレートを配置（`specs/004-docai2/plan.md`）

---

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T004 [P] `docai2` モードのCLI接続を追加（`src/nova_parser/main.py`）
- [X] T005 [P] `docai2` パイプライン実装を追加（`src/nova_parser/docai2.py`）
- [X] T006 `docai2` の利用手順と認証手順を追記（`docs/usage.md`）

---

## Phase 3: User Story 1 - TSV欠損値の安定化 (P1)

**Independent Test**: `docai2` 出力TSVに `None` / `null` が含まれない

- [X] T007 [US1] 欠損値を空文字へ変換する `_safe_value` を実装（`src/nova_parser/docai2.py`）
- [X] T008 [US1] TSV変換で `_safe_value` を全列に適用（`src/nova_parser/docai2.py`）
- [X] T009 [US1] `types` 空時に空TSVを返す挙動を確認（`src/nova_parser/docai2.py`）

---

## Phase 4: User Story 2 - 表見出し準拠の構造化抽出 (P2)

**Independent Test**: 抽出キーが見出し準拠で生成される

- [X] T010 [US2] 抽出プロンプトへ「見出し忠実使用」を明記（`src/nova_parser/docai2.py`）
- [X] T011 [US2] フィールド順を初出順で収集する実装を追加（`src/nova_parser/docai2.py`）
- [X] T012 [US2] 未知型を許容する抽出方針をプロンプトへ明記（`src/nova_parser/docai2.py`）

---

## Phase 5: User Story 3 - 実行時エラーの明確化 (P3)

**Independent Test**: 設定不足時に原因と設定例が表示される

- [X] T013 [US3] `DOCUMENT_AI_PROCESSOR` 未設定時のエラーメッセージを明確化（`src/nova_parser/docai2.py`）
- [X] T014 [US3] 無効な `GOOGLE_APPLICATION_CREDENTIALS` からのADCフォールバックを実装（`src/nova_parser/docai2.py`）

---

## Phase 6: Polish & Cross-Cutting

- [X] T015 設計成果物を作成（`specs/004-docai2/research.md`, `specs/004-docai2/data-model.md`, `specs/004-docai2/quickstart.md`）
- [X] T016 憲章を具体化（`.specify/memory/constitution.md`）
- [X] T017 lint/formatを実行して最終検証（`uv run task ruff`）

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → (US1, US2, US3) → Phase 6
- 実装順序は P1 を最優先し、P2/P3 は独立して検証可能
