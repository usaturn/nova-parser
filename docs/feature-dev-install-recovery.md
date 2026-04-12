# Claude Code `feature-dev` インストール復旧手順

`feature-dev` のインストール時に、次のようなエラーが出ることがあります。

```text
Error: Failed to install: Source path does not exist: /home/usaturn/.claude/plugins/marketplaces/claude-plugins-official/plugins/feature-dev
```

このドキュメントは、この状態を復旧するための手順をまとめたものです。

## 症状

よくある症状は次のいずれかです。

- `claude plugin install feature-dev@claude-plugins-official` が失敗する
- `claude plugin list` に `feature-dev@claude-plugins-official` が出るが、`failed to load` になる
- エラーメッセージ内のパスが、現在のホームディレクトリではなく古いユーザー名や別環境のパスを指している

例:

```text
Error: Failed to install: Source path does not exist: /home/usaturn/.claude/plugins/marketplaces/claude-plugins-official/plugins/feature-dev
```

## 原因

原因は `feature-dev` 自体が存在しないことではありません。多くの場合、Claude Code が保持しているマーケットプレイスのキャッシュ情報が壊れており、`~/.claude/plugins/known_marketplaces.json` に古い絶対パスが残っています。

典型例:

- 以前は `/home/usaturn/...` で使っていた
- 現在は `/home/vscode/...` で使っている
- その結果、Claude Code が存在しない古い保存先を参照してしまう

## 復旧手順

### 1. 現在の状態を確認する

```bash
claude plugin marketplace list
claude plugin list
cat ~/.claude/plugins/known_marketplaces.json
```

`known_marketplaces.json` の `installLocation` が現在のホームディレクトリを指していなければ、この問題です。

### 2. 壊れた公式マーケットプレイス登録を削除する

```bash
claude plugin marketplace remove claude-plugins-official
```

この操作で、壊れた `installLocation` を持つマーケットプレイス設定を外します。

### 3. 公式マーケットプレイスを再登録する

```bash
claude plugin marketplace add anthropics/claude-plugins-official
```

再登録後、`~/.claude/plugins/known_marketplaces.json` の `installLocation` が現在の環境に合わせて再生成されます。

### 4. `feature-dev` を再インストールする

```bash
claude plugin install feature-dev@claude-plugins-official
```

明示的にユーザースコープへ入れたい場合は次でも構いません。

```bash
claude plugin install feature-dev@claude-plugins-official --scope user
```

### 5. 反映する

Claude Code のセッションがすでに開いている場合は、次のどちらかを行います。

- `/reload-plugins` を実行する
- Claude Code を再起動する

## 確認方法

次のコマンドで状態を確認します。

```bash
claude plugin marketplace list
claude plugin list
cat ~/.claude/plugins/known_marketplaces.json
```

期待される状態:

- `claude plugin marketplace list` に `claude-plugins-official` が表示される
- `claude plugin list` に `feature-dev@claude-plugins-official` が表示される
- `Status: enabled` になる
- `known_marketplaces.json` の `installLocation` が現在のホームディレクトリ配下を向く

## うまくいかない場合

### まだ `failed to load` が残る場合

一度アンインストールしてから入れ直します。

```bash
claude plugin uninstall feature-dev@claude-plugins-official
claude plugin install feature-dev@claude-plugins-official
```

### `settings.json` に古いプラグイン ID が残っている場合

`~/.claude/settings.json` の `enabledPlugins` に、現在使っていない古い ID が残ることがあります。たとえば次のようなものです。

```json
"feature-dev@anthropics/claude-code": true
```

現在の導入先が `claude-plugins-official` なら、使うべき ID は次です。

```json
"feature-dev@claude-plugins-official": true
```

古い ID が残っていると混乱の原因になるため、不要なら削除します。

## 補足

- この障害は、ユーザー名変更、devcontainer / Codespaces への移行、`~/.claude` ディレクトリのコピー後に起きやすい
- 問題の本質は「プラグインの欠損」ではなく「マーケットプレイスの保存先参照の破損」
- 単なる `claude plugin marketplace update` では直らず、`remove` → `add` が必要なことがある
