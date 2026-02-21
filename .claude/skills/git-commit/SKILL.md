---
name: git-commit
description: git commit を自動化するスキル。ユーザーが /commit と呼び出した時、またはコミットを依頼した時にトリガーする。変更内容を分析し、Conventional Commits 形式・日本語でコミットメッセージを生成して git commit を実行する。
---

# Git Commit

変更内容を分析し、Conventional Commits 形式・日本語のコミットメッセージを生成して git commit を実行する。

## 手順

1. `git status` で変更状況を確認する
2. `git diff` および `git diff --staged` で変更内容を分析する
3. `git log --oneline -5` で直近のコミットメッセージのスタイルを確認する
4. 変更内容に基づき、Conventional Commits 形式・日本語でコミットメッセージを生成する
5. 変更ファイルを `git add` でステージングする（機密ファイルは除外）
6. `git commit` を実行する

## Conventional Commits ルール

コミットメッセージは以下の形式に従う:

```
<type>: <日本語の説明>
```

### プレフィックス一覧

| プレフィックス | 用途 |
|---|---|
| `feat` | 新機能の追加 |
| `fix` | バグ修正 |
| `docs` | ドキュメントのみの変更 |
| `refactor` | リファクタリング（機能変更なし） |
| `style` | コードスタイル・フォーマットの変更 |
| `test` | テストの追加・修正 |
| `chore` | ビルド・設定・依存関係など雑務 |

### メッセージ例

```
feat: 画像OCR機能を追加
fix: Gemini APIのタイムアウトエラーを修正
docs: README.mdにセットアップ手順を追記
chore: ruff-checkスキルを追加
```

## 注意事項

- `.env`、認証情報、シークレットファイルはステージングしないこと
- `--no-verify` フラグを使わないこと
- `--force` や `--force-with-lease` での push をしないこと
- コミットメッセージは HEREDOC 形式で渡すこと
- コミットメッセージの末尾に `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>` を付与すること
