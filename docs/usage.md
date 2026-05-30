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
nova-parser [--mode {plain,structured,structured_tsv,gamedata,schema,docai,docai_plain,schema_propose,extract,crop}] [--schema SCHEMA] [--parallel-files PARALLEL_FILES] [--output-dir OUTPUT_DIR] [--min-card-area MIN] [--max-card-area MAX] [--padding PX] [files ...]
```

| 引数/オプション | 説明 | デフォルト |
|------|------|------|
| `--mode` | 出力モード（`plain`、`structured`、`structured_tsv`、`gamedata`、`schema`、`docai`、`docai_plain`、`schema_propose`、`extract`、`crop`） | `plain` |
| `--schema` | スキーマ定義ファイルのパス（`extract` モード時に必須） | — |
| `--parallel-files` | `docai` / `extract` モードで同時に処理するファイル数（ファイル単位並列） | `1` |
| `--output-dir` | 結果を保存するディレクトリ。未作成の場合は自動作成 | `Output` |
| `--min-card-area` | `crop` モード: カード最小面積比率 | `0.05` |
| `--max-card-area` | `crop` モード: カード最大面積比率 | `0.80` |
| `--padding` | `crop` モード: クロップ時のパディング（px） | `15` |
| `files` | 処理する画像/PDF ファイルまたはディレクトリのパス。`schema_propose` モードでは TSV ファイルを受け取る | — |

- 引数を省略すると、`schema_propose` 以外のモードでは `Images/` ディレクトリ直下のサポート対象画像を全て処理します
- ディレクトリを指定した場合は、その直下にあるサポート対象ファイルだけを処理します
- `schema_propose` モードだけは画像ではなく TSV ファイルを受け取ります
- `--output-dir` を指定した場合、出力ファイル、`extract` キャッシュ、Gemini JSON エラー調査用ファイルは指定先に保存されます。`schema_propose` で TSV 入力を省略した場合も、指定先の `*.docai*.tsv` を走査します
- `extract` モードで `--output-dir` を省略し、かつ入力が単一ディレクトリ（例: `Images/dx3/DX3_EA`）の場合は、そのディレクトリ名を使い `Output/[ディレクトリ名]/`（例: `Output/DX3_EA/`）に出力します。ファイル指定・glob 展開・複数引数・引数省略時は従来どおり `Output/` 直下に出力します
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

# Document AI OCR + 構造化 TSV 出力（4ファイル並列）
uv run nova-parser --mode docai --parallel-files 4 Images/dx3/DX3_EA

# 出力先を指定
uv run nova-parser --output-dir Results --mode docai Images/TNX_OFC_020.tif

# docai TSV からスキーマ提案を生成（既定では Output/ 内の全 docai TSV を走査）
uv run nova-parser --mode schema_propose

# 特定の TSV ファイルのみからスキーマ提案を生成
uv run nova-parser --mode schema_propose Output/TNX_OFC_020.docai.tsv Output/TNX_OFC_037.docai.tsv

# スキーマ準拠で型別 TSV 抽出
uv run nova-parser --mode extract --schema Output/schema.json image1.tif image2.tif

# スキーマ準拠で型別 TSV 抽出（4ファイル並列）
uv run nova-parser --mode extract --parallel-files 4 --schema Output/schema.json Images/dx3/DX3_EA

# Gemini Vision でカード領域を切り出し（必要に応じて Document AI にフォールバック）
uv run nova-parser --mode crop image1.png

# カード面積比率とパディングを調整して切り出し
uv run nova-parser --mode crop --min-card-area 0.03 --max-card-area 0.60 --padding 20 image1.png
```

## 実行ログと性能サマリー

実行ログは標準出力に表示されます。ログファイルへの自動保存は行わないため、保存したい場合はシェルのリダイレクトや `tee` を使ってください。

```bash
uv run nova-parser --mode extract --parallel-files 4 --schema Output/schema.json Images/dx3/DX3_EA 2>&1 | tee perf.log
```

- `plain`、`docai_plain`、`docai`、`extract` では、完了時と実行終了時に性能サマリーが標準出力に表示されます
- `docai` / `extract` で 429 が発生した場合は、失敗したステップ名と待機時間を含む retry 詳細ログが表示されます
- Gemini JSON 解析で `JSONDecodeError` が発生した場合は、1 秒待って 1 回だけ同一リクエストを再試行します
- `実計` は成功した API 呼び出しに加え、失敗した attempt と retry wait を含む実時間ベースの集計です
- `成功計` は成功した API 呼び出しのみを集計した値です

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

この章の `Output/` は未指定時の既定出力先です。`--output-dir` を指定した場合は、指定先ディレクトリに読み替えてください。

### plain モード（デフォルト）

画像を OCR し、Markdown テキストとして出力します。

| 項目 | 内容 |
|------|------|
| 使用モデル | `gemini-3.1-pro-preview` |
| 出力先 | `Output/` ディレクトリ（自動作成） |
| ファイル名 | `{元のファイル名（拡張子なし）}.plain.md` |
| エンコーディング | UTF-8 |
| フォーマット | Markdown |
| 標準出力ログ | `Gemini OCR` の性能サマリー |

例:

- `Images/document.png` → `Output/document.plain.md`
- `Images/photo.jpeg` → `Output/photo.plain.md`

Gemini に以下の指示で OCR を実行します:

- 画像内のテキストを全て抽出
- 元のレイアウトや改行をできるだけ維持
- 表がある場合は Markdown のテーブル形式で出力
- 読み取れない文字は `[?]` と表記

完了時と実行終了時に、`Gemini OCR` の性能サマリーが標準出力に表示されます。

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
| 並列実行 | `--parallel-files` によるファイル単位並列（デフォルト `1`） |
| 標準出力ログ | `DocAI OCR` / `Gemini JSON` の性能サマリー |

例:

- `Images/NAN_067.tif` → `Output/NAN_067.docai.tsv`

```bash
uv run nova-parser --mode docai --parallel-files 4 Images/dx3/DX3_EA
```

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

#### 並列実行とログ

- `--parallel-files` はファイル単位並列です。1ファイル内の OCR と構造化抽出を分割並列するものではありません
- 完了時と実行終了時に `DocAI OCR` / `Gemini JSON` の性能サマリーが標準出力に表示されます
- 同じ stem を持つ入力で出力先 `.docai.tsv` が衝突する場合は、処理開始前にエラーになります

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
| 標準出力ログ | `DocAI OCR` の性能サマリー |

例:

- `Images/NAN_067.tif` → `Output/NAN_067.docai_plain.md`

#### 前提条件・環境変数

docai モードと同じです。認証設定と `DOCUMENT_AI_PROCESSOR` 環境変数が必要です。

#### 処理フロー

1. **Document AI OCR**: 画像を Document AI の OCR プロセッサに送信してテキストを取得（PDF が 15 ページを超える場合は自動的にチャンク分割して処理）
2. **Markdown 出力**: OCR テキストをそのまま Markdown ファイルとして保存

完了時と実行終了時に、`DocAI OCR` の性能サマリーが標準出力に表示されます。

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
| 出力先 | `Output/` ディレクトリ（自動作成）。`--output-dir` 省略かつ単一ディレクトリ入力時は `Output/[ディレクトリ名]/` |
| ファイル名 | `{type_name}.tsv`（スキーマ合致）/ `none_{type_name}.tsv`（スキーマ外） |
| エンコーディング | UTF-8 |
| フォーマット | TSV（タブ区切り、ヘッダ付き） |
| 並列実行 | `--parallel-files` によるファイル単位並列（デフォルト `1`） |
| 標準出力ログ | `DocAI OCR` / `Gemini JSON` の性能サマリー |

例:

```bash
uv run nova-parser --mode extract --schema Output/schema.json Images/TNX_OFC_020.tif
# → Output/武器.tsv, Output/防具.tsv 等

# 単一ディレクトリを4並列で抽出（--output-dir 省略時は Output/DX3_EA/ に出力）
uv run nova-parser --mode extract --parallel-files 4 --schema Output/schema.json Images/dx3/DX3_EA
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
3. **画像単位キャッシュ**: 各画像の抽出結果を `Output/cache/extract/{stem}.json` に保存
4. **型別 TSV 再生成**: 全画像分のキャッシュを集約し、スキーマ上の全型 `{type_name}.tsv` と unmatched の `none_{type_name}.tsv` を staging 経由で再生成し、成功 run の出力集合を `Output/cache/extract/_meta/tsv_manifest.json` に記録

#### 並列実行とログ

- `--parallel-files` はファイル単位並列です。デフォルトは `1` で、`docai` と `extract` でのみ有効です
- 並列実行時も TSV 書き込みは全ファイルの抽出結果を回収した後に行うため、途中失敗時にその run の部分追記を避けます
- 完了時と実行終了時に `DocAI OCR` / `Gemini JSON` の性能サマリーが標準出力に表示されます
- 429 が発生した場合は、失敗したステップ名と retry wait を含む詳細ログが標準出力に表示されます
- Gemini が不正 JSON を返して `JSONDecodeError` になった場合は、1 秒待って 1 回だけ再試行し、それでも失敗した場合に `*.gemini_json_error.json` を残します

#### 再開機能（キャッシュ）

extract モードは画像ごとに Gemini 抽出結果を `Output/cache/extract/{stem}.json` にキャッシュします。途中でエラー停止しても、同じ引数で再実行すれば成功済み画像のキャッシュを自動で再利用し、未処理画像だけを新規抽出します。

- **キャッシュ有効判定（C1 強化）**: 以下の全条件を満たす場合のみヒット。
  - `cache_version`（payload 形式版）
  - スキーマ内容の SHA-256（`schema_hash`）
  - 画像 bytes の SHA-256（`source_sha256`）
  - prompt_fingerprint（`SCHEMA_EXTRACT_PROMPT` + 契約版）
  - model（使用 Gemini モデル）
  - extractor_id（"gemini-extract/v1" 等）
  - result_schema_fingerprint / validator_fingerprint（json_contracts 契約版）
  - JSON shape 検証（`validate_extract_result`）
  いずれかが不一致/破損ならキャッシュミスとして再抽出。**プロンプト・モデル・抽出器変更時の stale リスクを機械的に排除**。
- **プロンプト/モデル/抽出器変更時の運用**: `CACHE_VERSION` の手動 bump は不要（上記 fingerprint が自動で無効化）。`CACHE_VERSION` は payload 形式変更時のみ bump。
- **手動キャッシュクリア**: `Output/cache/extract/` ディレクトリを削除（または該当 `{stem}.json` 削除）
- **画像 stem の重複禁止**: 同じ stem を持つ入力（例: `a.png` と `a.jpg`）はキャッシュキーが衝突するため事前エラーになる
- **実行終了時ログ**: `キャッシュ: ヒット N / 新規 M / ...` の形で内訳を表示

#### TSV 再生成ポリシー

TSV ファイルはキャッシュを元に毎回 current run 基準で再生成します（追記ではありません）。

- **staging 生成**: まず staging ディレクトリに TSV 一式を生成し、生成フェーズで失敗した場合は旧 TSV 群を保持します
- **スキーマに定義された全型** の `{type_name}.tsv` は run ごとに再生成されます。0 件の型でもヘッダ行のみのファイルが作られます
- **unmatched 型** の `none_{type_name}.tsv` は current run に出現した型だけが生成されます
- **stale TSV の整理**: current run に存在しない旧 `{type_name}.tsv` / `none_{type_name}.tsv` は成功 run 後に削除されます
- **manifest**: 直前の成功 run が管理していた TSV 一覧を `Output/cache/extract/_meta/tsv_manifest.json` に保存し、次回 cleanup に使います
- **行の並び順**: 入力画像の指定順で安定しており、並列実行でも順序は保たれます
- **過去 run のデータは保持されません**: 前回 run と今回 run で異なる画像セットを指定した場合、前回分の行は出力されません（再利用したい場合はキャッシュごと保持して同じ引数で実行）

#### 出力形式

各 TSV ファイルは1行目がヘッダ（スキーマの fields + `source`）、2行目以降がデータ行です。

```
名称	ルビ	メーカー	購	隠	攻	受	射	ス	電制	部位	解説	source
撃滅バット	げきめつ	ブラックドラゴン	2/1	8/0	I+1	1	至近	0	10	片手持ち	戦闘にも耐えられるように...	TNX_OFC_020.tif
```

- `source` 列: 抽出元の画像ファイル名
- スキーマに合致しないデータは `none_{type_name}.tsv` に動的なヘッダで出力されます

### crop モード

Gemini Vision でカード領域を検出し、検出できなかった場合は Document AI OCR のブロック座標にフォールバックして、画像内のカード領域を自動切り出しします。近接ブロックのクラスタリングと面積比率フィルタリングにより、テーブルやカードなどのまとまった領域を個別の画像として保存します。

| 項目 | 内容 |
|------|------|
| カード検出 | Gemini Vision（優先） / Google Cloud Document AI OCR ブロック座標（フォールバック） |
| 出力先 | `Output/` ディレクトリ（自動作成） |
| 画像ファイル名 | `{元のファイル名（拡張子なし）}.crop_{NNN}.png`（NNN は 001 から連番） |
| メタデータファイル名 | `{元のファイル名（拡張子なし）}.crop.json` |
| エンコーディング | UTF-8（JSON） |
| フォーマット | PNG（画像）、JSON（メタデータ） |

例:

- `Images/NAN_067.png` → `Output/NAN_067.crop_001.png`, `Output/NAN_067.crop_002.png`, ..., `Output/NAN_067.crop.json`

#### 前提条件・環境変数

- Gemini Vision を使うため、通常の Gemini 系モードと同じ認証設定（`VERTEX_AI_API_KEY` など）が必要です
- Document AI へのフォールバックを使う場合は、`docai` モードと同じ認証設定と `DOCUMENT_AI_PROCESSOR` 環境変数が必要です

#### CLI オプション

| オプション | 型 | デフォルト | 説明 |
|------|------|------|------|
| `--min-card-area` | float | `0.05` | カード候補の最小面積比率（ページ全体に対する割合）。これより小さい領域は除外される |
| `--max-card-area` | float | `0.80` | カード候補の最大面積比率。これより大きい領域は除外される |
| `--padding` | int | `15` | クロップ時に各辺に追加するパディング（ピクセル） |

#### 処理フロー

1. **Gemini Vision 検出**: 画像を Gemini に送り、カード候補の正規化座標を取得
2. **Document AI フォールバック**: Gemini がカードを返さなかった場合のみ Document AI OCR を実行し、ブロック座標を取得
3. **ブロック抽出とクラスタリング**: Document AI フォールバック時は各ブロックの正規化座標をピクセル座標に変換し、近接ブロックを統合
4. **面積フィルタリング**: `--min-card-area` 〜 `--max-card-area` の範囲外の領域を除外
5. **クロップ**: 各候補領域を `--padding` 付きで切り出し、PNG として保存
6. **メタデータ出力**: 全カード情報を JSON ファイルに保存

#### 出力形式（メタデータ JSON）

```json
{
  "source": "NAN_067.png",
  "cards": [
    {
      "index": 1,
      "left": 100,
      "top": 200,
      "right": 500,
      "bottom": 600,
      "confidence": 0.9876,
      "text_snippet": "カード内のテキスト（先頭100文字）...",
      "file": "NAN_067.crop_001.png"
    }
  ]
}
```

| フィールド | 型 | 説明 |
|------|------|------|
| `source` | string | 元の画像ファイル名 |
| `cards[].index` | int | カードの連番（1 始まり） |
| `cards[].left` | int | 左端のピクセル座標 |
| `cards[].top` | int | 上端のピクセル座標 |
| `cards[].right` | int | 右端のピクセル座標 |
| `cards[].bottom` | int | 下端のピクセル座標 |
| `cards[].confidence` | float | Gemini 検出時は `1.0`、Document AI フォールバック時はクラスタ内ブロックの平均信頼度 |
| `cards[].text_snippet` | string | Gemini 検出時はモデルが返したラベル、Document AI フォールバック時は領域内テキストの先頭 100 文字 |
| `cards[].file` | string | 切り出し画像のファイル名 |

#### 制限事項

- **PDF は非対応**: ピクセル座標での切り出しに画像が必要なため、PDF ファイルはスキップされます
- レート制限（429）発生時は指数バックオフで最大 5 回リトライします

## 4段階ワークフロー

複数の画像ファイルからゲームデータを体系的に抽出する推奨ワークフローです。

### Stage 1: サンプル抽出（docai モード）

サンプル画像を `docai` モードで処理し、動的にデータパターンを検出します。

```bash
uv run nova-parser --mode docai --parallel-files 4 sample1.tif sample2.tif sample3.tif
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
uv run nova-parser --mode extract --parallel-files 4 --schema Output/schema.json Images/*.tif
```

## エラー処理

| 状況 | 動作 |
|------|------|
| 指定したファイルが見つからない | エラーメッセージを表示して終了（exit code 1） |
| サポートされていない画像形式 | エラーメッセージを表示して終了（exit code 1） |
| `Images/` に画像がない（引数省略時） | メッセージを表示して正常終了 |
| 出力ファイルが既に存在する | スキップメッセージを表示して次のファイルへ進む（※ `extract` モードは run 毎に TSV を再生成） |
| `docai` モードで出力ファイル名が衝突する | エラーメッセージを表示して終了（同じ stem の複数入力など） |
| `extract` モードで画像 stem が衝突する | エラーメッセージを表示して終了（キャッシュキーが衝突するため） |
| `extract` モードが途中で停止 | 次回実行時に成功済み画像分をキャッシュから再利用して再開 |
| Gemini API レート制限（429） | 指数バックオフで最大 5 回リトライ（初回 30 秒待機、以降倍増） |
