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
nova-parser [--mode {plain,structured,structured_tsv,gamedata,schema,docai,docai_plain,schema_propose,extract}] [--schema SCHEMA] [files ...]
```

| 引数/オプション | 説明 | デフォルト |
|------|------|------|
| `--mode` | 出力モード（`plain`、`structured`、`structured_tsv`、`gamedata`、`schema`、`docai`、`docai_plain`、`schema_propose`、`extract`） | `plain` |
| `--schema` | スキーマ定義ファイルのパス（`extract` モード時に必須） | — |
| `files` | 処理する画像/PDFファイルのパス（省略可、複数指定可） | — |

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

# 構造化抽出 TSV 出力
uv run nova-parser --mode structured_tsv image1.png

# ゲームデータ動的抽出
uv run nova-parser --mode gamedata image1.png

# スキーマ抽出（型名・フィールド名のみ）
uv run nova-parser --mode schema image1.png

# Document AI OCR（Markdown 出力）
uv run nova-parser --mode docai_plain image1.png

# Document AI OCR + 構造化 TSV 出力
uv run nova-parser --mode docai image1.png

# docai TSV からスキーマ提案を生成（Output/ 内の全 docai TSV を走査）
uv run nova-parser --mode schema_propose

# 特定の TSV ファイルのみからスキーマ提案を生成
uv run nova-parser --mode schema_propose Output/TNX_OFC_020.docai.tsv Output/TNX_OFC_037.docai.tsv

# スキーマ準拠で型別 TSV 抽出
uv run nova-parser --mode extract --schema Output/schema.json image1.tif image2.tif
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
| `.pdf` | `application/pdf` |

## 出力モード

### plain モード（デフォルト）

画像を OCR し、Markdown テキストとして出力します。

| 項目 | 内容 |
|------|------|
| 使用モデル | `gemini-3.1-pro-preview` |
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
| 使用モデル | `gemini-3.1-pro-preview`（Pydantic AI 経由） |
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

### structured_tsv モード

structured モードと同じ Pydantic AI による構造化抽出を行い、結果を JSON ではなく TSV（タブ区切り）で出力します。スプレッドシートへの取り込みに適しています。

| 項目 | 内容 |
|------|------|
| 使用モデル | `gemini-3.1-pro-preview`（Pydantic AI 経由） |
| 出力先 | `Output/` ディレクトリ（自動作成） |
| ファイル名 | `{元のファイル名（拡張子なし）}.structured.tsv` |
| エンコーディング | UTF-8 |
| フォーマット | TSV（タブ区切り、カテゴリごとにセクション分割） |

例:

- `Images/NAN_067.tif` → `Output/NAN_067.structured.tsv`

#### 出力形式

カテゴリごとに `## カテゴリ名` ヘッダーで区切られ、各セクションにフィールド名のヘッダー行とデータ行が続きます。該当データがないカテゴリはスキップされます。

```
## 組織
name	classification	sub_organizations	headquarters	description
組織名	企業	下部組織A, 下部組織B	東京	組織の解説テキスト...

## 技能
name	ruby	prerequisite	max_level	timing	target	range	target_value	opposed	description
技能名	ぎのうめい	前提技能名	3	メジャー	単体	10m	対決	回避	技能の解説テキスト...

## 装備
name	ruby	category	type	purchase	concealment	defense_s	defense_p	defense_i	restriction	electric_restriction	slot	description
装備名	そうびめい	カテゴリ	ボディアーマー	-/25	3/-1	3	4	5	0	20	スーツ	装備の解説テキスト...

## ルール
depth	title	body
0	セクション見出し	本文テキスト...
1	サブセクション見出し	サブセクション本文...
```

- `sub_organizations` は `, ` 区切りで結合されます
- `rules` は再帰構造（`sub_sections`）を `depth` 列でフラット化して出力します（0 が最上位）
- `null` 値は空文字として出力されます

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

- Document AI API が有効なプロジェクトに OCR プロセッサが作成済みであること
- `.env` に `DOCUMENT_AI_PROCESSOR` が設定されていること
- 以下のいずれかの方法で認証が設定されていること

#### 認証方法

認証は以下の優先順で解決されます:

1. **`GOOGLE_APPLICATION_CREDENTIALS` 環境変数** — 有効なファイルパスを指している場合に使用
2. **`.secrets/docai-sa.json`** — プロジェクトルートまたはパッケージルートの `.secrets/docai-sa.json` にサービスアカウントキーがある場合にフォールバック
3. **アプリケーションデフォルト認証（ADC）** — 上記いずれも該当しない場合に使用

```bash
# ADC の設定（初回のみ）
gcloud auth application-default login

# またはサービスアカウントキーを配置
cp /path/to/service-account-key.json .secrets/docai-sa.json
```

#### 環境変数

| 変数名 | 説明 | 例 |
|--------|------|------|
| `DOCUMENT_AI_PROCESSOR` | OCR プロセッサのリソース名 | `projects/123456/locations/us/processors/abc123` |
| `GOOGLE_APPLICATION_CREDENTIALS` | サービスアカウントキーのパス（省略可） | `/path/to/credentials.json` |

#### 処理フロー

1. **Document AI OCR**: 画像を Document AI の OCR プロセッサに送信してテキストを取得（PDF が 15 ページを超える場合は自動的にチャンク分割して処理）
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

#### Document AI OCR レスポンスの出力形式

Document AI の OCR プロセッサが返すレスポンス (`Document`) は、テキストを複数の粒度で構造化して提供します。nova-parser では現在 `document.text`（プレーンテキスト全文）のみを使用していますが、以下のデータも取得可能です。

##### トップレベル構造

| フィールド | 型 | 説明 |
|---|---|---|
| `text` | `str` | ページ全体の OCR テキスト（改行含む） |
| `pages` | `list[Page]` | ページごとの詳細情報（画像1枚につき1ページ） |
| `mime_type` | `str` | 入力ドキュメントの MIME タイプ |
| `entities` | `list[Entity]` | 抽出されたエンティティ（OCR プロセッサでは空、カスタムプロセッサで使用） |
| `document_layout` | `DocumentLayout` | レイアウト解析結果（Layout Parser プロセッサで使用） |
| `chunked_document` | `ChunkedDocument` | チャンク分割結果（Layout Parser プロセッサで使用） |

##### Page の階層構造

各ページは以下の4階層でテキスト要素を保持します。上位から下位に向かって粒度が細かくなります。

| 階層 | フィールド | 説明 | 実測件数（NAN_067.tif） |
|---|---|---|---|
| Block | `page.blocks` | 意味的にまとまったテキストブロック | 41 |
| Paragraph | `page.paragraphs` | 段落単位のテキスト | 64 |
| Line | `page.lines` | 行単位のテキスト | 140 |
| Token | `page.tokens` | 単語（形態素）単位のテキスト | 935 |

各要素は共通の `Layout` オブジェクトを持ちます:

| Layout のフィールド | 型 | 説明 |
|---|---|---|
| `text_anchor.text_segments` | `list[TextSegment]` | `document.text` 内の開始・終了インデックス |
| `confidence` | `float` | OCR の信頼度（0.0〜1.0） |
| `bounding_poly.normalized_vertices` | `list[NormalizedVertex]` | 画像上の正規化座標（左上原点、0.0〜1.0） |
| `orientation` | `int` | テキストの向き（1=横書き） |

##### Token の追加情報

| フィールド | 型 | 説明 |
|---|---|---|
| `detected_break.type_` | `int` | 後続の区切り種別（1=スペース、2=改行） |
| `detected_languages` | `list[DetectedLanguage]` | 検出された言語（`language_code`, `confidence`） |
| `style_info` | `StyleInfo` | フォント情報（`font_size`, `bold`, `font_type`） |

##### Page のメタ情報

| フィールド | 型 | 説明 | NAN_067.tif での値 |
|---|---|---|---|
| `dimension` | `Dimension` | 画像サイズ（幅・高さ・単位） | 1659x2409 pixels |
| `detected_languages` | `list[DetectedLanguage]` | ページ全体の検出言語 | ja: 0.907, en: 0.022, zh: 0.018 |
| `image_quality_scores` | `ImageQualityScores` | 画像品質スコア | — |

##### OCR プロセッサで空になるフィールド

以下は OCR プロセッサ (`OCR_PROCESSOR`) では値が返されません。カスタムプロセッサや専用プロセッサで利用可能です。

| フィールド | 利用可能なプロセッサ |
|---|---|
| `page.tables` | Form Parser、Table プロセッサ |
| `page.form_fields` | Form Parser プロセッサ |
| `page.visual_elements` | 特殊プロセッサ |
| `document.entities` | Custom Extraction プロセッサ（[セットアップガイド](./custom-extractor-setup.md)） |
| `document.document_layout` | Layout Parser プロセッサ |
| `document.chunked_document` | Layout Parser プロセッサ |

##### 後処理

Document AI の OCR はプレーンテキスト認識のため、特殊文字が標準文字に置き換えられることがあります。nova-parser では以下の後処理を行っています:

| OCR 出力 | 補正後 | 理由 |
|---|---|---|
| `NOVA` | `N◎VA` | ゲームタイトル「トーキョーN◎VA」の特殊表記 |

### docai_plain モード

Document AI で OCR を行い、結果を Markdown テキストとして出力します。docai モードと異なり、Gemini による構造化抽出は行いません。

| 項目 | 内容 |
|------|------|
| OCR | Google Cloud Document AI（OCR プロセッサ） |
| 出力先 | `Output/` ディレクトリ（自動作成） |
| ファイル名 | `{元のファイル名（拡張子なし）}.docai_plain.md` |
| エンコーディング | UTF-8 |
| フォーマット | Markdown |

例:

- `Images/NAN_067.tif` → `Output/NAN_067.docai_plain.md`

#### 前提条件・環境変数

docai モードと同じです。認証設定と `DOCUMENT_AI_PROCESSOR` 環境変数が必要です。

#### 処理フロー

1. **Document AI OCR**: 画像を Document AI の OCR プロセッサに送信してテキストを取得（PDF が 15 ページを超える場合は自動的にチャンク分割して処理）
2. **Markdown 出力**: OCR テキストをそのまま Markdown ファイルとして保存

### schema_propose モード

`Output/` 内の docai TSV ファイル（`*.docai*.tsv`）を走査し、各 `## 型名` セクションのヘッダ行を解析してスキーマ提案 JSON を自動生成します。Gemini は使用しません。

| 項目 | 内容 |
|------|------|
| 入力 | `Output/*.docai*.tsv`（docai モードの出力ファイル群） |
| 出力先 | `Output/` ディレクトリ |
| ファイル名 | `schema_proposal.json` |
| エンコーディング | UTF-8 |
| フォーマット | JSON（インデント付き） |

例:

```bash
# Output/ 内の全 docai TSV を走査
uv run nova-parser --mode schema_propose

# 特定のファイルのみ指定
uv run nova-parser --mode schema_propose Output/TNX_OFC_020.docai.tsv Output/TNX_OFC_037.docai.tsv
# → Output/schema_proposal.json
```

#### 出力形式

```json
{
  "types": [
    {
      "type_name": "白兵武器",
      "fields": ["名称", "ルビ", "隠", "受", "ス", "購", "攻", "射", "電制", "部位", "解説"],
      "source": "TNX_OFC_020.docai.tsv"
    }
  ]
}
```

- 同一型名が複数ファイルに存在する場合、フィールドは和集合（出現順保持）になります
- `## ` ヘッダのないファイル（手動作成ファイル等）はスキップされます

### extract モード

スキーマ定義ファイル（`schema.json`）に従って、Document AI OCR + Gemini でゲームデータを抽出し、型名ごとに TSV ファイルを出力します。

| 項目 | 内容 |
|------|------|
| OCR | Google Cloud Document AI（OCR プロセッサ） |
| 構造化抽出 | `gemini-3-flash-preview` |
| 出力先 | `Output/` ディレクトリ（自動作成） |
| ファイル名 | `{type_name}.tsv`（スキーマ合致）/ `none_{type_name}.tsv`（スキーマ外） |
| エンコーディング | UTF-8 |
| フォーマット | TSV（タブ区切り、ヘッダ付き） |

例:

```bash
uv run nova-parser --mode extract --schema Output/schema.json Images/TNX_OFC_020.tif
# → Output/武器.tsv, Output/防具.tsv 等
```

#### 前提条件

- docai モードと同じ前提条件（認証設定、`DOCUMENT_AI_PROCESSOR` 環境変数）
- スキーマ定義ファイル（`--schema` で指定）

#### スキーマ定義ファイル

以下の JSON 形式で型名とフィールド一覧を定義します:

```json
{
  "types": [
    {
      "type_name": "武器",
      "fields": ["名称", "ルビ", "メーカー", "購", "隠", "攻", "受", "射", "ス", "電制", "部位", "解説"]
    },
    {
      "type_name": "防具",
      "fields": ["名称", "ルビ", "メーカー", "購", "隠", "防(S/P/I)", "制", "電制", "部位", "解説"]
    }
  ]
}
```

#### 処理フロー

1. **Document AI OCR**: 画像を Document AI の OCR プロセッサに送信してテキストを取得（PDF が 15 ページを超える場合は自動的にチャンク分割して処理）
2. **Gemini スキーマ準拠抽出**: OCR テキストとスキーマ定義を Gemini に送り、スキーマに合致するデータ（`matched_types`）と合致しないデータ（`unmatched_types`）を JSON で抽出
3. **型別 TSV 出力**: 合致データは `{type_name}.tsv` に、非合致データは `none_{type_name}.tsv` に追記

#### 出力形式

各 TSV ファイルは1行目がヘッダ（スキーマの fields + `source`）、2行目以降がデータ行です。複数画像の処理結果は同一ファイルに追記されます。

```
名称	ルビ	メーカー	購	隠	攻	受	射	ス	電制	部位	解説	source
撃滅バット	げきめつ	ブラックドラゴン	2/1	8/0	I+1	1	至近	0	10	片手持ち	戦闘にも耐えられるように...	TNX_OFC_020.tif
```

- `source` 列: 抽出元の画像ファイル名
- スキーマに合致しないデータは `none_{type_name}.tsv` に動的なヘッダで出力されます

## 4段階ワークフロー

複数の画像ファイルからゲームデータを体系的に抽出する推奨ワークフローです。

### Stage 1: サンプル抽出（docai モード）

サンプル画像を `docai` モードで処理し、動的にデータパターンを検出します。

```bash
uv run nova-parser --mode docai sample1.tif sample2.tif sample3.tif
```

### Stage 2: スキーマ提案生成（schema_propose モード）

Stage 1 の出力 TSV からスキーマ案を自動生成します。

```bash
uv run nova-parser --mode schema_propose
# → Output/schema_proposal.json
```

### Stage 3: スキーマ確定（手動）

`schema_proposal.json` を元に、エディタでスキーマを編集・確定します。

- 類似の型を統合（例: 白兵武器 + 射撃武器 → 武器）
- フィールド名の正規化（OCR 誤認識の修正等）
- 不要な型の削除、フィールドの追加

確定したスキーマを `schema.json` として保存します。

### Stage 4: 本番抽出（extract モード）

確定スキーマに従って全画像を処理し、型別 TSV を生成します。

```bash
uv run nova-parser --mode extract --schema Output/schema.json Images/*.tif
```

## エラー処理

| 状況 | 動作 |
|------|------|
| 指定したファイルが見つからない | エラーメッセージを表示して終了（exit code 1） |
| サポートされていない画像形式 | エラーメッセージを表示して終了（exit code 1） |
| `Images/` に画像がない（引数省略時） | メッセージを表示して正常終了 |
| 出力ファイルが既に存在する | スキップメッセージを表示して次のファイルへ進む（※ `extract` モードは既存ファイルに追記） |
| Gemini API レート制限（429） | 指数バックオフで最大 5 回リトライ（初回 30 秒待機、以降倍増） |
