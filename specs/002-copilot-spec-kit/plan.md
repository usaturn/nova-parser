# Implementation Plan: Devcontainer 上で Spec Kit を Copilot 運用可能にする

**Branch**: `002-copilot-spec-kit` | **Date**: 2026-02-28 | **Spec**: /specs/002-copilot-spec-kit/spec.md
**Input**: Feature specification from `/specs/002-copilot-spec-kit/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Spec Kit を既存 devcontainer 環境へ導入し、CLI 検証・feature 開始・Copilot Chat 連携開始までを再現可能な運用フローとして確立する。`uv` 統一運用と既存 `nova-parser` CLI 互換維持を前提に、手順の文書化と検証結果の明示を行う。

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.14 / Bash  
**Primary Dependencies**: uv, specify-cli, GitHub Copilot (VS Code)  
**Storage**: リポジトリ内ファイル（`.specify/`, `.github/`, `specs/`）  
**Testing**: CLI コマンド実行結果による確認（終了コード・生成物・メッセージ）  
**Target Platform**: Linux devcontainer (Ubuntu 24.04)  
**Project Type**: 既存 Python CLI への開発運用導入  
**Performance Goals**: セットアップを 5 分以内で再実行可能  
**Constraints**: Python 関連手順は `uv` 統一、既存 CLI 互換維持、機密情報をコミットしない  
**Scale/Scope**: 1 リポジトリ、少人数開発チーム向けの運用確立

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] All Python commands use `uv` (`uv run`, `uv add`, `uvx`, `uv tool`).
- [x] Existing CLI UX remains backward compatible (do not break current entrypoint/flags).
- [x] Verification steps are explicit and reproducible (commands + expected results).
- [x] Documentation updates are written in Japanese when process or behavior changes.
- [x] Secrets and credentials are not committed; `.env`/ignore policy is respected.

## Project Structure

### Documentation (this feature)

```text
specs/002-copilot-spec-kit/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
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

docs/
├── usage.md
└── mcp-servers.md

.specify/
├── memory/
├── scripts/
└── templates/

.github/
├── prompts/
└── agents/

specs/
└── 002-copilot-spec-kit/
```

**Structure Decision**: 既存の単一 Python CLI プロジェクト構成を維持し、Spec Kit 関連は `.specify/`, `.github/`, `specs/` に限定する。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| なし | 追加の複雑化は不要 | 既存構成で要件と検証を満たせる |
