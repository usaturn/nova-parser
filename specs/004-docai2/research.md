# Research: docai2の出力品質改善

## Decision 1: 欠損値はTSVで空文字に統一
- Decision: 欠損値のシリアライズは `""` を採用する
- Rationale: 表計算取り込み・後続フィルタで `None`/`null` 文字列がノイズになるため
- Alternatives considered:
  - `null` 文字列を保持: 既存運用で後処理コストが高い
  - `-` 等の記号利用: 真の値 `-` と衝突する

## Decision 2: フィールド順は初出順を採用
- Decision: 複数レコードのキーを走査し、初出順でヘッダー化する
- Rationale: 原資料の見出し順を保持しやすく、可読性が高い
- Alternatives considered:
  - アルファベット順: 日本語列で自然順にならず確認しづらい
  - 固定スキーマ: 未知型への拡張性が低い

## Decision 3: Document AI認証のフォールバック対応
- Decision: `GOOGLE_APPLICATION_CREDENTIALS` が無効パスの場合、一時的に環境変数を外して ADC を試行する
- Rationale: 開発環境での設定崩れを復旧しやすくする
- Alternatives considered:
  - 即時失敗: 原因追跡に時間がかかる
  - 自動で別キー探索: 挙動が不透明になりやすい

## Decision 4: 失敗時は原因を明示する
- Decision: `DOCUMENT_AI_PROCESSOR` 未設定時に設定例を含むエラーを返す
- Rationale: 運用初動の迷いを減らす
- Alternatives considered:
  - 汎用例外のみ: 原因特定に追加調査が必要
