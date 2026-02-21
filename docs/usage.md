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
nova-parser [--mode {plain,structured}] [files ...]
```

| 引数/オプション | 説明 | デフォルト |
|------|------|------|
| `--mode` | 出力モード（`plain` または `structured`） | `plain` |
| `files` | 処理する画像ファイルのパス（省略可、複数指定可） | — |

- 引数を省略すると、`Images/` ディレクトリ内のサポート対象画像を全て処理します
- 複数ファイルを指定できます

```bash
# Images/ 内の全画像を OCR（Markdown 出力）
uv run nova-parser

# 構造化抽出モード（JSON 出力）
uv run nova-parser --mode structured

# 特定のファイルを指定
uv run nova-parser image1.png

# 特定のファイルを構造化抽出
uv run nova-parser --mode structured image1.png image2.tif
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

## 出力モード

### plain モード（デフォルト）

画像を OCR し、Markdown テキストとして出力します。

| 項目 | 内容 |
|------|------|
| 出力先 | `Output/` ディレクトリ（自動作成） |
| ファイル名 | `{元のファイル名（拡張子なし）}.plain.md` |
| エンコーディング | UTF-8 |
| フォーマット | Markdown |

例:

- `Images/document.png` → `Output/document.plain.md`
- `Images/photo.jpeg` → `Output/photo.plain.md`

Gemini に以下の指示で OCR を実行します:

- 画像内のテキストを全て抽出
- 元のレイアウトや改行をできるだけ維持
- 表がある場合は Markdown のテーブル形式で出力
- 読み取れない文字は `[?]` と表記

### structured モード

Pydantic AI を使い、画像からゲームデータを構造化抽出して JSON として出力します。

| 項目 | 内容 |
|------|------|
| 出力先 | `Output/` ディレクトリ（自動作成） |
| ファイル名 | `{元のファイル名（拡張子なし）}.structured.json` |
| エンコーディング | UTF-8 |
| フォーマット | JSON（インデント付き） |

例:

- `Images/NAN_067.tif` → `Output/NAN_067.structured.json`

#### 抽出されるデータ構造

出力 JSON は以下の 4 カテゴリで構成されます。該当データがないカテゴリは空配列になります。

| カテゴリ | フィールド名 | 説明 |
|------|------|------|
| 組織 | `organizations` | 組織名・分類・下部組織・本部・解説 |
| 技能・特技 | `skills` | 技能名・ふりがな・前提技能・上限・タイミング・対象・射程・目標値・対決・解説 |
| 装備 | `equipment` | 装備名・ふりがな・カテゴリ・タイプ・購入価格・隠匿・防御力(S/P/I)・制・電制・部位・解説 |
| ルール説明文 | `rules` | 見出し・本文・子セクション（再帰構造） |

#### JSON 出力例

```json
{
  "source_file": "NAN_067.tif",
  "organizations": [],
  "skills": [
    {
      "name": "技能名",
      "ruby": "ぎのうめい",
      "prerequisite": "前提技能名",
      "max_level": 3,
      "timing": "メジャー",
      "target": "単体",
      "range": "10m",
      "target_value": "対決",
      "opposed": "回避",
      "description": "技能の解説テキスト"
    }
  ],
  "equipment": [],
  "rules": []
}
```

## エラー処理

| 状況 | 動作 |
|------|------|
| 指定したファイルが見つからない | エラーメッセージを表示して終了（exit code 1） |
| サポートされていない画像形式 | エラーメッセージを表示して終了（exit code 1） |
| `Images/` に画像がない（引数省略時） | メッセージを表示して正常終了 |
| 出力ファイルが既に存在する | スキップメッセージを表示して次のファイルへ進む |
