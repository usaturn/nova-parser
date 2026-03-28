# Task Type Prompts

Agent Team 作成時に、タスク種別に応じて teammate への初期指示を組み立てるためのテンプレート集。

## Feature（機能追加）

```text
この機能追加を Agent Team で進めて。
requirements 担当は、要求、受入条件、既存モード互換性への影響、ユーザ確認事項を先にまとめて。
architecture 担当は、変更対象、責務分割、例外処理、テスト方針を整理して。
implementation 担当は、承認済み計画だけを実装して。plan approval は必須。
review and docs 担当は、レビュー観点、QA 観点、README / docs/usage.md / 必要な運用文書の更新点を整理して。
lead は teammate が完了する前に自分で実装へ進まないで。
```

## Bugfix（バグ修正）

```text
この不具合の修正を Agent Team で進めて。
requirements 担当は、再現条件、期待挙動、ユーザ確認が必要な曖昧点を整理して。
architecture 担当は、原因候補、修正方針、回帰リスク、テスト方針を整理して。
implementation 担当は、承認済み方針だけを修正して。plan approval は必須。
review and docs 担当は、回帰確認、未検証事項、必要な文書更新の有無を確認して。
複数の仮説がある場合は、team 内で仮説を競合させてから収束して。
```

## Refactor（リファクタリング）

```text
このリファクタリングを Agent Team で進めて。
requirements 担当は、維持すべき外部挙動、壊してはいけない互換性、確認事項を明文化して。
architecture 担当は、責務境界、段階的な移行手順、影響範囲、テスト戦略を整理して。
implementation 担当は、承認済みの段階的計画だけを実装して。plan approval は必須。
review and docs 担当は、設計の崩れ、テスト不足、保守者向け文書の更新点を確認して。
同一ファイルの競合を避けるため、task を file ownership ベースで分けて。
```

## Docs（ドキュメント更新）

```text
この変更内容に対応する文書更新を Agent Team で進めて。
requirements 担当は、利用者影響と保守者影響を整理して。
architecture 担当は、どの文書に何を反映すべきか、実装との整合観点を整理して。
implementation 担当は、必要なコード差分がある場合だけ対応して。plan approval は必須。
review and docs 担当は、README、docs/usage.md、運用文書の更新を行い、実装との齟齬がないかを確認して。
lead は最後に、文書と実装の整合を確認してから shutdown と cleanup を実行して。
```
