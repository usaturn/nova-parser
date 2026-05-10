# Owner ベース差し戻しルーティング

reviewer が `result: changes-requested` を返したときに、orchestrator が High 指摘を `owner` enum で集約し、該当サブエージェントに再呼び出しするためのアルゴリズム詳細。

## 入力

reviewer の出力 JSON:

```json
{
  "result": "changes-requested",
  "findings": [
    {"severity": "high", "file": "...", "line": 42, "owner": "implementation|test|design|requirement", "owner_reason": "...", "evidence": "...", "recommendation": "..."}
  ]
}
```

## ステップ

### 1. High 指摘を抽出

```
high_findings = [f for f in findings if f.severity == "high"]
```

Medium / Low は差し戻しの引き金にしない（ユーザへの参考表示のみ）。`high_findings` が空なら矛盾なので契約違反として停止。

### 2. owner ごとにグルーピング

```
groups = {
    "requirement":    [f for f in high_findings if f.owner == "requirement"],
    "design":         [f for f in high_findings if f.owner == "design"],
    "test":           [f for f in high_findings if f.owner == "test"],
    "implementation": [f for f in high_findings if f.owner == "implementation"],
}
```

### 3. 上流優先で 1 グループずつ処理

優先順位（上から実行）:

1. `requirement` → python-requirements に差し戻し（その後 architect 以降を再実行）
2. `design` → python-architect に差し戻し（その後 test-author 以降を再実行）
3. `test` → python-test-author に差し戻し（その後 implementer 以降を再実行）
4. `implementation` → python-implementer に差し戻し（その後 reviewer のみ再実行）

**1 回の差し戻しで処理するのは最上流のグループ 1 つだけ**。下流の指摘は次の reviewer サイクルで再評価する（実装直してテスト直して下流の指摘が自然消滅することがあるため）。

### 4. 差し戻しコンテキストの組み立て

各エージェントへの再呼び出しプロンプトには以下を含める:

#### python-requirements への差し戻し
```
タスクは継続中。以下の reviewer High 指摘により受入条件を見直してください。

## 既存 criteria（prior_criteria として渡す）
{criteria[] JSON}

## 見直し対象 High 指摘
{high_findings の owner=requirement のみ列挙}

ID 安定性ルールに従って criteria を更新し、change_log に kept/added/removed/description_updated を記録してください。
```

#### python-architect への差し戻し
```
設計を以下の reviewer High 指摘で見直してください。

## 受入条件（変更なし）
{criteria[] JSON}

## 見直し対象 High 指摘
{owner=design の High 指摘}

## 前回設計サマリ
{design_summary}

修正後の設計サマリを返してください。既存 I/F を変える場合は破壊的変更の有無を明記してください。
```

#### python-test-author への差し戻し
```
以下の reviewer High 指摘に対応するテストの追加 / 修正を行ってください。
src/ は触らないこと（実装は implementer が担当）。

## 受入条件
{criteria[] JSON}

## 見直し対象 High 指摘
{owner=test の High 指摘}

## 前回 test-author 出力
{test-author の前回 criteria mapping 全文}

red 確認を再実行し、status=red の test を red のまま、preexisting-green は証跡を維持してください。
```

#### python-implementer への差し戻し
```
以下の reviewer High 指摘を解消する最小修正を src/nova_parser/ に対して行ってください。
tests/ は触らないこと。

## 見直し対象 High 指摘
{owner=implementation の High 指摘}

## 前回テスト一覧（green を保つこと）
{green 化対象テスト全件}

`uv run pytest` 全 green を再確認してから返してください。`uv run task ruff` も pass させること。
```

### 5. ループカウンタ更新

```
loop_count_by_owner[selected_owner] += 1
if loop_count_by_owner[selected_owner] >= 3:
    停止してユーザに引き渡す
```

### 6. 該当フェーズから再実行

差し戻し owner に応じて、以下のフェーズから順に再実行する:

| 差し戻し owner | 再実行範囲 |
|---------------|----------|
| requirement   | requirements → architect → test-author → implementer → reviewer |
| design        | architect → test-author → implementer → reviewer |
| test          | test-author → implementer → reviewer |
| implementation | implementer → reviewer |

requirements / architect が再実行されたら、ユーザゲート 1 / 2 も **再度発動** する（criteria や設計が変わるため）。

## エッジケース

### High 指摘が 0 件なのに `changes-requested`
契約違反。reviewer 出力を raw でユーザに提示して停止。

### owner が enum 外の値
契約違反。raw 出力提示して停止。

### 差し戻し中にユーザが「中止」を選択
全 state を破棄し、現状の `git status` を提示してスキル終了。orchestrator は何も commit / revert しない。

### 同一 owner で 3 回ループ後
該当 owner の履歴（過去 3 回の指摘 + 各回の修正概要）をユーザに提示し、以下を選ばせる:

1. ユーザ自身が手動で問題を解決し、orchestrator に「解決した、reviewer から再開して」と指示
2. タスクを取り下げて全変更を一度棚上げ（`git stash` 推奨だが orchestrator は実行しない）
3. 上流フェーズから設計を見直す（requirements / architect に差し戻し、ループカウンタリセット）

### Phase 跨ぎループ
`requirement → design → requirement` のような循環が 2 周目に入ったら自動停止。タスク自体の再定義が必要なシグナル。
