# 5 サブエージェント出力契約サマリ

orchestrator が parse する JSON フィールドと validation rule を一覧化。**正本は各 `.claude/agents/python-*.md`**。本ファイルは parse 対象の早見表。

## 共通: JSON ブロック抽出

各エージェントの出力には人間向け Markdown と機械可読 JSON が混在する。orchestrator は出力テキストから ```` ```json ... ``` ```` フェンスを正規表現で抽出し、複数あれば **最後のもの** を採用する（agent 規約: 人間向け説明 → 機械可読を最後に置く）。

JSON parse 失敗・必須フィールド欠落・enum 違反は **すべて契約違反** で fail-closed。

---

## 1. python-requirements

### 必須出力 JSON

```json
{
  "criteria": [
    {
      "id": "AC-1",
      "description": "<観測可能な受入条件文言>",
      "category": "functional|nonfunctional|error_handling"
    }
  ],
  "change_log": [
    {"action": "kept|added|removed|description_updated", "id": "AC-1", "note": "<任意>"}
  ]
}
```

### Validation

- `criteria` 配列が空でないこと（タスクから受入条件を 1 件も抽出できないのは契約違反）
- 各 `criteria[].id` が `^AC-\d+$` 正規表現にマッチ
- `criteria[].id` 重複禁止
- 各 `criteria[].description` が非空
- 各 `criteria[].category` が enum 値
- 再呼び出し時: prior_criteria の active な ID は `change_log` に必ず登場すること
- 再呼び出し時: 削除された ID は `change_log` に `removed` で記録（`criteria` 配列からは消える）

### orchestrator 側の責務

- 初回は `prior_criteria` 引数を渡さない（または空配列）
- 再呼び出し時は前回の `criteria[]` JSON をそのまま `prior_criteria` として渡す
- ID 衝突や勝手な再採番（kept なのに ID が変わっている等）を検出したら停止

---

## 2. python-architect

### 必須出力（人間向け Markdown）

architect は機械可読 JSON 契約は持たない。正本は `.claude/agents/python-architect.md` の `## 出力コントラクト` セクション。本ファイルは早見表。

architect は以下の見出しを **この見出し名のまま** 出力する:

- `## Result`（`設計完了` または `要追加情報`）
- `## モジュール配置`（新規 / 追記ファイルパス）
- `## I/F 仕様`（型ヒント付き Python シグネチャ + 例外 + docstring サマリ）
- `## pydantic スキーマ`（`BaseModel` 派生クラス定義）
- `## データフロー`（番号付き手順）
- `## 既存資産再利用`（`file:line` — 用途）
- `## 依存追加`（`なし` または `uv add <pkg>` ＋理由）
- `## テスト戦略方針`（fixture / 異常系 / 外部 API モック方針）

### Validation

- 出力テキストが上記 8 セクション（`Result` / `モジュール配置` / `I/F 仕様` / `pydantic スキーマ` / `データフロー` / `既存資産再利用` / `依存追加` / `テスト戦略方針`）をすべて含むこと。検出は `## I/F 仕様` のような **正本の見出し名そのもの** で正規表現マッチする
- `## I/F 仕様` の中身に型ヒント付き Python シグネチャが含まれていること（test-author がテストを書ける粒度）
- `## 依存追加` セクションが存在すること（`なし` でも可）

**AC-N 逐語要求は撤廃**（架空の制約だった）。受入条件カバレッジは architect の自然文判断に委ねる。orchestrator は AC-N の grep 検出失敗だけで契約違反停止しない。受入条件カバレッジの最終チェックは Phase 3 の test-author で `criteria[]` の set equality として担保される。

### orchestrator 側の責務

- 出力テキストをそのまま `design_summary` として保持し、test-author / implementer に転送
- 不足セクションがあれば差し戻し

---

## 3. python-test-author

### 必須出力 JSON

```json
{
  "criteria": [
    {
      "id": "AC-1",
      "description": "<requirements の description を echo>",
      "status": "red|preexisting-green",
      "red_tests": [
        {"test": "test_<name>", "fail_reason": "NotImplementedError|AttributeError|ImportError|期待値ミスマッチ|..."}
      ],
      "preexisting_green_evidence": {
        "passed_test": "test_<name>",
        "pre_edit_pytest_evidence": "tests/test_<feature>.py::test_<name> PASSED ...",
        "post_edit_pytest_evidence": "tests/test_<feature>.py::test_<name> PASSED ...",
        "assertion_evidence": "tests/test_<feature>.py:42 assert foo(...) == expected"
      },
      "supplementary_evidence": ["src/nova_parser/<file>:<line>"]
    }
  ]
}
```

### Validation

- `criteria[].id` の集合が requirements 出力の `criteria[].id` 集合と **set equality**（差分 0）
- 各 criterion の `status` が enum
- `status == "red"` のとき: `red_tests[]` が 1 件以上、各要素の `fail_reason` が非空
- `status == "preexisting-green"` のとき: `preexisting_green_evidence` の 4 フィールド（passed_test / pre_edit_pytest_evidence / post_edit_pytest_evidence / assertion_evidence）すべて非空
- `passed_test` は **test-author 編集前から存在していた** テストであること（新規追加 test を挙げるのは契約違反 — orchestrator は `git diff --stat tests/` と突き合わせて検出可能）

### orchestrator 側の責務

- status=red の test 関数名を集約し、implementer への申し送りに含める
- status=preexisting-green の criterion は implementer の green 化対象から除外
- test-author の出力に新規追加された tests/ ファイルを `generated_files[]` に追加

---

## 4. python-implementer

### 必須出力（人間向け Markdown）

implementer は機械可読 JSON 契約は持たない。以下のセクションを必ず含むテキスト:

- `## Result`: `green` または `blocked`
- `## 変更ファイル`: 新規 / 修正したファイルパス一覧
- `## pytest 結果`: `uv run pytest` の `passed` / `failed` / `skipped` 件数
- `## ruff 結果`: `uv run task ruff` の結果

### Validation

- `Result: green` の場合: pytest 結果に `failed` が 0 件、ruff が pass
- `Result: blocked` の場合: 差し戻し理由が記載されていること
- 変更ファイルがすべて `src/nova_parser/` 配下（tests/ を編集していたら契約違反）

### orchestrator 側の責務

- `green` なら次の reviewer フェーズへ
- `blocked` なら理由を見て差し戻し先を判定（実装側か設計側か）
- 変更ファイルを `generated_files[]` に追加

---

## 5. python-reviewer

### 必須出力 JSON（2 ブロック）

#### ブロック A: files_read

```json
{
  "review_mode": "worktree|commit|mixed",
  "base_ref": "main",
  "files_read": [
    {"path": "<relative path>", "source": "unstaged|staged|untracked|base_ref_diff", "method": "full_read|diff|skipped"},
    {"path": "<path>", "source": "untracked", "method": "skipped", "skip_reason": "binary|size_exceeded|security_denylist"}
  ]
}
```

#### ブロック B: findings

```json
{
  "result": "approved|changes-requested",
  "findings": [
    {
      "severity": "high|medium|low",
      "file": "<relative path>",
      "line": 42,
      "owner": "implementation|test|design|requirement",
      "owner_reason": "<1 行根拠>",
      "evidence": "<指摘の根拠>",
      "recommendation": "<推奨修正>"
    }
  ],
  "good_points": [
    {"file": "<relative path>", "line": 10, "note": "..."}
  ]
}
```

### Validation

- `result` が enum
- `findings[].severity` が `high|medium|low` enum
- `findings[].owner` が `implementation|test|design|requirement` enum（**他値不可**）
- `findings[].owner_reason` が非空
- `files_read[]` が orchestrator の渡した `generated_files[]` を **すべて含む**（`method=skipped` は許容、ただし含まれていなければならない）
- `result == "approved"` のとき: `findings[].severity == "high"` が 0 件であること（high が残っているのに approved は契約違反）
- `result == "changes-requested"` のとき: `findings[].severity == "high"` が 1 件以上であること（high 0 件で changes-requested も契約違反）

### orchestrator 側の責務

- ブロック A と B の 2 つの JSON フェンスをそれぞれ抽出（**最後の 2 つ** を採用）
- `files_read[]` ⊇ `generated_files[]` チェック
- High 指摘を owner ごとに集約 → `routing.md` のアルゴリズムへ
- skip された files（binary / size / denylist）は Medium 指摘として扱う（ループの引き金にはしない、ただしユーザに表示）

---

## 共通の差し戻し条件

以下のいずれかに該当した場合、orchestrator は **暗黙の補完を行わず** 該当エージェントを再呼び出しする（または契約違反としてユーザに raw 出力を提示）:

- 必須 JSON ブロックが見つからない
- 必須フィールドの欠落
- enum 違反
- ID set equality 違反（test-author / requirements 間）
- `files_read[]` ⊇ `generated_files[]` 違反（reviewer）
- `result` と `findings` の整合性違反（reviewer）

差し戻し回数のカウントは `loop_count_by_owner` を使う。同一 owner 3 回でユーザに引き渡し。
