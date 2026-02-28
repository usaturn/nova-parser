# Data Model: docai2の出力品質改善

## ExtractResult
- 説明: Gemini 構造化抽出のトップレベル
- フィールド:
  - `types`: `TypeBlock[]`
  - `source_file`: `str`（実行時付与）

## TypeBlock
- 説明: 同種データのグループ
- フィールド:
  - `type_name`: `str`
  - `items`: `ItemRecord[]`

## ItemRecord
- 説明: 1行分のデータ
- フィールド:
  - キー: `str`（原資料の見出し）
  - 値: `str | None`（TSV化時に `None` は空文字へ正規化）

## TSVSection
- 説明: 出力TSV上の型単位セクション
- 構成:
  - ヘッダー行: `## {type_name}`
  - 列名行: 初出順に収集したキー配列
  - データ行: 各 `ItemRecord` の値

## Validation Rules
- `types` が空の場合、空TSVを返す
- `items` が空の `TypeBlock` は出力しない
- 欠損値は必ず空文字に変換する
- キー順序は初出順で固定する
