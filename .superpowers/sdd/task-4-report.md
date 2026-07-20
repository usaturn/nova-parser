# Task 4 実装レポート

## Status

完了。LLM 構造推定を、入力済みブロックへの参照選択だけを返す契約として実装した。

## 実装内容

- `StructureClassifier` Protocol と `GeminiStructureClassifier` を追加した。
- 既存 `nova_parser.ocr.generate_json()` を `temperature=0.0`、JSON Schema、
  result validator、失敗アーティファクト付きで再利用した。
- 応答 Schema から `normalized_text` / `summary` を排除し、未知 ID、中心ページ外 ID、
  重複、順序変更、原文ブロック内に完全一致しない entity を拒否した。
- GM 継承範囲の player/shared 提案を GM のまま保持し、
  `audience_downgrade_candidate` を review reason に追加した。
- `StructureProposal` に classifier ID、prompt 契約版、`sha256:<64hex>` 入力 hash を必須記録した。
- 全体アウトラインを短い見出し候補と先頭 120 文字だけから一度推定し、
  失敗時は入力ブロックの min/max page に基づく決定的な unknown outline へ fallback した。
- `StructureWindow` を中心ページ、前後 1 ページの文脈、返却許可 ID に分離し、
  各ブロックが中心ページとして一度だけ返却対象になる窓生成を追加した。
- entity 検証用に OCR 原文を変更せずプロンプトへ渡し、正規化本文とは別に保持した。

## RED / GREEN 証拠

- 初回 RED: `uv run pytest -q tests/test_semistructure_llm.py`
  - `ModuleNotFoundError: nova_parser.semistructure.llm`
- 窓生成 RED: 同コマンド
  - `ImportError: build_structure_windows`
- モデル契約 RED: focused 実行
  - processing metadata 未必須、旧 `blocks` 契約、出力 metadata 不在の 3 failure
- 原文送信 RED: `-k unchanged_raw_text`
  - OCR 原文が prompt に含まれず 1 failure
- entity 境界 RED: `-k spanning`
  - 2 ブロック連結だけで成立する entity を誤受理して 1 failure
- 最終 GREEN: focused 44 passed、全体 625 passed / 6 skipped

## 検証コマンドと結果

- `uv run pytest -q tests/test_semistructure_llm.py tests/test_semistructure_models.py tests/test_semistructure_normalize.py tests/test_semistructure_input.py`
  - 44 passed
- `uv run pytest -q`
  - 625 passed、6 skipped
- `uv run task ruff`
  - All checks passed、71 files unchanged
- `git diff --check`
  - 問題なし

## 変更ファイル

- `src/nova_parser/semistructure/prompts.py`
- `src/nova_parser/semistructure/llm.py`
- `src/nova_parser/semistructure/models.py`
- `tests/test_semistructure_llm.py`
- `tests/test_semistructure_models.py`
- `tests/semistructure_factories.py`
- `.superpowers/sdd/task-4-report.md`

## 自己レビュー

- Schema と Pydantic の二重境界で生成本文・未知フィールドを拒否することを確認した。
- 返却順は中心ページの `context_blocks` 順と比較し、同一 ID の複数窓生成を防いだ。
- entity は選択ブロックそれぞれの `raw_text` 内で検証し、ブロック間連結による偽一致を防いだ。
- API 実呼び出しを行わず、全 LLM テストを注入した fake で実行した。

## 懸念

- Google GenAI 依存側の既知の `DeprecationWarning` が pytest で 1 件出るが、
  本変更による failure ではない。
- ページまたぎの結合自体はこの参照選択分類器では行わず、各窓の中心ページ所有を一意にした。
  将来結合を導入する場合は、別の境界判定レコードとして実装する必要がある。
