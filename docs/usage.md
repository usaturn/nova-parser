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
nova-parser [--mode {plain,structured,gamedata,schema,docai}] [files ...]
```

| 引数/オプション | 説明 | デフォルト |
|------|------|------|
| `--mode` | 出力モード（`plain`、`structured`、`gamedata`、`schema`、`docai`） | `plain` |
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

# ゲームデータ動的抽出
uv run nova-parser --mode gamedata image1.png

# スキーマ抽出（型名・フィールド名のみ）
uv run nova-parser --mode schema image1.png

# Document AI OCR + 構造化 TSV 出力
uv run nova-parser --mode docai image1.png
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

### gamedata モード

画像からゲームデータの型を動的に発見・抽出して JSON として出力します。structured モードが固定の 4 カテゴリで抽出するのに対し、gamedata モードは画像の内容に応じて型名やフィールドを自動的に判別します。

| 項目 | 内容 |
|------|------|
| 使用モデル | `gemini-3-flash-preview` |
| 出力先 | `Output/` ディレクトリ（自動作成） |
| ファイル名 | `{元のファイル名（拡張子なし）}.gamedata.json` |
| エンコーディング | UTF-8 |
| フォーマット | JSON（インデント付き） |

例:

- `Images/TNX_OFC_020.tif` → `Output/TNX_OFC_020.gamedata.json`

#### 動的型発見

プロンプトに以下のデータ型をパターン例として与えますが、これらに限定されません:

- **スキル**: 名称, ルビ, 技能, 上限, タイミング, 対象, 射程, 目標値, 対決, 解説
- **防具**: 名称, ルビ, 購, 隠, 防S, 防P, 防I, 制, 電制, 部位, 解説
- **サービス**: 名称, ルビ, 購, 隠, 電制, 部位, 解説

画像に上記以外のデータ型（武器、サイバーウェア、ヴィークル等）がある場合、Gemini が適切な型名とフィールドを自動定義して抽出します。

#### JSON 出力例

```json
{
  "types": [
    {
      "type_name": "白兵武器",
      "items": [
        {
          "名称": "撃滅バット",
          "ルビ": "げきめつ",
          "購": "2/1",
          "隠": "8/0",
          "攻": "I+1",
          "受": "1",
          "射": "至近",
          "ス": "0",
          "電制": "10",
          "部位": "片手持ち",
          "解説": "戦闘にも耐えられるように作られた、野球用の金属バット。"
        }
      ]
    }
  ],
  "source_file": "TNX_OFC_020.tif"
}
```

該当するゲームデータがない画像の場合、`types` は空配列 `[]` になります。

### schema モード

画像からゲームデータの**型名とフィールド名のみ**を抽出し、タブ区切り（TSV）で出力します。データ本体は抽出しないため、画像にどんなデータ型が存在するかを素早く把握できます。

| 項目 | 内容 |
|------|------|
| 使用モデル | `gemini-3-flash-preview` |
| 出力先 | `Output/` ディレクトリ（自動作成） |
| ファイル名 | `{元のファイル名（拡張子なし）}.schema.tsv` |
| エンコーディング | UTF-8 |
| フォーマット | TSV（タブ区切り） |

例:

- `Images/NAN_067.tif` → `Output/NAN_067.schema.tsv`

#### 出力形式

各行が1つのデータ型を表し、先頭が型名、以降がフィールド名です:

```
スキル	名称	ルビ	技能	上限	タイミング	対象	射程	目標値	対決	解説
防具	名称	ルビ	購	隠	防S	防P	防I	制	電制	部位	解説
サービス	名称	ルビ	購	隠	電制	部位	解説
```

該当するゲームデータがない画像の場合、出力ファイルは空になります。

### docai モード

Google Cloud Document AI で OCR を行い、その結果を Gemini で構造化抽出して、同種の項目パターンごとに TSV 出力します。Gemini に直接画像を送る他モードと異なり、Document AI の OCR エンジンを使用します。

| 項目 | 内容 |
|------|------|
| OCR | Google Cloud Document AI（OCR プロセッサ） |
| 構造化抽出 | `gemini-3-flash-preview` |
| 出力先 | `Output/` ディレクトリ（自動作成） |
| ファイル名 | `{元のファイル名（拡張子なし）}.docai.tsv` |
| エンコーディング | UTF-8 |
| フォーマット | TSV（タブ区切り、パターン種別ごとにセクション分割） |

例:

- `Images/NAN_067.tif` → `Output/NAN_067.docai.tsv`

#### 前提条件

- Google Cloud のアプリケーションデフォルト認証（ADC）が設定されていること
- Document AI API が有効なプロジェクトに OCR プロセッサが作成済みであること
- `.env` に `DOCUMENT_AI_PROCESSOR` が設定されていること

```bash
# ADC の設定（初回のみ）
gcloud auth application-default login

# OCR プロセッサの作成（初回のみ、Google Cloud Console からも可能）
# 作成後、プロセッサのリソース名を .env に設定する
```

#### 環境変数

| 変数名 | 説明 | 例 |
|--------|------|------|
| `DOCUMENT_AI_PROCESSOR` | OCR プロセッサのリソース名 | `projects/123456/locations/us/processors/abc123` |

#### 処理フロー

1. **Document AI OCR**: 画像を Document AI の OCR プロセッサに送信してテキストを取得
2. **Gemini 構造化抽出**: OCR テキストを Gemini に送り、ゲームデータを JSON 形式で抽出
3. **TSV 出力**: 抽出されたデータを同種パターンごとにヘッダー付き TSV に変換

#### 出力形式

パターン種別ごとに `## 型名` ヘッダーで区切られ、各セクションにフィールド名のヘッダー行とデータ行が続きます:

```
## スキル
名称	ルビ	技能	上限	タイミング	対象	射程	目標値	対決	解説
フェスラー国境警備隊	こっきょうけいびたい	なし	4	常時	自身	なし	なし	なし	解説テキスト...

## 防具
名称	ルビ	購	隠	防S	防P	防I	制	電制	部位	解説
ロイヤルガード		-/25	3/-1	3	4	5	0	20	スーツ	解説テキスト...
```

該当するゲームデータがない画像の場合、出力ファイルは空になります。

## エラー処理

| 状況 | 動作 |
|------|------|
| 指定したファイルが見つからない | エラーメッセージを表示して終了（exit code 1） |
| サポートされていない画像形式 | エラーメッセージを表示して終了（exit code 1） |
| `Images/` に画像がない（引数省略時） | メッセージを表示して正常終了 |
| 出力ファイルが既に存在する | スキップメッセージを表示して次のファイルへ進む |
