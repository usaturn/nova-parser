---
name: python-tdd-team
description: nova-parser リポジトリで Python の機能追加・変更を 5 サブエージェント（python-requirements / python-architect / python-test-author / python-implementer / python-reviewer）の TDD パイプラインで進める orchestrator スキル。`/python-tdd-team` の後にタスク説明を続けて明示起動するほか、「TDD チームで実装して」「テスト先行で進めて」「Python チームで」等の自然言語でもトリガーする。受入条件 ID 化・owner ベース差し戻し・fail-closed 契約検証を内蔵。
---

# Python TDD Team

## 目的と適用範囲

nova-parser の Python 機能変更を、TDD パイプライン（要件 → 設計 → テスト先行 → 実装 → レビュー）で進めるための orchestrator。各フェーズは専用サブエージェントが担当し、orchestrator（このスキルを実行している親 Claude）はフェーズ間のオーケストレーション、契約検証、ユーザゲート、差し戻しルーティングだけを担う。

**適用する**:
- `src/nova_parser/` 配下の機能追加 / 既存機能の拡張 / バグ修正
- pydantic スキーマや CLI モードの変更を伴う中規模以上の作業

**適用しない**（重い orchestrator が過剰）:
- ドキュメント単独の変更（`doc-writer` を使う）
- devcontainer / CI / `pyproject.toml` の依存追加のみ
- 1 ファイル数行のタイポ修正

## 前提

スキル起動前に以下を確認する。1 つでも欠けていれば中断してユーザに報告する。

1. `.claude/agents/python-requirements.md`, `python-architect.md`, `python-test-author.md`, `python-implementer.md`, `python-reviewer.md` の 5 ファイルが存在する
2. リポジトリ root の作業ツリーが理解可能な状態（無関係な大量 untracked / 未保存の改変が無い）。汚れていれば `git status --short` を提示してユーザに確認する
3. `uv` が利用可能で `uv run pytest --collect-only` が走る

## トリガー

- **明示**: `/python-tdd-team <タスク説明>`
- **自然言語**: 「TDD チームで X を実装して」「テスト先行で進めて」「Python チームで」「python-tdd-team で」

タスク説明が極端に短い場合は、起動直後に 1〜2 個だけ追加質問してから requirements に渡す（曖昧な依頼を requirements に丸投げしない）。

## ワークフロー（5 フェーズ）

各フェーズは Agent tool で対応するサブエージェントを呼び出す。orchestrator は各フェーズの **出力をパースして次フェーズへの入力に組み立て直す** のが主任務。

### 共有 state（フェーズ間で持ち回る）

orchestrator が記憶しておくべき値:

- `task_description`: ユーザの依頼文
- `criteria[]`: requirements 出力の受入条件配列（id / description / category）
- `prior_criteria[]`: requirements を再呼び出しする際に渡す前回 criteria
- `design_summary`: architect 出力サマリ（テキスト）
- `generated_files[]`: test-author / implementer が新規作成・編集したファイルパスリスト
- `review_mode`: `worktree` / `commit` / `mixed`（既定は `worktree`）
- `base_ref`: 既定 `main`
- `loop_count_by_owner`: `{implementation: N, test: N, design: N, requirement: N}` の差し戻し回数カウンタ

### Phase 1: requirements

**目的**: タスク説明を構造化要件と機械可読受入条件 (`AC-N`) に変換する。

呼び出し:
- Agent tool で `subagent_type: python-requirements`
- 渡す引数: `task_description`、再呼び出しなら `prior_criteria`

検証 (fail-closed):
- 出力に `criteria[]` JSON が存在し、`id` `description` `category` が enum 制約を満たす
- 詳細は [references/contracts.md](references/contracts.md) を参照

**ユーザゲート 1**: criteria[] を Markdown チェックリスト形式で提示し、「進む / 修正指示 / 中止」をユーザに確認。修正指示があれば prior_criteria を渡して requirements を再呼び出し。

### Phase 2: architect

**目的**: 受入条件を満たすモジュール配置・関数 I/F・pydantic スキーマ・データフローを設計する。

呼び出し:
- Agent tool で `subagent_type: python-architect`
- 渡す引数: `task_description`, `criteria[]`

検証:
- 8 セクション（`Result` / `モジュール配置` / `I/F 仕様` / `pydantic スキーマ` / `データフロー` / `既存資産再利用` / `依存追加` / `テスト戦略方針`）の見出しがすべて存在すること（`references/contracts.md` の architect セクションを参照）
- `## I/F 仕様` に型ヒント付き Python シグネチャが含まれていること（test-author がテストを書ける粒度）
- 受入条件カバレッジは Phase 3 の test-author 出力 `criteria[].id` set equality で担保するため、ここで AC-N 逐語の grep チェックは行わない

**ユーザゲート 2**: design_summary（モジュール配置・新規 I/F・新規モード追加の有無・既存資産再利用箇所）を提示し、「進む / 修正指示 / 中止」を確認。

### Phase 3: test-author

**目的**: architect 設計に対して pytest を書き、`uv run pytest` で受入条件単位の状態（red / preexisting-green）を確定する。

呼び出し:
- Agent tool で `subagent_type: python-test-author`
- 渡す引数: `criteria[]`, `design_summary`

検証:
- 出力 `criteria[]` の id 集合が requirements 出力と **set equality**（差分があれば即停止）
- 各 criterion が `red` または `preexisting-green` のいずれかに分類されている
- `preexisting-green` は 4 フィールド（passed_test / pre_edit_pytest_evidence / post_edit_pytest_evidence / assertion_evidence）すべて非空

`generated_files[]` に test-author が編集した tests/ 配下のファイルを追記する。

### Phase 4: implementer

**目的**: test-author が red にした受入条件のテストを green にする最小実装を `src/nova_parser/` に書く。

呼び出し:
- Agent tool で `subagent_type: python-implementer`
- 渡す引数: `design_summary`, test-author 出力（モック対象 / fixture / green 化対象テスト一覧 / 申し送り）, red 状態の criteria id リスト

検証:
- pytest 該当ファイル全 green
- `uv run task ruff` pass
- 結果が `blocked` なら orchestrator は実装ループ判定（後述「失敗パターン」へ）

`generated_files[]` に implementer の変更ファイルを追記する。

### Phase 5: reviewer

**目的**: ここまでの全変更を read-only でレビューし、High 指摘の有無で `approved` か `changes-requested` を返す。

呼び出し:
- Agent tool で `subagent_type: python-reviewer`
- 渡す引数: `review_mode`, `base_ref`, `generated_files[]`, `criteria[]`, `allowlist`（既定値はエージェント側で設定済み、特殊事情があるときのみ override）

検証:
- `result` が enum
- `findings[].owner` が `implementation|test|design|requirement` enum
- `files_read[]` が `generated_files[]` をすべて含む（不足は契約違反）

**結果分岐**:
- `result: approved` → ユーザゲート 3 へ
- `result: changes-requested` → owner ベース差し戻しへ（次節）

## ユーザゲート（ハイブリッド・3 ゲート）

各ゲートでは「進む / 修正指示 / 中止」をユーザに確認する。確認方法は AskUserQuestion か明示的な質問テキストで統一する。

| ゲート | タイミング | 提示内容 |
|--------|----------|---------|
| Gate 1 | requirements 完了直後 | criteria[] のチェックリスト + 残課題 |
| Gate 2 | architect 完了直後 | モジュール配置・新規 I/F・新規モードの有無・既存資産再利用箇所 |
| Gate 3 | reviewer `approved` 直後 | 受入条件 ↔ 実装 ↔ テスト 対応表 + `git status` |

中間フェーズ（test-author / implementer / reviewer 完了時）は基本自動進行。ただし契約違反や差し戻し上限到達時は別途ユーザに引き渡す。

## owner ベース差し戻し

reviewer が `changes-requested` を返したとき、High 指摘のみを `owner` ごとに集約して該当エージェントに再呼び出しする。詳細アルゴリズムと優先順位は [references/routing.md](references/routing.md) を参照。

要点:

- High 指摘のみ差し戻し対象（Medium / Low はユーザに表示するだけで自動ループの引き金にしない）
- 1 回の差し戻しで複数 owner が出た場合は **上流から順に解決**: requirement → design → test → implementation
- 差し戻し後は該当フェーズから先（architect 以降 or test-author 以降など）を再実行する
- `loop_count_by_owner` をインクリメント。**同一 owner で 3 回ループ** したら自動進行を停止し、ユーザに raw findings を提示

## fail-closed 契約検証

各エージェント出力の JSON ブロックは `references/contracts.md` の schema に厳密一致する必要がある。違反を検出した場合の挙動:

1. orchestrator は **暗黙の補完を行わない**
2. 該当フェーズの raw 出力をユーザに提示し、エージェント側のバグか入力指示の不備かをユーザに判断させる
3. ユーザの明示指示なしに次フェーズへ進まない

検証対象の主要フィールド:

- `requirements`: `criteria[].id` (AC-N 形式), `criteria[].category` (enum), `change_log[]`
- `test-author`: `criteria[].id` (requirements との set equality), `criteria[].status` (enum), `preexisting_green_evidence` 4 フィールド非空
- `reviewer`: `result` (enum), `findings[].owner` (enum), `findings[].owner_reason` (非空), `files_read[]` ⊇ `generated_files[]`

JSON ブロック抽出ルール: 出力テキストから ```json ... ``` フェンスを正規表現で抽出。エージェントごとに採用ルールを変える:

- **`python-reviewer`**: 出力末尾の **最後の 2 ブロック** を採用する（順に `files_read` と `findings`）。順序は reviewer 契約で固定。両方とも必須なので片方欠落は契約違反として停止
- **その他のエージェント**（`python-requirements` / `python-test-author` 等）: 最後の **1 ブロック** を採用（人間向け説明 → 機械可読を最後に置く規約）

`files_read` ブロックを誤って捨てると `files_read[] ⊇ generated_files[]` 検証が無効化されるため、reviewer の例外規定は **必ず守る**。

## 完了報告（commit はしない）

reviewer `approved` かつユーザゲート 3 通過後の最終アクション:

1. **受入条件対応表** を表示

   | AC ID | description | 実装ファイル | テスト | reviewer 評価 |
   |-------|-------------|------------|-------|-------------|
   | AC-1  | ... | src/nova_parser/foo.py:42 | tests/test_foo.py::test_bar | ✓ |

2. **変更サマリ**: `git status --short` を提示

3. **commit は orchestrator では実行しない**。ユーザに対して以下を案内:

   - 「commit は本スキルでは実行しません。`/git-commit` または `/commit-detailed` で commit メッセージを作成・実行してください」
   - `git add` も orchestrator はしない（ユーザの commit 戦略を尊重）

4. **ユーザに Medium / Low の reviewer findings** が残っていれば一覧で提示（任意対応）

## 失敗パターンと回復

| パターン | 検出条件 | 回復手順 |
|---------|---------|---------|
| implementer が `blocked` 返却 | 実装出力 `Result: blocked` | 同一 owner=implementation を 3 回までリトライ。理由が「設計と前提が合わない」なら architect に差し戻し |
| 同一 owner ループ上限到達 | `loop_count_by_owner[X] >= 3` | 自動進行停止、ユーザに raw findings + 履歴提示、次の判断を仰ぐ |
| reviewer が空 diff で `changes-requested` | `files_read[]` が空 / `findings` に「変更が検出できません」 | `generated_files[]` の妥当性を再確認 → review_mode / base_ref を見直して再呼び出し（最大 1 回） |
| 契約違反（JSON 不正） | 必須フィールド欠落 / enum 違反 | 即停止、raw 出力をユーザに提示。ユーザ指示があれば該当エージェントを再呼び出し |
| Phase 跨ぎループ | requirement → design → requirement のような循環 | 2 周目に入った時点で停止、ユーザに「タスクを再定義する必要あり」と提示 |

## 禁止事項

- **commit / push を一切実行しない**（変更概要の提示のみ）
- 5 サブエージェント以外を勝手に呼び出さない（`commit-detailed` などへの自動委譲も禁止、ユーザ指示が必要）
- フェーズ順序を入れ替えない（test-author 前に implementer を呼ぶ等）
- 差し戻しループを無制限に回さない（同一 owner 3 回上限）
- ユーザゲート（Gate 1 / 2 / 3）をスキップしない
- 各エージェントの出力契約に違反した出力を「だいたい合ってる」と扱って次フェーズに進めない

## 参考

- [references/routing.md](references/routing.md) — owner ベース差し戻しの詳細アルゴリズム
- [references/contracts.md](references/contracts.md) — 5 エージェントの出力 JSON schema 一覧
- `.claude/agents/python-*.md` — 各サブエージェントの完全な仕様（出力契約の正本）
