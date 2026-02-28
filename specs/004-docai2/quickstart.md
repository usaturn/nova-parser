# Quickstart: docai2の出力品質改善

## 1. 前提
- `.env` に以下を設定
  - `GOOGLE_GENAI_USE_VERTEXAI=true`
  - `VERTEX_AI_API_KEY=<your key>`
  - `DOCUMENT_AI_PROCESSOR=projects/.../locations/.../processors/...`
- （任意）`GOOGLE_APPLICATION_CREDENTIALS` を設定

## 2. 実行
```bash
uv run nova-parser --mode docai2 Images/NAN_067.tif
```

## 3. 期待結果
- `Output/NAN_067.docai2.tsv` が生成される
- 出力TSVに `None` / `null` の文字列が含まれない

## 4. 検証コマンド
```bash
grep -En '\\b(None|null)\\b' Output/NAN_067.docai2.tsv || echo "OK"
```

## 5. 代表エラー
- `DOCUMENT_AI_PROCESSOR` 未設定: 設定例付きエラーが表示される
- 認証失敗: `GOOGLE_APPLICATION_CREDENTIALS` のパスと権限を確認
