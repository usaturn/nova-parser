---
name: pr-review
description: GitHub の指定した PR をレビューする。PRのメタデータ、説明、差分（diff）を gh CLI で取得し、使い捨て git worktree 上で検証した指摘を Severity・位置・根拠付きで reviews/branch/model.md に作成または更新する。PR番号・URLを指定したコードレビュー依頼で使用する
---

# GitHub PR レビュー

GitHub 上の指定された Pull Request（PR）に対して、Codex の `/review` に近い高品質なコードレビューを行います。git worktree を使用し、ユーザの作業ブランチ・working tree に触れずにレビューします。

## 規約

- レビュー出力は助言として扱われる
- プロダクトコード・テストを編集しない
- レビュー中は `git clean`、`git checkout -f`、`git reset --hard`、`git worktree remove --force` を実行しない。既存 worktree を再利用・初期化・自動削除しない
- 独立したレビューを行うため、`reviews/<変換後ブランチ名>/` にある他モデルのレビュー本文は、候補の洗い出し・重点観点の収集・重複確認・自分の指摘の検証を含むいかなる目的でも読まない。レビュー完了後も読まない。メインリポジトリ側と `$WT` 側（PR に同梱された `reviews/`）のどちらも対象とする
- `MAIN_ROOT` は、指定された PR の URL に `devenv` が含まれる場合は toplevel 直下のパス `devenv` の submodule ルートへ確定する。含まれない場合はカレントディレクトリを `MAIN_ROOT` とする
- 自モデルの既存レビューはライブの `$DESTINATION` ではなく、`create` が返した `$PREVIOUS_REVIEW`（セッション内 snapshot）だけを読む。`$PREVIOUS_REVIEW` が空なら既存レビューなしとして扱う
- Codex ではモデル名を自分で推測・短縮・一般化せず、`create` が Codex session metadata から確定した `model_name` を使用する。Codex 実行時は `create --model-name` を渡さない
- Codex 以外では、実行中のエージェントランタイムが提示する正確なモデル識別子を `MODEL_NAME` として記録し、`create --model-name "$MODEL_NAME"` に一度だけ渡す。モデル系列の説明、設定ファイル、既存レビューのファイル名から推測しない
- Codex 以外で正確なモデル識別子を取得できない場合は、代替名で続行せず停止してユーザに確認する
- provider にかかわらず、draft と destination は `create` が返した値をそのまま使用する。`save` では model、draft、destination を再指定しない
- 初回・更新とも `gh pr diff "$PR_NUMBER"` が返す現在の PR 全体差分をレビューする
- PR 内の各 commit と親 commit の差分、前回 HEAD と現在 HEAD のローカル diff はレビュー対象にしない
- 更新時は既存 active 指摘を現在の差分と `$WT` のコードで再検証する
- 継続指摘は ID・タイトル・検出時 HEAD を維持し、位置と根拠を現在値へ更新する
- 解消済み指摘は active Severity セクションから `Resolved findings` へ移す
- 旧形式に存在しない過去 HEAD を推測しない
- 旧形式の active 指摘を安全に解釈できない場合は既存成果物を上書きせず停止する
- rebase または force-push 後も commit 単位の review range は計算せず、現在の `gh pr diff` 全体をレビューする
- 実際のコードパスと周辺ファイルを読んで指摘を検証する
- 指摘は報告前に反証を試みる（「この指摘が誤りだとしたらどこか」を自問し、反証に成功した候補は報告しない）
- 指摘がパッケージの挙動に依存する場合は、依存関係ファイルを読む
- diff に含まれない既存コードの問題は原則対象外。ただし diff が既存の潜在バグを顕在化させる場合は指摘対象
- 非現実的なエッジケース、推測ベースのリスク、大規模な書き直し、過度に複雑な修正提案を避ける
- 適切な責務境界での小さな修正を優先する
- 重大で実行可能な問題に集中する
- 指摘が不確かな場合は【確認推奨】と明記する
- 実行可能な指摘がない場合は、その旨を明確に伝える
- レビューは日本語で返す
- レビュー結果は常に `create` が返した `$DESTINATION` に作成する。`$DESTINATION` はヘルパーが PR のヘッドブランチ名とモデル識別子に含まれる `/` をすべて `-` に置換したパスへ配置する（例: ブランチ `feature/foo` は `feature-foo` 配下、モデル `opencode/deepseek-v4-flash-free` は `opencode-deepseek-v4-flash-free.md`）。`create` が返す `model_name` もこの置換後の値であり、エージェントが手で組み立てない
- 同じブランチを同じモデルで再レビューする場合は、同一ファイルの内容全体を上書きし、別名ファイルを作らない。別モデルの結果は同じブランチディレクトリ内の別ファイルへ保存する
- PR 上で既に指摘済みの問題は重複報告しない（触れる場合は「既出」と明記する）
- 件数表と Merge recommendation は active findings のみから計算する。Resolved findings は件数・Merge recommendation に含めない
- 既存 Review history と Resolved findings は削除・並べ替えず、今回分だけ追記する。同じ HEAD の再レビューでも Review history 行を追加する

## 手順

1. **PR情報の取得**:
   - ユーザがPR番号またはURLを指定している場合、`PR_JSON=$(gh pr view "$PR_NUMBER" --json number,title,body,baseRefName,headRefName,headRefOid,url)` を実行し、PRのタイトル、説明、ベースブランチ、ヘッドブランチなどのメタ情報を取得してコンテキストを把握する。ヘッドブランチは機械的に `HEAD_BRANCH=$(printf '%s' "$PR_JSON" | jq -r .headRefName)` で確定する。
   - 指定がない場合、`gh pr view` を実行して現在のブランチに関連付けられたPRの情報を取得する。関連付けられたPRがない場合はユーザにPR番号の指定を促す。
   - `gh pr view <PR_NUMBER> --comments` で既存のレビューコメント・議論を取得し、既出の指摘を把握する。
   - gh が未認証・API エラーの場合はエラー内容をそのまま報告し、`gh auth login` を案内する。
2. **worktree への展開**:
   - ユーザの作業ブランチ・working tree に触れないため、`gh pr checkout` は使わない。
   - `MAIN_ROOT` は、指定された PR の URL に `devenv` が含まれる場合は toplevel 直下のパス `devenv` の submodule ルートへ確定し、含まれない場合はカレントディレクトリを `MAIN_ROOT` とする。PR の URL は手順 1 で取得した `$PR_JSON` の `url` フィールドを使う。remote origin の URL では判定しない。
     ```bash
     PR_URL=$(printf '%s' "$PR_JSON" | jq -r .url)
     TOPLEVEL=$(git rev-parse --show-toplevel)
     if printf '%s' "$PR_URL" | grep -q devenv; then
       MAIN_ROOT="$TOPLEVEL/devenv"
     else
       MAIN_ROOT="$(pwd)"
     fi
     ```
   - PR の URL に `devenv` が含まれ `MAIN_ROOT` を submodule ルートに確定した場合、`git -C "$TOPLEVEL" submodule status -- devenv` が成功することを確認する。失敗した場合（toplevel 直下にパス `devenv` の submodule が登録されていない等）は推測せず停止してユーザに確認する。
   - `HELPER="$MAIN_ROOT/.agents/skills/pr-review/scripts/pr_review_workspace.py"` を記録する。以降、メインリポジトリに対する Git コマンドには必ず `git -C "$MAIN_ROOT"` を使い、カレントディレクトリへ暗黙に作用させない。
   - PR head は PR 番号ごとの専用 ref `PR_REF=refs/pr-review/<PR_NUMBER>` に固定する。`git -C "$MAIN_ROOT" fetch origin "+pull/<PR_NUMBER>/head:$PR_REF"` の後、`PR_HEAD=$(git -C "$MAIN_ROOT" rev-parse "$PR_REF")` で検証対象 SHA を確定する。共有の擬似参照 `FETCH_HEAD` は使わない。
   - fetch 後に `git -C "$MAIN_ROOT" merge-base HEAD "$PR_REF"` が成功することを確認する。失敗した場合は `MAIN_ROOT` の選定が誤っている（無関係なリポジトリに PR のオブジェクトを取り込んだ状態）ため、保存を行わず停止して報告する。
   - dedicated ref fetch 後、次で GitHub の head と `PR_HEAD` の一致を確認する（HEAD consistency check 1/3）。不一致、空値、`gh` failure の場合は履歴を追記せず保存しない。
     ```bash
     CURRENT_PR_HEAD=$(gh pr view "$PR_NUMBER" --json headRefOid --jq .headRefOid)
     test "$CURRENT_PR_HEAD" = "$PR_HEAD"
     ```
   - `create` を一度だけ実行する。ヘルパーは `${TMPDIR:-/tmp}/pr-review-<PR_NUMBER>-<ランダム値>/worktree` に新しい detached worktree を作り、保存先 `$DESTINATION` の create 時フィンガープリント（存在有無、通常ファイル・directory・symlink・その他の種別、通常ファイルの内容 SHA-256 または symlink target text の SHA-256）を `session.json` に保存する。既存パスは再利用しない。destination が通常ファイルの場合はセッション backup へ snapshot し、そのパスを `previous_review` として返す。destination が directory・symlink・特殊 entry の場合は fail-closed で停止する。
   - Codex では次を実行する。helper が `CODEX_THREAD_ID` から model を解決する。
     ```bash
     SESSION_JSON=$(uv run --no-project python "$HELPER" create --repo "$MAIN_ROOT" --pr-number "$PR_NUMBER" --commit "$PR_HEAD" --head-branch "$HEAD_BRANCH")
     ```
   - Codex 以外では、ランタイムから取得済みの正確な `MODEL_NAME` を使って次を実行する。
     ```bash
     SESSION_JSON=$(uv run --no-project python "$HELPER" create --repo "$MAIN_ROOT" --pr-number "$PR_NUMBER" --commit "$PR_HEAD" --head-branch "$HEAD_BRANCH" --model-name "$MODEL_NAME")
     ```
   - `CODEX_THREAD_ID` が存在するのに異なる `--model-name` を渡した場合、または非 Codex で `--model-name` を省略した場合、helper は worktree 作成前に停止する。
   - Codex rollout は追記中の末尾にある未完了 JSON レコードだけを無視する。改行済みの壊れた JSON レコード、正常な `turn_context.payload.model` の欠落は fail-closed で拒否する。モデル識別子に含まれる `/` はヘルパーが `-` に置換してファイル名に使う。空白・`..` など置換後も安全なファイル名にならない識別子は fail-closed で拒否する。
   - `SESSION_JSON` の JSON から以下を一度だけ取得する。値を推測・再構築しない。ヘルパーが失敗した場合は、手動で代替 Git コマンドを実行せず停止してエラーを報告する。
     ```bash
     WT=$(printf '%s' "$SESSION_JSON" | jq -r .worktree)
     STATE_FILE=$(printf '%s' "$SESSION_JSON" | jq -r .state_file)
     DRAFT=$(printf '%s' "$SESSION_JSON" | jq -r .draft)
     DESTINATION=$(printf '%s' "$SESSION_JSON" | jq -r .destination)
     MODEL_NAME=$(printf '%s' "$SESSION_JSON" | jq -r .model_name)
     MODEL_SOURCE=$(printf '%s' "$SESSION_JSON" | jq -r .model_source)
     PREVIOUS_REVIEW=$(printf '%s' "$SESSION_JSON" | jq -r '.previous_review // empty')
     SHORT_HEAD=$(git rev-parse --short=12 "$PR_HEAD")
     ```
   - `$SHORT_HEAD` は固定した `$PR_HEAD` の 12 文字短縮 hash である。`git rev-parse` は `$WT` または `$MAIN_ROOT` など、当該 object を参照できるリポジトリ上で実行する。
   - `$PREVIOUS_REVIEW` が空なら Mode は `Initial`、helper が返した通常ファイル snapshot なら Mode は `Update` とする。ライブ `$DESTINATION` と他モデル files は読まない。
   - 以降のファイル読解・テスト実行は `$WT` を対象に行う。ただしレビュー成果物は `create` が返した `$DESTINATION`（メインリポジトリの `reviews/` 配下）に書き、`$WT` 内には書かない。
3. **既存レビューの読解（更新時）**:
   - `$PREVIOUS_REVIEW` が空でない場合だけ、その snapshot ファイルを読む。ライブ `$DESTINATION`、他モデルのレビュー本文、ディレクトリ一覧から自モデルを推測して読むことはしない。
   - snapshot から active findings、既存の Review history、Resolved findings を把握する。旧形式で過去 HEAD が無い場合は推測せず、今回の Review history から開始し、旧形式 active 指摘の検出時 HEAD は `不明（旧形式）` とする。
   - 旧形式の active 指摘を安全に解釈できない場合は既存成果物を上書きせず停止する。
4. **差分収集**:
   - 次で PR 全体の差分を取得する。PR 内の各 commit 差分や前回 HEAD とのローカル diff は使わない。
     ```bash
     PR_DIFF=$(gh pr diff "$PR_NUMBER")
     ```
   - `gh pr diff` 失敗時は履歴を追記せず保存しない。
   - 取得直後に HEAD consistency check 2/3 を実行する。不一致、空値、`gh` failure の場合は履歴を追記せず保存しない。
     ```bash
     CURRENT_PR_HEAD=$(gh pr view "$PR_NUMBER" --json headRefOid --jq .headRefOid)
     test "$CURRENT_PR_HEAD" = "$PR_HEAD"
     ```
5. **コンテキスト読解**:
   - `$WT` にある変更ファイルは diff だけでなくファイル全体を読む。変更箇所の呼び出し元・呼び出し先、依存関係ファイル（pyproject.toml / package.json / lock ファイル等）、変更に対応する既存テストを辿る。
6. **プロジェクト固有観点の取り込み**: CLAUDE.md とプロジェクト内の規約・設計ドキュメントがあれば読み、そのプロジェクトの重点観点（例: XSS 多層防御、並列・増分ビルド互換性）を優先順位のチェックリストに加える。メインリポジトリ側と `$WT` 側の `reviews/` にある他モデルのレビューは情報源にしない。
7. **候補洗い出し → 検証 → 報告**:
   - 優先順位に沿って候補指摘を洗い出し、検証プロトコルを通過したものだけを指摘フォーマットで報告する。
   - 更新時は既存 active 指摘を現在の差分と `$WT` のコードで再検証し、継続・解消・新規に分類する。
   - 継続指摘は ID・タイトル・検出時 HEAD を維持し、位置と根拠を現在値へ更新する。
   - 解消済み指摘は active Severity セクションから `Resolved findings` へ移し、解消確認時 HEAD に今回の `$SHORT_HEAD` と確認根拠を記録する。
   - 新規指摘には検出時 HEAD として今回の `$SHORT_HEAD` を設定する。
8. **レビュー結果の保存**:
   - draft 完成時の時刻を次で取得する。
     ```bash
     REVIEWED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
     ```
   - Review history に今回分を 1 行だけ追記する（既存行は削除・並べ替えない）。列は Reviewed at (UTC)・HEAD（`$SHORT_HEAD`）・Mode（`Initial` または `Update`）。同じ HEAD でも追記する。
   - draft/save 直前に HEAD consistency check 3/3 を実行する。不一致、空値、`gh` failure の場合は履歴を追記せず保存しない。
     ```bash
     CURRENT_PR_HEAD=$(gh pr view "$PR_NUMBER" --json headRefOid --jq .headRefOid)
     test "$CURRENT_PR_HEAD" = "$PR_HEAD"
     ```
   - 完成したレビュー本文を `create` が返した `$DRAFT` へ書く。これはメインリポジトリと `$WT` の外部にある復旧用の正本であり、最終応答後も削除しない。保存先と draft は `create` が確定して返した `$DESTINATION`・`$DRAFT` のみを使い、パスを自分で組み立てない。
   - 保存は `uv run --no-project python "$HELPER" save --state "$STATE_FILE"` だけを実行する。`save` は共有ロック（Git 共通ディレクトリの `flock`）で最終検証と原子的コピーを直列化し、保存直前の検証として、確定した `$DESTINATION` が create 時フィンガープリントと一致することを確認してから原子的に保存する。`reviews/` 配下の無関係な他モデルのファイルも、`reviews/` 外のメインリポジトリの変更（tracked ファイルの編集、untracked ファイルの追加、HEAD・branch の移動）も `save` を妨げない。ただし確定した `$DESTINATION` はこのセッションが保存するまで不変でなければならない。resolved path は `reviews/` 外への脱出検証だけに使い、fingerprint と原子的置換は lexical destination entry を対象にする。同じブランチ・モデルの再レビューでは内容全体を上書きし、別名ファイルは作らない。
   - 途中確認用の `uv run --no-project python "$HELPER" verify --state "$STATE_FILE"` は残してよいが、`verify` も同じ共有ロックと上記の destination フィンガープリント検証を行う。ただし保存の安全性はその事前実行に依存しない。
   - 別モデルのレビュー結果は、`create` が返した `$DESTINATION` に従って同じブランチディレクトリ内の別ファイルへ保存する。レビュー成果物を `$WT` 内には書かない。
9. **後片付けと報告**: worktree、session state、外部バックアップを自動削除しない。最終応答で保存先、外部バックアップ、残した worktree の完全パスを報告する。後片付けが必要な場合も、このスキル内で破壊的コマンドを組み立てずユーザへ判断を委ねる。

## 検証プロトコル

候補指摘 1 件ごとに、以下を順に行う:

1. **精読**: 指摘に関わる実コードパスを最後まで読む（途中の早期 return・ガード・呼び出し規約を見落とさない）
2. **反証試行**: 「この指摘が誤りだとしたらどこか」を明示的に検討する（既存のガード、テストによる固定、ドキュメント化された意図的トレードオフ等）。反証に成功したら報告しない
3. **実行検証**: 挙動が不確かな場合、可能なら worktree 側で実行して確かめる（プロジェクトのテストコマンド、REPL、最小再現スクリプト）。テストコマンドが不明な場合は無理に実行しない

検証結果に応じて、各指摘に確度ラベルを付ける:

- **【検証済み】**: コード精読または実行検証で裏付けがある
- **【確認推奨】**: もっともらしいが裏付けが不完全
- **【要設計判断】**: 挙動は確認済みだが、修正すべきか仕様とすべきかはユーザの判断が必要

## Severity 判定基準

| Severity | 基準 |
|---|---|
| Critical | データ破壊・セキュリティ侵害・主要機能の停止が、通常の利用経路で発生する |
| High | 実行時バグ・セキュリティ問題・破壊的挙動変更が、現実的な条件で発生する |
| Medium | 特定条件下の実挙動不具合、互換性リスク、仕様未定義の挙動（設計判断が必要なものを含む） |
| Low | 実害は限定的だが対応が望ましい欠陥（依存下限未指定、稀なエッジケース、性能の二次的コスト等） |
| Info | 実害なし。ドキュメント追随漏れ、スタイル逸脱、将来の再検討事項 |

重大度は「影響 × 発生しやすさ」で判定し、迷ったら低い方に倒す（Severity インフレを防ぐ）。

## 指摘 1 件のフォーマット

各指摘は次のテンプレートに従う:

```markdown
### <ID>: <一行タイトル>【検証済み|確認推奨|要設計判断】

- 位置: `path/to/file.py:123`（複数箇所あれば列挙）
- 検出時 HEAD: `<12文字のshort-sha>` または `不明（旧形式）`
- 内容: 何が・どの条件（入力・状態・操作列）で起きるか
- 根拠: 読んだコードパス、実行した検証とその結果
- 推奨対応: 適切な責務境界での最小の修正案（あわせて固定すべきテスト）
```

- ID は Severity 別の連番（Critical: C-1、High: H-1、Medium: M-1、Low: L-1、Info: I-1）
- 「内容」には具体的な発生条件を必ず書く。「〜の可能性がある」だけの指摘は書かない
- 新規指摘の検出時 HEAD は今回の `$SHORT_HEAD` を設定する。継続指摘は検出時 HEAD を維持する。旧形式から移行する指摘で過去 HEAD が無い場合は `不明（旧形式）` とし、hash を生成・推測しない

## 優先順位

1. 実行時バグ
2. セキュリティ問題
3. 破壊的な挙動変更
4. 依存関係の互換性リスク
5. 不足しているテスト
6. 保守性リスク

## コメントしないこと

- 無害なフォーマット差分
- 命名の好み
- 根拠のない理論上の問題
- 差分と無関係な広範なリファクタリング
- 差分外の既存コードの問題（diff が顕在化させる場合を除く）
- 重要な不変条件を隠していないコメント不足
- リンタ・フォーマッタで機械的に検出できる指摘だけの列挙

## 出力

以下のテンプレートを使用する。指摘が 0 件の Severity セクションは省略する。件数表と Merge recommendation は active findings のみから計算する。

```markdown
- 対象: PR #<N> / head <12文字のshort-sha> / <YYYY-MM-DD>

## Review history

| Reviewed at (UTC) | HEAD | Mode |
|---|---|---|
| <RFC3339 UTC> | `<12文字のshort-sha>` | Initial または Update |

## Summary

（総評 2〜4 文。何をレビューし、何を実行検証したかを含める）

| Severity | 件数 |
|---|---|
| Critical | n |
| High | n |
| Medium | n |
| Low | n |
| Info | n |

## Critical

## High

## Medium

## Low

## Info

（各指摘は「指摘 1 件のフォーマット」に従う）

## Test suggestions

（番号付きリスト。各項目にどの指摘（ID）を固定するテストかを明記する）

## Merge recommendation

（下記基準で 1 つを選び、理由を 1 文添える）

## Resolved findings

### <過去のID>: <過去の指摘タイトル>

- 検出時 HEAD: `<12文字のshort-sha>` または `不明（旧形式）`
- 解消確認時 HEAD: `<今回の12文字のshort-sha>`
- 確認根拠: <現在のコードパスまたは実行検証による根拠>
```

- Review history の時刻は `$REVIEWED_AT`（`date -u +"%Y-%m-%dT%H:%M:%SZ"`）を使う。HEAD は `$SHORT_HEAD`（12 文字）。Mode は `$PREVIOUS_REVIEW` が空なら `Initial`、snapshot があれば `Update`
- 既存 Review history 行と既存 Resolved findings は削除・並べ替えず、今回分だけ追記する。同じ HEAD でも追記する
- Resolved findings が無い初回で解消も無い場合はセクションを省略してよい。更新で既存 Resolved findings がある場合は維持する

Merge recommendation の判定基準:

- **Approve**: 【検証済み】の Critical / High が 0 件で、残る指摘が Medium 以下または【要設計判断】のみ
- **Needs manual verification**: 【確認推奨】の High 以上が残っている、または必要な実行検証ができなかった
- **Request changes**: 【検証済み】の Critical / High が 1 件以上ある

## 出力前セルフチェック

- `PR_HEAD`、`gh pr diff`、`$WT` が同じ headRefOid に対応しているか（3 地点の HEAD consistency check がすべて成功したか）
- 自モデルの `$PREVIOUS_REVIEW` 以外（ライブ `$DESTINATION`、他モデルのレビュー本文）を読んでいないか
- Review history に UTC、12 文字 HEAD、Mode（`Initial` または `Update`）が今回分として 1 行だけ追加されているか。既存行を削除・並べ替えていないか
- active 指摘の検出時 HEAD が維持または新規設定されているか。旧形式の不明 hash を生成していないか（`不明（旧形式）` を使う）
- 解消済み指摘が active counts から除かれ、Resolved findings に存在する（検出時 HEAD・解消確認時 HEAD・確認根拠付き）か
- 件数表と本文の active 指摘数が一致しているか
- 全指摘に位置（`file:line`）・具体的な発生条件・確度ラベルがあるか
- 各指摘に反証を試みたか
- 「コメントしないこと」に該当する指摘が紛れていないか
- メインリポジトリ側と `$WT` 側の `reviews/<変換後ブランチ名>/` にある他モデルのレビュー本文を開いたり、検索対象に含めたりしていないか
- Merge recommendation が判定基準と整合し、active findings のみから計算されているか
- `MAIN_ROOT` は指定された PR の URL に `devenv` が含まれる場合は toplevel 直下のパス `devenv` の submodule ルートに確定し、含まれない場合はカレントディレクトリとしたか。`merge-base HEAD "$PR_REF"` の成功を確認したか
- `create` が返した `model_name`、`draft`、`destination`、`previous_review` を変更・再構築せず使用したか
- `save` を `--state "$STATE_FILE"` だけで実行し、caller-selected path を渡していないか
- `save` の返却した destination と backup が存在し、最終応答にその完全パスを記載したか
- 同じブランチ・モデルの再レビューで既存ファイルの内容全体を上書きし、別名ファイルを作っていないか
- レビュー成果物が `create` が返した `$DESTINATION` に書かれ、`$WT` 配下に無いか
- `git clean`、強制 checkout/reset、worktree の強制削除を実行していないか
- 保存前に検証（確定 `$DESTINATION` のフィンガープリントが不変）が成功し、`save` の出力先と外部バックアップの両方が存在するか
- 最終応答に保存先、外部バックアップ、残した worktree の完全パスを記載したか
