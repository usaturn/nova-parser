# 使い方の詳細

## 実行方法

```bash
# 開発時（uv 経由）
uv run nova-parser

# インストール後
nova-parser
```

## CLI 引数

```
nova-parser [files ...]
```

| 引数 | 説明 |
|------|------|
| `files` | 処理する画像ファイルのパス（省略可、複数指定可） |

- 引数を省略すると、`Images/` ディレクトリ内のサポート対象画像を全て処理します
- 複数ファイルを指定できます

```bash
# Images/ 内の全画像を処理
uv run nova-parser

# 特定のファイルを指定
uv run nova-parser image1.png

# 複数ファイルを指定
uv run nova-parser image1.png image2.jpg image3.webp
```

## サポート画像形式

| 拡張子 | MIME タイプ |
|--------|------------|
| `.png` | `image/png` |
| `.jpg` | `image/jpeg` |
| `.jpeg` | `image/jpeg` |
| `.gif` | `image/gif` |
| `.bmp` | `image/bmp` |
| `.webp` | `image/webp` |
| `.tiff` | `image/tiff` |
| `.tif` | `image/tiff` |

## 出力仕様

| 項目 | 内容 |
|------|------|
| 出力先 | `Output/` ディレクトリ（自動作成） |
| ファイル名 | `{元のファイル名（拡張子なし）}.md` |
| エンコーディング | UTF-8 |
| フォーマット | Markdown |

例:

- `Images/document.png` → `Output/document.md`
- `Images/photo.jpeg` → `Output/photo.md`

## OCR の動作

Gemini に以下の指示で OCR を実行します:

- 画像内のテキストを全て抽出
- 元のレイアウトや改行をできるだけ維持
- 表がある場合は Markdown のテーブル形式で出力
- 読み取れない文字は `[?]` と表記

## エラー処理

| 状況 | 動作 |
|------|------|
| 指定したファイルが見つからない | エラーメッセージを表示して終了（exit code 1） |
| サポートされていない画像形式 | エラーメッセージを表示して終了（exit code 1） |
| `Images/` に画像がない（引数省略時） | メッセージを表示して正常終了 |
