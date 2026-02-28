# Feature Specification: Devcontainer で Spec Kit を Copilot 運用に載せる

**Feature Branch**: `003-copilot-spec-kit`  
**Created**: 2026-02-28  
**Status**: Closed  
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

### User Story 1 - セットアップを完了できる (Priority: P1)

開発者として、devcontainer 上で Spec Kit を使える状態にし、仕様駆動の作業を開始できるようにしたい。

**Why this priority**: ここが未完了だと以降の仕様作成・計画作成に進めないため。

**Independent Test**: 事前条件を満たした環境で導入手順を実行し、ツール利用可能状態を確認できれば完了と判定する。

**Acceptance Scenarios**:

1. **Given** devcontainer が起動している、**When** セットアップ手順を実行する、**Then** Spec Kit を利用可能と確認できる。
2. **Given** セットアップ済み環境、**When** 同手順を再実行する、**Then** 同等の成功結果が得られる。

---

### User Story 2 - feature 仕様を起票できる (Priority: P2)

開発者として、新しい feature を開始し、仕様ファイルを生成して記述を始めたい。

**Why this priority**: セットアップ完了だけでは開発が始まらないため、実際の起票導線を確立する必要がある。

**Independent Test**: feature 開始フローを実行し、専用ブランチと仕様ファイルが生成されれば完了と判定する。

**Acceptance Scenarios**:

1. **Given** Spec Kit が利用可能な状態、**When** feature 開始手順を実行する、**Then** feature 番号付きブランチと仕様ファイルが作成される。

---

### User Story 3 - Copilot Chat で実行できる (Priority: P3)

開発者として、Copilot Chat の slash command から Spec Kit フローを開始し、チーム標準の運用に乗せたい。

**Why this priority**: 実運用では Chat 導線が中心になるため、CLI と同等に利用できることが必要。

**Independent Test**: Copilot Chat で対象コマンドを実行し、対応する処理が開始されることを確認できれば完了と判定する。

**Acceptance Scenarios**:

1. **Given** コマンド定義が有効な状態、**When** Copilot Chat で slash command を実行する、**Then** 仕様作成フローの応答が開始される。

---

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- 既存リポジトリに差分がある状態でも、追加された Spec Kit 関連差分を識別して運用できること。
- feature ブランチ規約に合致しない場合、開始前チェックで明確な理由を返して停止すること。
- Copilot が一時的に利用不可でも、CLI 側のセットアップ検証は独立して完了できること。

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: 開発者は devcontainer 環境で Spec Kit 利用開始まで完了できなければならない。
- **FR-002**: システムはセットアップ可否を明示的に確認できる結果を提供しなければならない。
- **FR-003**: 開発者は feature 開始フローを実行し、feature 専用仕様書を生成できなければならない。
- **FR-004**: システムは前提条件未達時に、失敗理由を利用者が理解できる形で提示しなければならない。
- **FR-005**: システムは Copilot Chat からの実行導線を提供しなければならない。
- **FR-006**: システムは同一手順の再実行で一貫した結果を返さなければならない。
- **FR-007**: 既存の `nova-parser` 実行体験を阻害してはならない。

### Key Entities *(include if feature involves data)*

- **WorkspaceState**: 導入状態を表す単位。セットアップ済みか、前提チェック状態、再実行可否を持つ。
- **FeatureTicket**: feature の識別単位。番号、短縮名、ブランチ名、仕様ファイルパスを持つ。
- **ChatCommandRoute**: Copilot Chat コマンドと処理フローの対応情報を表す。

## Constitution Alignment *(mandatory)*

- **CA-001**: Python 関連手順は `uv` 系コマンドで統一する。
- **CA-002**: 既存 CLI の後方互換を維持する。
- **CA-003**: 検証手順は成功/失敗を判定可能な形式で記述する。
- **CA-004**: 関連ドキュメントは日本語で更新する。
- **CA-005**: 機密情報をリポジトリ差分へ含めない。

## Assumptions

- VS Code の Copilot 利用権限とサインイン状態は有効である。
- ネットワーク接続により導入に必要な取得処理を実行できる。
- 本 feature の対象は開発運用フローであり、アプリ機能追加は含まない。

## Scope Boundary

### In Scope

- Spec Kit の導入・初期化・前提チェックの手順確立
- feature 起票（spec/plan/tasks 作成）導線の整備
- Copilot Chat 連携開始条件の明文化

### Out of Scope

- `nova-parser` の OCR/抽出ロジック変更
- 新規 API や UI 機能の実装
- 本番運用向け認証・権限制御の追加実装

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: セットアップ担当者が 5 分以内に利用可能状態へ到達できる。
- **SC-002**: feature 開始操作から 1 分以内に仕様ファイル生成が完了する。
- **SC-003**: 前提チェックは毎回、成功または失敗理由を明示する。
- **SC-004**: 少なくとも 2 名が同手順で同等結果を再現できる。
