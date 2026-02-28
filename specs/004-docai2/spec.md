# Feature Specification: docai2の出力品質改善

**Feature Branch**: `004-docai2`  
**Created**: 2026-02-28  
**Status**: Draft  
**Input**: User description: "docai2の出力品質改善"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - TSV欠損値の安定化 (Priority: P1)

データ整形担当者として、`docai2` 出力TSVで欠損値が `None` や `null` として混入せず、常に空文字として出力されてほしい。これによりスプレッドシート取り込み時の後処理を不要にしたい。

**Why this priority**: 下流処理で最も実害が大きい不具合（型崩れ・フィルタ誤判定）を直接防ぐため。

**Independent Test**: 欠損値を含む入力画像で `uv run nova-parser --mode docai2 <file>` を実行し、出力TSVに `None` / `null` が含まれないことを確認できる。

**Acceptance Scenarios**:

1. **Given** 欠損値を含む抽出結果、**When** TSVを生成する、**Then** 欠損セルは空文字で出力される
2. **Given** 既存の正常データ、**When** TSVを生成する、**Then** 非欠損セルの文字列値は従来どおり保持される

---

### User Story 2 - 表見出し準拠の構造化抽出 (Priority: P2)

データ監修者として、出力JSON/TSVのキー名が画像の表見出しと一致してほしい。これにより原本との照合を容易にしたい。

**Why this priority**: データの信頼性とレビュー速度に直結するため。

**Independent Test**: 代表画像で抽出し、出力キーをOCRテキストまたは原画像の見出しと突合して一致率を確認できる。

**Acceptance Scenarios**:

1. **Given** 見出し付き表を含むページ、**When** `docai2` で抽出する、**Then** 出力キーは表見出しに準拠する
2. **Given** 既知型（例: 白兵武器）以外の表、**When** 抽出する、**Then** 見出しベースで型名・フィールドが定義される

---

### User Story 3 - 実行時エラーの明確化 (Priority: P3)

運用者として、Document AI 設定不備時に原因が即座にわかるエラーメッセージがほしい。これにより復旧時間を短縮したい。

**Why this priority**: 実行不能時の調査コスト削減に有効だが、出力品質そのものより優先度は低いため。

**Independent Test**: `DOCUMENT_AI_PROCESSOR` 未設定環境で実行し、具体的な設定例を含むエラーが表示されることを確認できる。

**Acceptance Scenarios**:

1. **Given** `DOCUMENT_AI_PROCESSOR` 未設定、**When** `docai2` を実行する、**Then** 設定必須であることと設定例が表示される

### Edge Cases

- OCR結果にゲームデータが存在しない場合、出力は空文字（空TSV）とし、異常終了しない
- `types` が配列形式で返る場合でも、内部で正規化して処理できる
- 列見出しの順序が行ごとに一部異なる場合、TSVヘッダーは初出順で一貫した順序を維持する
- `GOOGLE_APPLICATION_CREDENTIALS` が無効パスを指す場合、ADCフォールバックを試行する

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: システムは `docai2` モードで欠損値を常に空文字として出力しなければならない
- **FR-002**: システムは `docai2` モードの出力に `None` および `null` の文字列表現を含めてはならない
- **FR-003**: システムは抽出キー名に画像由来の表見出しを優先採用しなければならない
- **FR-004**: システムは未知データ型を検出した場合でも、型名とフィールドを動的定義して抽出できなければならない
- **FR-005**: システムは `DOCUMENT_AI_PROCESSOR` 未設定時に、設定例付きの明確なエラーを提示しなければならない
- **FR-006**: システムは項目ごとにフィールド数が異なる場合でも、TSVを破綻なく出力しなければならない

### Key Entities *(include if feature involves data)*

- **ExtractResult**: Geminiの構造化抽出結果。`types` 配列を持つ
- **TypeBlock**: データ型単位のブロック。`type_name` と `items` を持つ
- **ItemRecord**: 各行データ。キーは見出し名、値は文字列または欠損
- **TSVSection**: `## type_name` ヘッダー、列名行、データ行から構成される出力単位

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `docai2` の代表サンプル10件で、出力TSV中の `None` / `null` 出現回数が0件
- **SC-002**: 代表サンプル10件で、表見出しとのキー一致率が95%以上
- **SC-003**: `DOCUMENT_AI_PROCESSOR` 未設定時、原因と設定例を含むエラーが1回の実行で確認できる
- **SC-004**: 既存 `docai2` 成功ケースで実行失敗率が増加しない（回帰なし）
