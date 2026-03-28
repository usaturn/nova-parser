---
name: team-init
description: Agent Team の作成を半自動化するスキル。ユーザーが `/team-init` と呼び出した時、または「Agent Team を作って」「チームで進めて」等の指示をした時にトリガーする。標準 4 teammate（requirements, architecture, implementation, review-and-docs）構成で Team を結成し、shared task list で作業を管理する。
---

# Agent Team 初期化

## 前提確認

Team 作成前に以下を確認する。1 つでも満たさなければユーザに報告して中断する。

1. `claude --version` が 2.1.32 以上であること
2. 環境変数 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` が `1` であること
3. split panes を使う場合は `tmux` が利用可能であること（なければ in-process で続行）

## ワークフロー

### 1. タスク種別の特定

ユーザの依頼から以下のいずれかを判定する。判定できない場合はユーザに確認する。

- **feature** — 機能追加
- **bugfix** — バグ修正
- **refactor** — リファクタリング
- **docs** — ドキュメント更新

### 2. 曖昧点の解消

実装に入る前に、要求の曖昧な点・複数解釈がある点をユーザに質問して解像度を上げる。

### 3. Team 作成

TeamCreate で Team を作成する。Team 名はタスク内容から kebab-case で命名する（例: `add-pdf-support`）。

### 4. Teammate のスポーン

以下の 4 teammate を順にスポーンする。各 teammate には役割に応じた spawn prompt を渡す。

| Name | 役割 | mode | コード変更 |
|------|------|------|-----------|
| `requirements` | 要件整理・曖昧点抽出・受入条件定義 | plan | しない |
| `architect` | 設計・変更境界・テスト方針整理 | plan | しない |
| `implementer` | 承認済み範囲の実装 | plan | する |
| `reviewer` | レビュー・QA・文書更新 | plan | 必要に応じて |

spawn prompt の組み立て方:
1. [references/prompts.md](references/prompts.md) からタスク種別に対応するテンプレートを読む
2. テンプレートの該当ロール部分を抽出し、ユーザの具体的なタスク内容を付加する
3. 共通ルール（後述）を末尾に付加する

### 5. Shared Task List の構築

TaskCreate で作業を分解する。以下の原則に従う。

- 依存関係がない task は並列化する
- 依存関係がある task は blockedBy で順序を明示する
- 同じファイルに複数 teammate が触らない単位で切る
- teammate あたり 5-6 task を目安にする
- 各 task に owner（teammate name）を明示する

典型的な task 順序:

```
requirements: 要件整理 → 受入条件定義
                ↓
architect: 設計方針策定 → テスト方針整理
                ↓
implementer: 実装（plan approval 必須）
                ↓
reviewer: コードレビュー → 文書更新
```

### 6. 進捗監視

Lead は以下に徹し、自分で実装を行わない。

- TaskGet / TaskList で進捗を監視する
- 進め方がずれている teammate には SendMessage で修正を指示する
- plan approval が来たら、以下の基準で承認・却下を判断する
  - テスト方針があること
  - 既存挙動との互換性が整理されていること
  - 変更対象ファイルが明確であること
  - 文書更新要否が明記されていること
- 不十分な計画は reject し、修正版を再提出させる

### 7. Shutdown と Cleanup

全 teammate の作業が完了したら、以下を順に実行する。

1. TaskList で完了済み task と未完了 task を確認する
2. 全 teammate に shutdown を指示する（SendMessage）
3. 全 teammate の停止を確認する
4. TeamDelete で team を cleanup する

## 共通ルール（全 teammate の spawn prompt に付加）

```
品質を最優先にし、実装速度は遅くてもよい。
曖昧な要求や複数解釈がある要求は、実装前に必ずユーザへ確認して。
同じファイルを複数 teammate に同時編集させないで。
CLAUDE.md のルールに従うこと。
```
