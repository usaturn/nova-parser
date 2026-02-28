# Feature Specification: Copilot で Spec Kit をセットアップし実行試験する

**Feature Branch**: `001-copilot-spec-kit`  
**Created**: 2026-02-28  
**Status**: Draft  
**Input**: User description: "この devcontainer 環境の GitHub Copilot で spec kit をセットアップし、実際に動かすところまで試験して"

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Spec Kit CLI を導入して初期化できる (Priority: P1)

開発者として、この devcontainer 内で Spec Kit CLI を利用可能にし、既存リポジトリを `--ai copilot` で初期化したい。

**Why this priority**: ここが失敗すると以降の `/speckit.*` フローを実行できないため、最優先。

**Independent Test**: `uvx ... specify check` と `specify check` が成功し、`.specify/` と `.github/prompts/` が生成されれば独立して完了判定できる。

**Acceptance Scenarios**:

1. **Given** `uv` が利用可能な devcontainer、**When** `uvx --from git+https://github.com/github/spec-kit.git specify check` を実行する、**Then** `Specify CLI is ready to use!` が表示される。
2. **Given** リポジトリルート、**When** `specify init --here --ai copilot` を実行する、**Then** Spec Kit の初期化が完了し、次ステップ案内が表示される。

---

### User Story 2 - Spec Kit の feature ワークフローを開始できる (Priority: P2)

開発者として、Spec Kit 標準スクリプトで feature ブランチを作成し、spec/plan 生成の前提を満たしていることを確認したい。

**Why this priority**: 実装前に運用フローが機能することを確認でき、以降の仕様駆動開発へ接続できる。

**Independent Test**: `create-new-feature.sh` の JSON 出力で `SPEC_FILE` が返り、`check-prerequisites.sh --json --paths-only` がパス情報を返せば完了。

**Acceptance Scenarios**:

1. **Given** Spec Kit 初期化済みリポジトリ、**When** `bash .specify/scripts/bash/create-new-feature.sh --json "copilotでspec kit動作確認"` を実行する、**Then** `001-copilot-spec-kit` ブランチと `specs/001-copilot-spec-kit/spec.md` が生成される。

---

### User Story 3 - Copilot Chat で `/speckit.*` を実行開始できる (Priority: P3)

開発者として、VS Code の Copilot Chat から `/speckit.constitution` と `/speckit.specify` を実行し、対話ベースで仕様作成を開始したい。

**Why this priority**: CLI 検証後に実際の Copilot 運用へ接続できるかを確認する最終ステップ。

**Independent Test**: Copilot Chat で `/speckit.constitution` を入力し、エージェント応答が開始されれば独立して確認可能。

**Acceptance Scenarios**:

1. **Given** `.github/prompts/speckit.constitution.prompt.md` と `.github/agents/speckit.constitution.agent.md` が存在する、**When** Copilot Chat に `/speckit.constitution` を入力する、**Then** constitution 更新フローの応答が開始される。

---

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- `specify init --here` 実行時に既存ファイルと衝突する場合は、上書き前の確認プロンプトを明示的に承認する。
- feature ブランチ命名規則に合致しない場合、`check-prerequisites.sh` は失敗するため先に `create-new-feature.sh` を実行する。
- Copilot が未サインインの場合、CLI 側チェックは通っても `/speckit.*` 実行は開始できない。

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: システムは devcontainer 内で `uvx` による Spec Kit CLI 一時実行を成功させなければならない。
- **FR-002**: システムは `uv tool install` により `specify` コマンドを永続利用可能にしなければならない。
- **FR-003**: ユーザーは `specify init --here --ai copilot` により既存リポジトリを Spec Kit 初期化できなければならない。
- **FR-004**: システムは Spec Kit の feature 開始（ブランチ生成と spec ファイル生成）をスクリプトで実行できなければならない。
- **FR-005**: システムは Copilot Chat で利用する `/speckit.*` 定義ファイルを生成しなければならない。
- **FR-006**: システムは実行試験結果（成功/失敗理由）を開発者が確認できる形で出力しなければならない。

### Key Entities *(include if feature involves data)*

- **SpecKitWorkspace**: Spec Kit により初期化されたリポジトリ状態（`.specify/`, `.github/prompts/`, `.github/agents/` を含む）。
- **FeatureSpec**: `specs/<feature>/spec.md` に配置される feature 単位の仕様書。
- **CopilotSlashCommand**: Copilot Chat から実行する `/speckit.*` コマンド定義（prompt + agent の組）。

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: `uvx ... specify check` と `specify check` がどちらも終了コード 0 で完了する。
- **SC-002**: 初期化後に `.specify/`、`.github/prompts/`、`.github/agents/` が存在する。
- **SC-003**: `create-new-feature.sh --json` が `BRANCH_NAME` と `SPEC_FILE` を返し、実際にファイルが存在する。
- **SC-004**: `check-prerequisites.sh --json --paths-only` が `FEATURE_SPEC`, `IMPL_PLAN`, `TASKS` を JSON で返す。
