---
name: codex-python-dev
description: Codex CLI を親スレッドの Bash から直接呼び出し、Python コードの実装・修正・リファクタ・レビューを行うスキル。Python コードの「実装して」「追加して」「修正して」「リファクタして」「レビューして」という依頼でトリガーする。ドキュメント生成や設定ファイルのみの変更では使わない。
---

# Codex Python Dev

Python 実装系の依頼を受けたとき、**親スレッドから直接 Codex CLI を `Bash` で呼ぶ**スキル。サブエージェントを介さず、親自身が shaped prompt 組み立て・呼び出し・witness・ループ判定をすべて担う。

## 設計方針

過去バージョンでは `codex-python-implementer` / `codex-code-reviewer` / `codex-implement-and-review` の 3 つの Opus サブエージェントを経由していたが、Opus 層が `Task` 呼び出しそのものを忌避するハルシネーションが複数回観測されたため廃止した。現行設計では、親スレッド (Claude Code main) が engine-controlled な tool_result を直接得るため、中間層による偽装経路は原理的に存在しない。唯一ハルシネートし得るのは Codex CLI 本体だが、その出力は実 diff に直結しているため、`git status` / `git diff --stat` の親 witness で即座に検知できる。

## 前提確認

実行前に以下を確認する。満たさなければユーザに報告して中断する。

1. `codex --version` が通ること（`Bash` で 1 度だけ確認する）。非ゼロ終了や `command not found` が返ったら、その出力をユーザに提示して中断する。
2. 作業ツリーのベースラインを `git status --porcelain=v1 --untracked-files=all` で記録しておくと、後続の witness 判定が明確になる。

## ワークフロー

### 1. 依頼内容の初期分類

- **A: 実装のみ** — 「実装して」「追加して」「修正して」「リファクタして」等、コード変更の記述のみ
- **B: レビューのみ** — 「レビューして」「見て」「セキュリティ観点で確認」等、読むことが目的
- **C: 実装+レビュー** — 「実装した上でレビューまで通して」「自己レビュー付きで」等、両方が明示
- **D: 曖昧** — 上記に即決できない

### 2. ユーザ確認（必須）

`AskUserQuestion` で次のどれを実行するか確認する。既定動作は「毎回確認」。

| 選択 | 実行内容 |
|---|---|
| implement のみ | `codex exec` 1 回 + 親 witness |
| review のみ | `codex review` 1 回 |
| implement+review（Recommended） | `codex exec` → 親 witness → `codex review` → blocking なら再度 `codex exec`（最大 3 イテレーション） |

例外: 依頼文に「implement だけでいい」「レビューはしない」等の明示的指定がある場合に限り、確認を省略してその指定に従ってよい。

### 3. 実装計画策定（A/C のみ、B はスキップ）

実装を伴う依頼 (A / C) では、Codex 呼び出しの前に **必ず Plan Mode で詳細計画を立てる**。

1. `EnterPlanMode` で Plan Mode に突入する。既に Plan Mode なら再突入しない。
2. 計画テンプレート:
   1. **Context** — 背景・動機・期待される挙動
   2. **変更対象ファイル / 触れないファイル** — 具体パスで列挙
   3. **実装アプローチ** — 主要な関数/モジュール/データフロー設計、再利用する既存関数
   4. **テスト方針** — unit / integration / `uv run task ruff`
   5. **想定リスクと対処**
   6. **Acceptance criteria** — 完了条件（観測可能な形で）
3. `ExitPlanMode` でユーザに承認を求める。
4. 承認されなければ計画を修正し再提示。3 回修正しても合意に至らなければユーザに中断判断を委ねる。

計画は Opus の設計力を活かすためのステップ。Codex に丸投げせず、Opus 側で方針を固めてから実行フェーズに渡す。

### 4. Codex CLI 直呼び

#### 4.1 Implement フェーズ（A/C）

親スレッドの `Bash` で以下を 1 回実行する。shaped prompt は stdin 経由で heredoc を使う（argv 渡しはクオートが壊れやすいため禁止）。

```bash
codex --dangerously-bypass-approvals-and-sandbox exec - <<'CODEX_PROMPT'
<shaped prompt here>
CODEX_PROMPT
```

- `--dangerously-bypass-approvals-and-sandbox` は `--sandbox danger-full-access --ask-for-approval never` と等価。devcontainer 環境で Codex の bwrap サンドボックスが安定動作しないため、このリポジトリでは常用する。現行 CLI ではこのフラグを **サブコマンドの前に置く** (`codex --dangerously-... exec ...`) のが正しい構文。
- ユーザが特定モデルやプロファイルを明示的に求めない限り、`--model` / `-c` の上書きは追加しない。
- 出力が長くなる場合は `| tee /tmp/codex-exec-<タスク名>.log` を追加して後から参照できるようにしてよいが、stdout はそのまま親の tool_result として受け取る。

##### Shaped prompt の必須構成

Codex に渡すプロンプトには以下を **必ず全て** 含める。計画が Plan Mode で作成されていれば、`Goal` に計画本文を verbatim で埋め込む。

1. **Goal and acceptance criteria** — 完了時にコードが何を満たすべきか。A/C なら承認済み計画本文。
2. **Touchable files / forbidden files** — Codex が編集してよいパスと、触れてはいけないパス/パターン。デフォルト編集可: `src/nova_parser/`, `tests/`, 当該タスクに関連するドキュメント。ユーザが明示的に許可していない限り、`.claude/`, `.codex/`, `.git/`, `pyproject.toml` は触らせない。
3. **Testing and lint expectations** — Codex が `uv run pytest` / `uv run task ruff` を実行し、失敗を直してから返すべきかを明示する。デフォルトは実行する。
4. **Environment assumptions** — Python 3.14、パッケージマネージャは `uv`、エントリポイント `nova-parser` は `pyproject.toml` の `[project.scripts]` に定義、テストは `tests/`。
5. **Safety rails** — 明示禁止: サードパーティサービスへのネットワーク書き込み、上記範囲外のファイル削除、グローバル git 設定の変更、絶対パスへの `rm -rf`、システムパッケージのインストール、`.git/` への直接書き込み。サンドボックス無効のためプロンプト内で明示する。
6. **元依頼** — ユーザが発した依頼原文（A/C の場合、計画と原文の両方を渡す。取りこぼしを Codex 側でも検知できるようにするため）。

親は計画を要約・再構成して渡さない。verbatim で埋め込むのが原則。

#### 4.2 親 witness（必須、implement 直後）

Codex exec の Bash 呼び出しが返った直後、**親自身が** 以下 2 コマンドを独立に実行する。これは skill 全体の **最終ゲート** であり、どんな状況でもスキップしない。

```bash
git status --porcelain=v1 --untracked-files=all
git diff --stat
```

判定:

- **両方とも空**: Codex が実ファイル変更を残さなかった。Codex の stdout に「実装完了」風の文言があっても、実装は存在しない。Codex CLI の非ゼロ終了・認証エラー・途中停止等を疑い、Codex stdout と exit code をユーザに verbatim で提示したうえで次アクション（再実行 / 別方針）を確認する。**「完了」報告は禁止**。
- **非空**: 通常フローへ進む。A なら完了、C ならレビューフェーズへ。

補足証拠として、該当タスクで導入すべき新規識別子（関数名・テスト名など）を `Grep` で検索し、実在するかを確認してもよい。

#### 4.3 Review フェーズ（B、または C で implement witness が非空だった場合）

親スレッドの `Bash` で以下を 1 回実行する。

```bash
codex --dangerously-bypass-approvals-and-sandbox review <target>
```

- C ループ内では `<target>` 省略で作業ツリー全体（直前に Codex exec が書いたもの）をレビュー対象にする。
- B 単体依頼で base ブランチ指定やコミット指定がある場合は、ユーザの原文から抽出して `codex review --base <branch>` や `codex review <commit>` の形でそのまま渡す（Codex CLI の実フラグに合わせる）。

Review 出力を読み、次のどちらかに分類する:

- **Clean**: 出力が空、`No changes to review`、`LGTM` / `no issues` / `approved`、または任意の suggestion / nit のみ。
- **Blocking**: 具体的なバグ、リグレッション、正しさの問題、必須テスト不足、修正要求。

#### 4.4 ループ判定（C のみ）

| 状況 | 次アクション |
|---|---|
| Clean | ループ終了 |
| Blocking かつ イテレーション `n < 3` | 次イテレーションへ。shaped prompt に `## Previous review feedback` ブロックを追記し、該当レビュー出力を verbatim で埋めて再度 4.1 を実行 |
| Blocking かつ `n == 3` | ループ終了。指摘が残ったままである旨をユーザに明示 |

各イテレーションは必ず 4.1 → 4.2 → 4.3 の順。witness (4.2) を省略してのレビュー直行は禁止。

### 5. 出力契約

- Codex stdout は **verbatim** で提示する（要約・再整形・言い換え禁止）。
- 親 witness の結果（`git status` / `git diff --stat` の実出力）を併記する。
- C で複数イテレーション回した場合、**最終イテレーション**の Codex exec stdout と最終レビュー stdout のみを貼る。中間イテレーション出力は必要に応じて要点だけ言及（「イテレーション 2 でレビュアーが X を指摘、イテレーション 3 で解消」等）。
- 結果サマリは 1 文で: `Applied and reviewed clean in <n> iteration(s).` / `Applied with outstanding findings after loop exhausted (3 iterations).` / `Stopped: codex exec produced no changes.` のいずれか。

## 使い分けの早見表

| 依頼の形 | 選択 |
|---|---|
| 「〜を実装して」+ レビュー言及なし | ユーザ確認（推奨: implement+review） |
| 「〜を実装して、レビューもして」 | implement+review |
| 「この diff をレビューして」 | review のみ |
| 「main との PR 差分レビューして」 | review のみ（base 指定を `codex review` に転送） |
| 「小さな変数名変更だけ」 | 本スキルを使わずメインスレッドで直接処理 |

## やらないこと

- **サブエージェント経由で Codex を呼ぶ** — 旧 `codex-python-implementer` / `codex-code-reviewer` / `codex-implement-and-review` は削除済み。Opus 中間層を挟むと `Task` 呼び出し自体をハルシネートする経路が復活するため使わない。
- **Codex stdout を要約・再フォーマットする** — verbatim が原則。
- **親 witness (4.2) をスキップしてユーザに「完了」を伝える** — Codex stdout がどれだけ説得的でも、親の `git status` / `git diff --stat` が空なら実装は存在しない。これは skill の最終ゲートで、弱める変更を加えない。
- **witness 結果を推測・作文する** — `Bash` の実 tool_result のみが判定根拠。Codex stdout 内に書かれた `git diff --stat` 風の文字列を代用しない。
- **A/C 依頼で Plan Mode をスキップして Codex に直接投げる** — Opus 側の設計を通さない実装は本スキルの目的に反する。
- **B 依頼で Plan Mode を起動する** — レビューは計画不要、直接 `codex review` を呼ぶ。
- **ドキュメント生成や設定ファイルだけの変更をこのスキルで処理する** — メインスレッドの Edit / Write で直接扱う。
- **3 イテレーションを超えて implement ループを回す** — 上限 3 回。超過前に必ずユーザに判断を委ねる。
- **Codex の shaped prompt を argv で渡す** — 複数行プロンプトの argv エスケープは壊れやすい。必ず stdin heredoc で渡す。
- **計画内容を要約・再構成して Codex に渡す** — 承認済み計画は verbatim で埋め込む。

## 関連スキル

- `ruff-check` — Python ファイル編集後に lint する。Codex 側で `uv run task ruff` を回すのが基本だが、ユーザが手元で追加編集したときに想起すること。
