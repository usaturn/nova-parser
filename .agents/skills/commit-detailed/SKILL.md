---
name: commit-detailed
description: Use when ユーザーが、すでに staged の変更だけを detailed または Conventional Commits 形式のメッセージで commit するよう依頼する場合。ファイルの stage、push、PR 作成、rebase、amend も同時に求める依頼では使用しない。
---

# Commit Detailed

## 概要

Git index にすでに登録されている変更だけを、ブランチと GitHub PR の安全条件に従って commit する。ブランチ名と commit message の記述は、すべて staged diff だけから導出する。

## ワークフロー

### 1. HEAD の状態を判定する

最初に次の read-only コマンドを実行する。

```bash
git rev-parse --is-inside-work-tree
git symbolic-ref --quiet --short HEAD
```

ほかの操作より先に結果を判定する。

- 最初のコマンドが `true` を出力しない: 現在のディレクトリが Git worktree ではないと報告して終了する。
- 出力が `main`: `main` は保護対象であると報告して終了する。GitHub への問い合わせ、staged diff の調査、ブランチ作成、commit は行わない。
- 出力が別のブランチ: **main 以外の通常ブランチ**へ進む。
- HEAD が detached のため終了コードが非0: **detached HEAD**へ進む。
- その他のエラー: エラーを報告して終了する。

### 2A. main 以外の通常ブランチ

index が空でないことを確認する。

```bash
git diff --staged --name-only
```

出力がなければ、staged changes がないと報告して終了する。`git add` は実行しない。

staged file 名を**機密ファイル**の規則と照合する。疑わしい名前があれば、GitHub への問い合わせや commit より前に終了する。

現在のブランチの upstream と、その remote repository の GitHub identity を確定する。

```bash
current_branch="$(git symbolic-ref --quiet --short HEAD)"
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
upstream_remote="$(git config --get "branch.$current_branch.remote")"
remote_url="$(git remote get-url "$upstream_remote")"
gh repo view "$remote_url" --json nameWithOwner --jq .nameWithOwner
```

upstream がない、`branch.<current_branch>.remote` が空または取得不能、remote 名から URL を取得できない、`gh repo view` が非0、または `owner/name` が空の場合は repository identity を確認できないため終了する。

現在のブランチを head とし、同じ repository identity を持つ open PR が1件以上あることを確認する。

```bash
gh pr list --head "$current_branch" --state open --limit 1000 \
  --json number,isDraft,url,headRefName,headRepository,headRepositoryOwner,isCrossRepository
```

結果は1件で打ち切らず、返されたすべての要素を次のように厳密に解釈する。

- 終了コードが非0: PR の状態は不明である。エラーを報告して終了する。
- JSON の解析に失敗した場合: PR の状態は不明である。エラーを報告して終了する。
- 各 PR について `headRefName` が現在のブランチと一致し、`headRepositoryOwner.login/headRepository.name` が upstream remote の `owner/name` と一致するか確認する。
- `headRepository` または `headRepositoryOwner` が欠ける要素は一致と見なさない。`isCrossRepository` だけで identity を推測しない。
- branch 名と repository identity の両方が一致する open PR が1件もない: commit を作成しなかったと報告して終了する。同名 branch の fork PR だけがある場合もここで停止する。
- 両方が一致する open PR が1件以上ある: 条件を満たす。draft も open であるため許可する。

closed または merged PR は条件を満たさない。

### 2B. detached HEAD

fetch せずに commit を解決して比較する。

```bash
git rev-parse --verify 'HEAD^{commit}'
git rev-parse --verify 'refs/remotes/origin/main^{commit}'
```

`origin/main` を解決できない場合、または2つの hash が異なる場合は、理由を報告して終了する。

ブランチ作成前に staged file 名を確認し、**機密ファイル**の規則と照合する。

```bash
git diff --staged --name-only
```

staged changes がない場合、または疑わしいファイルが staged されている場合は、ブランチを作成せず終了する。

**許可された変更範囲を調査する**の手順で staged diff を確認し、次の形式の名前を生成する。

```text
<type>/<lowercase-kebab-case-summary>
```

`<type>` は次の表から選ぶ。

| staged change | ブランチ種別 | commit type |
|---|---|---|
| ユーザー向け機能 | `feature` | `feat` |
| 不具合修正 | `fix` | `fix` |
| ドキュメントのみ | `docs` | `docs` |
| 内部構造の整理 | `refactor` | `refactor` |
| テストのみ | `test` | `test` |
| フォーマットのみ | `chore` | `style` |
| 保守作業 | `chore` | `chore` |
| CI 設定 | `ci` | `ci` |
| build system | `build` | `build` |
| performance 改善 | `perf` | `perf` |

staged diff の主要目的を表す短い英語要約を使う。候補を検証し、local と `origin` の両方で同名 ref を確認する。

```bash
git check-ref-format --branch "$candidate"
git show-ref --verify --quiet "refs/heads/$candidate"
git show-ref --verify --quiet "refs/remotes/origin/$candidate"
```

`git check-ref-format` が非0の場合は候補を再生成するか停止し、ブランチ作成へ進まない。

local と `origin` の各 `git show-ref --verify --quiet` は終了コードを個別に解釈する。

- 終了コード0: ref が存在し、候補は衝突している。
- 終了コード1: 指定した ref は存在しない。
- その他の終了コード: ref の有無を判定できないため停止する。

どちらかの ref が存在する場合は `-2`、次は `-3` と連番を付け、未使用名になるまで両方を再確認する。両コマンドが終了コード1の場合だけ、その候補でブランチ作成へ進む。

その local branch だけを作成する。

```bash
git switch -c "$candidate"
```

ブランチ作成に失敗した場合は、エラーを報告して終了する。既存 ref を削除または上書きしない。

### 3. 許可された変更範囲を調査する

staged state だけを使う。

```bash
git diff --staged --name-only
git diff --staged --stat
git diff --staged
```

規則:

- ブランチ名、subject、body は、この出力だけを根拠にする。
- message を補う目的で unstaged / untracked file の内容を読まない。
- staged diff の主要目的から commit type を選ぶ。

### 4. 機密ファイル

staged path が次のいずれかに該当する場合は終了し、index の確認をユーザーへ依頼する。

- `.env`
- `.env.*`
- `*.pem`
- `*.key`
- `*.pfx`
- `id_rsa*`
- ファイル名に `secret`、`token`、`credential` のいずれかを含む

detached HEAD の分岐では、この確認より前にブランチを作成しない。

### 5. commit message を作成する

次の構造を使う。

```text
<type>: <short subject in Japanese>

背景:
- ...

変更点:
- ...

影響:
- ...

テスト:
- ...
```

規則:

- `feat`、`fix`、`docs`、`refactor`、`test`、`style`、`chore`、`ci`、`build`、`perf` のいずれかを使う。
- subject は簡潔にし、末尾に句点を付けない。
- ユーザーが別言語を明示しない限り body は日本語で書く。
- 非自明な変更では `背景` と `変更点` を含める。
- 動作、workflow、ユーザー向け仕様が変わる場合は `影響` を含める。
- 具体的な test evidence だけを記載する。テストを実行していない場合は、その事実を明記する。
- unstaged / untracked content から記述を推測しない。

### 6. index を commit する

path の追加指定や scope の拡大をせずに commit する。

```bash
git commit -F - <<'EOF'
<final message>
EOF
```

`-a`、path 引数、`--amend`、`--no-verify` は使わない。

detached HEAD からブランチを作成した後に hook または検証が失敗した場合は、新規ブランチと staged state を維持する。現在のブランチと失敗を報告し、自動 rollback やブランチ削除は行わない。

### 7. 結果を報告する

commit 成功後に次を実行する。

```bash
git log -1 --format=fuller --stat
git log -1 --name-status
git status --short
```

次を報告する。

- short commit hash
- 使用した正確な commit message
- commit したファイル
- 残っている unstaged / untracked changes

## ガードレール

- `git add` を実行しない。
- `main` では commit しない。
- 自動 fetch しない。
- push または PR 作成を行わない。
- rebase または amend を行わない。
- unstaged / untracked files を含めない。
- ユーザーの明示指示なしに hook を回避しない。
