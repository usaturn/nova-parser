---
name: ruff-check
description: Python コードを書いた後に ruff で lint・フォーマットチェックを自動実行するスキル。Python ファイル (.py) を新規作成・編集した直後にトリガーする。Write や Edit ツールで .py ファイルを変更したら必ずこのスキルの手順に従うこと。
---

# Ruff Check

Python ファイルを書いた・編集した直後に ruff を実行してコード品質を確認する。

## 手順

1. `.py` ファイルを Write または Edit で変更した直後に、以下を実行する:

```bash
uv run task ruff
```

2. エラーが報告された場合、該当箇所を修正して再度 `uv run task ruff` を実行する
3. 全てのチェックが通るまで繰り返す

## 注意事項

- ruff の設定・実行コマンドは `pyproject.toml` の `[tool.taskipy.tasks]` と `[tool.ruff]` で一元管理されている
- 個別ファイル指定で直接 ruff を実行しないこと（taskipy タスク経由で統一する）
