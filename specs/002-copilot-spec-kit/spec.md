# Feature Specification: Devcontainer 上で Spec Kit を Copilot 運用可能にする

**Feature Branch**: `002-copilot-spec-kit`  
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

### User Story 1 - セットアップ完了を再現できる (Priority: P1)

開発者として、devcontainer 内で Spec Kit を利用可能な状態にし、同じ手順を別メンバーが再現できるようにしたい。

**Why this priority**: セットアップが再現できないと以降の仕様駆動フローを誰も開始できないため。

**Independent Test**: 新規メンバーが手順書に従い、環境準備からツールの利用可能状態まで到達できれば合格。

**Acceptance Scenarios**:

1. **Given** devcontainer が起動している、**When** セットアップ手順を実行する、**Then** Spec Kit を利用可能であると確認できる。
2. **Given** セットアップ完了後、**When** 同じ手順を再実行する、**Then** 失敗せず同等の結果を得られる。

---

### User Story 2 - 仕様作成フローを開始できる (Priority: P2)

開発者として、Spec Kit の feature 開始フローを実行し、仕様書の雛形を生成して作業を始めたい。

**Why this priority**: 実際の開発価値は「仕様を起点に進められること」にあるため。

**Independent Test**: feature 開始後に feature 専用の仕様ファイルが生成され、編集可能な状態になれば合格。

**Acceptance Scenarios**:

1. **Given** ツールが利用可能な状態、**When** feature 開始手順を実行する、**Then** feature ブランチと仕様書が生成される。

---

### User Story 3 - Copilot Chat 連携で運用できる (Priority: P3)

開発者として、VS Code の Copilot Chat から Spec Kit コマンドを実行し、仕様→計画→タスクの流れに接続したい。

**Why this priority**: 実運用では CLI だけでなく Chat 連携が必要で、チーム利用性に直結するため。

**Independent Test**: Copilot Chat で対象コマンドを入力し、想定するエージェント応答が開始すれば合格。

**Acceptance Scenarios**:

1. **Given** 連携定義ファイルが存在する、**When** Copilot Chat で Spec Kit コマンドを実行する、**Then** 該当フローが開始される。

---

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- 既存リポジトリに未コミット差分がある場合でも、セットアップ対象差分を識別して作業できること。
- feature ブランチ命名規則に合わない状態では前提チェックが失敗するため、開始手順で自動的に規約へ誘導されること。
- Copilot が一時的に利用不可でも、CLI 側検証までは完了でき、手動再試行で連携確認できること。

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: 開発者は devcontainer 内で Spec Kit のセットアップ手順を完了できなければならない。
- **FR-002**: セットアップ後、開発者はツール利用可否を明示的に確認できなければならない。
- **FR-003**: 開発者は feature 開始フローを実行し、feature 専用仕様書を生成できなければならない。
- **FR-004**: システムは Copilot Chat から利用するコマンド定義を提供しなければならない。
- **FR-005**: システムは仕様作成フローの前提条件チェックを実行し、未達時は理由を示さなければならない。
- **FR-006**: システムは手順の再実行時に結果の一貫性を保たなければならない。
- **FR-007**: システムは既存 CLI 利用体験を維持し、既存機能を阻害してはならない。

### Key Entities *(include if feature involves data)*

- **SpecKitWorkspaceState**: セットアップ後の作業状態を表す概念。利用可否、初期化有無、前提チェック結果を持つ。
- **FeatureDefinition**: feature ごとの識別情報。連番、短縮名、仕様ファイルパスを持つ。
- **CopilotCommandMapping**: Chat コマンドと処理エージェントの対応情報。

## Constitution Alignment *(mandatory)*

- **CA-001**: Python 関連の実行手順は `uv` 系コマンドで統一する。
- **CA-002**: 既存 CLI の実行体験と既存モード互換を維持する。
- **CA-003**: 各ステップで成功/失敗判定可能な検証方法を記述する。
- **CA-004**: 変更する運用文書は日本語で更新する。
- **CA-005**: 認証情報をリポジトリへ含めない運用を維持する。

## Assumptions

- VS Code の GitHub Copilot は利用可能な状態である。
- 外部ネットワークに接続でき、初回セットアップに必要な取得処理を実行できる。
- 本 feature では新規アプリ機能の追加ではなく、開発運用フローの確立を目的とする。

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: セットアップ手順を 5 分以内に完了できる。
- **SC-002**: feature 開始後 1 分以内に feature 専用仕様書の初期ファイルを生成できる。
- **SC-003**: 前提チェックは実行ごとに明示的な成功または失敗理由を返す。
- **SC-004**: チーム内の 2 名以上が同手順で再現し、同等の結果を得られる。
