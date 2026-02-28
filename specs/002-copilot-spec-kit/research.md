# Research: Devcontainer 上で Spec Kit を Copilot 運用可能にする

## 調査結論

- Spec Kit は `uvx` と `uv tool` の両方で運用可能で、devcontainer 内でも実行できる。
- `specify init --here --ai copilot` により既存リポジトリへ安全に初期化できる（確認プロンプトあり）。
- feature フローは `create-new-feature.sh` と `check-prerequisites.sh` で開始条件を機械検証できる。
- Copilot Chat 実行は VS Code UI 操作が必要で、CLI からは直接代替できない。

## 採用方針

1. 導入は `uv` 系コマンドに統一する。
2. 既存 CLI への影響が出ない範囲で Spec Kit ファイル群を追加する。
3. 再現可能性のため、各ステップに成功条件を設ける。

## リスクと対処

- ネットワーク不通時に導入失敗するリスク: 取得失敗時の再試行手順を明記する。
- Copilot 未認証リスク: CLI 検証と Chat 連携検証を分離して判定する。
- 既存差分混在リスク: feature ブランチ上で追加差分のみ確認して進める。
