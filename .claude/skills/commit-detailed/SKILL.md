---
name: commit-detailed
description: ステージング済みファイルを、カレントの feature ブランチに詳細なコミットメッセージ (Conventional Commits subject + 背景/変更点/影響/テストを含む body) でコミットするスキル。main ブランチ上では何もせず中断する。main 以外では対応する Open PR の有無を確認し、PR が無い場合はユーザに確認してから commit する。ユーザが「詳細メッセージで commit して」「staged を詳しくコミット」「/commit-detailed」等で依頼したときにトリガーする。git add は行わない。実行は専用の Sonnet サブエージェント `commit-detailed` に委譲する。
---

# Commit Detailed

ステージング済みのファイルを **カレントの feature ブランチに**、**詳細メッセージ付き** で commit するスキル。main ブランチ上では何もしない。実際のコミットは Sonnet 駆動のサブエージェント `commit-detailed` に Task で委譲する。

## 前提確認

Task 呼び出し前に、親スレッドで以下を順に Bash で確認する。

1. `.claude/agents/commit-detailed.md` が存在する。無ければユーザに報告して中断。
2. `git rev-parse --abbrev-ref HEAD` を確認する。
   - 結果が `main` の場合は **何もせず中断** し、「main 上のため中断しました。先に feature ブランチを切ってから再実行してください」とユーザに報告する。勝手にブランチを作成・切替しない。
3. `git diff --staged --name-only` に少なくとも 1 ファイル含まれる。空なら「staged なし」と報告して中断。
4. 対応する Open PR の有無を確認する。

   ```bash
   branch="$(git rev-parse --abbrev-ref HEAD)"
   gh pr list --head "$branch" --state open --json number --jq 'length'
   ```

   - 出力が `1` 以上（PR あり）→ そのまま Task 呼び出し（次節）へ進む。
   - 出力が `0`（PR なし）→ `AskUserQuestion` で「このブランチに対応する Open PR がありません。PR 無しのままこのブランチに commit しますか?」を確認する。
     - Yes → Task 呼び出しへ進む。
     - No → 「PR 未作成のため中断しました」と報告して中断する。

## ワークフロー

### 1. Task 呼び出し

`commit-detailed` サブエージェントを 1 回だけ Task で呼ぶ。プロンプトは最小限でよい:

```
staged 済みの変更を、カレントの feature ブランチに詳細メッセージで commit してください。
ユーザ依頼: <原文>
追加コンテキスト（あれば）: <ユーザが口頭で付けた背景、例: 「今回は X 対応」>
```

- ユーザが原文で指定した **追加コンテキスト**（背景、Issue 番号、関連 PR、テスト結果等）があれば、原文のまま転送する
- サブエージェント側が staged diff を自前で読み、メッセージを組み立てるので、スキルでは diff を事前に要約しない
- コミットメッセージ案を **親スレッドで事前に作ってサブエージェントに渡さない**（Sonnet に組ませる設計のため）

### 2. 結果の扱い

- サブエージェントの stdout をそのままユーザに表示する（要約しない）
- サブエージェントが中断理由（branch が main / staged 空 / 機密ファイル混入）を返した場合は、その理由を明示してユーザに次アクションを確認する
- commit 成功後、push が必要かどうかは **確認せず実行しない**（push はこのスキルの責務外）

## 使い分けの早見表

| 依頼の形 | 使うスキル |
|---|---|
| 「staged を詳しくコミット」（feature ブランチ上） | 本スキル (`commit-detailed`) |
| 「短い conventional commit で」 | `git-commit` スキル |
| 「まだ add してない。全部コミットまで通して」 | `git-commit` スキル（add 含む） |
| 「push まで通して」 | 本スキルで commit → 別途ユーザに push 確認 |

## やらないこと

- サブエージェントを介さず親スレッドで直接 `git commit` を実行する
- ユーザ確認なしに `git switch`/`git checkout` でブランチを切り替える、または新規作成する
- main ブランチ上で commit する（main では何もしない）
- `git add` を実行する（ステージングはユーザ責任）
- `git push` を実行する
- サブエージェントが返したコミットメッセージや結果を要約・再フォーマットする
- `--no-verify` 等で hook を skip するようサブエージェントに依頼する

## 関連スキル

- `git-commit` — 短い Conventional Commits 形式で add から一括で commit する既存スキル。詳細 body が不要な小さな変更向け
