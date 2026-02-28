# Implementation Plan: Devcontainer で Spec Kit を Copilot 運用に載せる

**Branch**: `003-copilot-spec-kit` | **Date**: 2026-02-28 | **Spec**: /specs/003-copilot-spec-kit/spec.md
**Input**: Feature specification from `/specs/003-copilot-spec-kit/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

devcontainer で Spec Kit の導入と Copilot 連携の運用導線を確立する。CLI 側のセットアップ確認・feature 起票・前提チェックを標準化し、手順を再現可能な形で文書化する。

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.14 / Bash  
**Primary Dependencies**: uv, specify-cli, GitHub Copilot (VS Code)  
**Storage**: リポジトリ内ファイル（`.specify/`, `.github/`, `specs/`）  
**Testing**: CLI の終了コード・生成物・メッセージを確認する運用テスト  
**Target Platform**: Linux devcontainer (Ubuntu 24.04)  
**Project Type**: 既存 Python CLI への開発運用導入  
**Performance Goals**: セットアップ手順を 5 分以内で完了可能  
**Constraints**: `uv` 統一運用、既存 CLI 互換維持、機密情報非コミット  
**Scale/Scope**: 単一リポジトリでの導入・運用確立

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
specs/003-copilot-spec-kit/
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
└── 003-copilot-spec-kit/
```

**Structure Decision**: 既存の単一 Python CLI 構成を維持し、Spec Kit 導入関連は `.specify/`, `.github/`, `specs/` 配下で完結させる。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| なし | 複雑化を追加する必要がない | 現行構成で要件を満たせる |
