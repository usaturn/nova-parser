# Implementation Plan: docai2の出力品質改善

**Branch**: `004-docai2` | **Date**: 2026-02-28 | **Spec**: `/specs/004-docai2/spec.md`
**Input**: Feature specification from `/specs/004-docai2/spec.md`

## Summary

`docai2` モードの出力品質を改善し、欠損値の安全なTSV化・見出し準拠の抽出・設定エラーの明確化を達成する。既存 `docai` パイプラインを踏襲しつつ、改良版として `docai2` を独立運用可能にする。

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.14  
**Primary Dependencies**: google-genai, google-cloud-documentai, python-dotenv  
**Storage**: ファイル出力（`Output/*.docai2.tsv`）  
**Testing**: `uv run task ruff` による静的検証 + 既存サンプルでの手動実行確認  
**Target Platform**: Linux devcontainer / CLI 実行環境
**Project Type**: CLI ツール（単一Pythonプロジェクト）  
**Performance Goals**: 既存 `docai` と同等の処理成功率を維持しつつ品質改善  
**Constraints**: 既存モード互換を維持、欠損値は空文字、認証エラーは明確化  
**Scale/Scope**: `docai2` モードおよび関連ドキュメント更新に限定

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- ✅ CLI First: `--mode docai2` で実行可能
- ✅ Japanese-First Documentation: `docs/usage.md` に利用手順・認証手順を記載
- ✅ Safe Defaults for OCR Output: `None/null` 文字列の排除方針を採用
- ✅ Reproducible Toolchain: `uv run task ruff` で最終検証
- ✅ Incremental Delivery: spec/plan/tasks の順で成果物を作成

## Project Structure

### Documentation (this feature)

```text
specs/004-docai2/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── tasks.md
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
src/
└── nova_parser/
  ├── main.py
  ├── docai2.py
  ├── documentai.py
  └── ocr.py

docs/
└── usage.md
```

**Structure Decision**: 既存の単一CLIプロジェクト構造を維持し、`docai2` 実装は `src/nova_parser` 内で完結させる。テスト基盤は未導入のため、既存運用に合わせて lint + 手動実行確認を採用する。

## Complexity Tracking

憲章違反なし。
