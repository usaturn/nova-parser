# Claude Code Agent Teams 運用ガイド

`nova-parser` で Claude Code の Agent Teams を使い、Python アプリケーションの開発、機能追加、修正、リファクタリング、および文書更新を高品質重視で進めるための運用ガイドです。

この文書は [Claude Code 公式の Agent Teams ドキュメント](https://code.claude.com/docs/en/agent-teams) を前提にしています。`.claude/agents/` に role ファイルを置く Sub Agents の説明ではありません。

## Agent Teams とは

Agent Teams は、複数の Claude Code セッションを 1 つの team として協調動作させる機能です。

- 1 つのメインセッションが team lead として動く
- teammate はそれぞれ独立した Claude Code セッションとして動く
- team 全体で shared task list を共有する
- teammate 同士が mailbox 経由で直接やりとりできる
- lead から teammate へ task を割り当てたり、teammate が自分で task を claim したりできる

Sub Agents との違いは、teammate が lead 経由でしか報告できない補助 worker ではなく、互いに連携できる独立セッションである点です。

## このリポジトリでの運用方針

- 実装速度より、コード品質、保守性、テスト容易性を優先する
- 曖昧な要求や複数解釈があり得る要求は、実装前に必ずユーザへ確認する
- 計画や設計が必要な変更では、十分に検討してから実装に入る
- コード変更を行う teammate には plan approval を必須にする
- 同じファイルを複数 teammate に同時編集させない
- lead は teammate の結果が揃う前に自分で実装へ流れず、進捗監視と統合に徹する

## 前提

- Claude Code `2.1.32` 以降が必要
- この環境では `claude --version` で `2.1.86` を確認済み
- Agent Teams は実験機能のため、`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` が必要
- split panes を使う場合は `tmux` または iTerm2 が必要
- この環境には `tmux` が入っていないため、split panes を使う場合は先に導入する

## Agent Teams の有効化

このリポジトリでは project settings で Agent Teams を有効化します。

`/.claude/settings.json`

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

補足:

- これは Agent Teams を有効にするための設定であり、Sub Agents の定義ではない
- teammate の表示方式は project settings ではなく、Claude Code の global config や起動方法で制御する

## 表示方式

Agent Teams には 2 つの表示方式があります。

- `in-process`: すべての teammate がメイン端末の中で動く
- `split panes`: teammate ごとに pane を分けて表示する

このリポジトリでは `tmux` による split panes を標準とします。理由は、誰が何をしているかを常時可視化しやすく、lead が teammate を監視・介入しやすいためです。

補足:

- Claude Code の既定値は `auto`
- `auto` は、tmux セッション内なら split panes、それ以外では in-process を使う
- 一時的に in-process を強制したい場合は `claude --teammate-mode in-process` を使う

## 標準の起動手順

### 1. バージョンと前提を確認する

```bash
claude --version
which tmux
```

- `claude --version` で `2.1.32` 以上を確認する
- `which tmux` で `tmux` が見つからない場合は、split panes は使えない

### 2. `tmux` セッションを開始する

```bash
tmux new -s nova-agent-teams
```

既に tmux 内で作業している場合は、そのセッションを使ってよいです。

### 3. リポジトリルートで Claude Code を起動する

```bash
claude
```

補足:

- tmux を使えない環境では `claude --teammate-mode in-process` を使う
- in-process では `Shift+Down` で teammate を切り替え、`Ctrl+T` で task list を開ける

## 標準 Team 設計

標準 Team は 4 teammate を基本とします。3 から 5 teammate が実務上扱いやすいという公式の推奨に合わせ、品質と統合のしやすさのバランスを取ります。

| 役割 | 主な責務 | コード変更 |
|---|---|---|
| Lead | Team 結成、task 分解、進捗監視、plan approval、最終統合 | 原則しない |
| Requirements teammate | 要件整理、曖昧点抽出、受入条件定義 | しない |
| Architecture teammate | 設計、変更境界、例外処理、テスト方針整理 | しない |
| Implementation teammate | 承認済み範囲の実装 | する |
| Review and Docs teammate | レビュー観点、QA 観点、文書更新点整理 | 必要に応じてする |

運用ルール:

- `Implementation teammate` は plan approval を通るまで書き込みに進ませない
- `Review and Docs teammate` がコードを書き換える場合も同様に plan approval を要求する
- file ownership を task 単位で明示し、同一ファイルの競合を避ける
- 5 から 6 task / teammate を目安に、細かすぎず大きすぎない task に分ける

## Team 作成時の共通プロンプト

最初の依頼では、quality gate と役割を明示して team を結成させます。

```text
このリポジトリで Agent Team を作成して。
Sub Agents ではなく、Claude Code の Agent Teams を使うこと。

品質を最優先にし、実装速度は遅くてもよい。
曖昧な要求や複数解釈がある要求は、実装前に必ず私へ確認して。
コードを書く teammate には plan approval を必須にして、十分に検討した計画だけ承認して。
lead は自分で実装を急がず、task 分解、進捗監視、レビュー統合に徹して。
同じファイルを複数 teammate に同時編集させないで。

標準 Team は以下で構成して:
- requirements 担当
- architecture 担当
- implementation 担当
- review and docs 担当

shared task list を使って作業を分解し、task ごとに担当と依存関係を明確にして。
全員の作業が終わったら、shutdown と cleanup まで lead が責任を持って実行して。
```

## 典型タスク別の開始プロンプト

### 機能追加

```text
この機能追加を Agent Team で進めて。
requirements 担当は、要求、受入条件、既存モード互換性への影響、ユーザ確認事項を先にまとめて。
architecture 担当は、変更対象、責務分割、例外処理、テスト方針を整理して。
implementation 担当は、承認済み計画だけを実装して。plan approval は必須。
review and docs 担当は、レビュー観点、QA 観点、README / docs/usage.md / 必要な運用文書の更新点を整理して。
lead は teammate が完了する前に自分で実装へ進まないで。
```

### バグ修正

```text
この不具合の修正を Agent Team で進めて。
requirements 担当は、再現条件、期待挙動、ユーザ確認が必要な曖昧点を整理して。
architecture 担当は、原因候補、修正方針、回帰リスク、テスト方針を整理して。
implementation 担当は、承認済み方針だけを修正して。plan approval は必須。
review and docs 担当は、回帰確認、未検証事項、必要な文書更新の有無を確認して。
複数の仮説がある場合は、team 内で仮説を競合させてから収束して。
```

### リファクタリング

```text
このリファクタリングを Agent Team で進めて。
requirements 担当は、維持すべき外部挙動、壊してはいけない互換性、確認事項を明文化して。
architecture 担当は、責務境界、段階的な移行手順、影響範囲、テスト戦略を整理して。
implementation 担当は、承認済みの段階的計画だけを実装して。plan approval は必須。
review and docs 担当は、設計の崩れ、テスト不足、保守者向け文書の更新点を確認して。
同一ファイルの競合を避けるため、task を file ownership ベースで分けて。
```

### ドキュメント更新

```text
この変更内容に対応する文書更新を Agent Team で進めて。
requirements 担当は、利用者影響と保守者影響を整理して。
architecture 担当は、どの文書に何を反映すべきか、実装との整合観点を整理して。
implementation 担当は、必要なコード差分がある場合だけ対応して。plan approval は必須。
review and docs 担当は、README、docs/usage.md、運用文書の更新を行い、実装との齟齬がないかを確認して。
lead は最後に、文書と実装の整合を確認してから shutdown と cleanup を実行して。
```

## Team の回し方

### task の作り方

- 依存関係がない task は並列化する
- 依存関係がある task は blocked にならないよう順番を切る
- 同じファイルに複数 teammate が触らない単位で切る
- 調査、設計、実装、レビュー、文書更新の deliverable を task ごとに明確にする

### plan approval の運用

- コード変更が入る task では、lead に「plan approval を必須にする」と最初から指示する
- 承認基準には、少なくとも以下を含める
  - テスト方針があること
  - 既存挙動との互換性が整理されていること
  - 変更対象ファイルが明確であること
  - 文書更新要否が明記されていること
- 不十分な計画は reject し、修正版を再提出させる

### teammate への直接介入

- 進め方がずれているときは、lead から teammate へ直接 message して修正する
- 調査が止まった teammate には、追加指示を出すか、必要なら別 teammate を立て直す
- broadcast は token 消費が増えるため、多用しない

### shutdown と cleanup

作業が終わったら、必ず lead に順番に実行させます。

1. 完了済み task と未完了 task を確認する
2. 稼働中の teammate を shutdown させる
3. 全 teammate の停止を確認する
4. `Clean up the team` を lead に実行させる

重要:

- cleanup は teammate ではなく lead に実行させる
- active teammate が残っていると cleanup は失敗する
- orphaned tmux session が残った場合は `tmux ls` と `tmux kill-session -t <session-name>` で片付ける

## 品質ルール

- まず research と review から入り、いきなり並列実装を始めない
- lead は teammate の完了を待ってから統合に入る
- token 消費は team サイズに比例して増えるため、逐次処理で十分な作業には team を使わない
- same-file edit が避けられない作業では、Agent Teams ではなく単独セッションで進める
- TeammateIdle / TaskCreated / TaskCompleted hooks を使える環境では quality gate を追加する

## 既知の制約

公式 docs で案内されている主な制約を、このリポジトリでも前提にします。

- Agent Teams は experimental 機能である
- in-process teammate は session resumption が弱い
- task 完了状態が遅延することがある
- teammate shutdown は現在の tool call 完了まで待つことがある
- 1 session で扱える team は 1 つだけ
- nested team は作れない
- split panes は tmux または iTerm2 が必要
- teammate は lead の permission mode を引き継いで起動する

## 参考

- 公式 Agent Teams docs: <https://code.claude.com/docs/en/agent-teams>
