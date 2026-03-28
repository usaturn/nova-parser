# CUSTOM_EXTRACTION_PROCESSOR セットアップガイド

## このドキュメントの位置づけ

このガイドは [Document AI 活用方針](./documentai-trpg-card-strategy.md) の「中期の理想解」で述べている `CUSTOM_EXTRACTION_PROCESSOR` を、実際にセットアップ・運用するための手順書です。

- 方針書（strategy doc）= **なぜ** Custom Extractor を選ぶのか（比較分析・判断根拠）
- 本ガイド = **どうやって** 構築・運用するか（具体的手順・設定値・コード例）

判断根拠が必要な場面では strategy doc へのリンクで参照します。

## 操作手段の整理

> **重要**: `gcloud` CLI に Document AI 専用コマンドは存在しません。

Document AI の操作は **Console GUI を主手順**、**REST API / Python SDK を補助・自動化手段** として使い分けます。

| Step | 主手順 | 補助 | 備考 |
|------|--------|------|------|
| 前提条件（API 有効化） | gcloud CLI | Console | `gcloud services enable` が使える唯一の箇所 |
| Step 1: カード切り出し | Python スクリプト | — | 画像処理のため |
| Step 2: プロセッサ作成 | Console | REST API, Python SDK | 初回 1 回の操作 |
| Step 3: スキーマ定義 | Console | REST API, Python SDK | GUI で確認しながら設定 |
| Step 4: データ準備・インポート | Console | REST API, Python SDK | ドラッグ&ドロップ |
| Step 5: ラベル付け | Console（必須） | JSON import | GUI 以外に選択肢なし |
| Step 6: トレーニング | Console | REST API, Python SDK | ワンクリック |
| Step 7: 評価・改善 | Console | — | GUI の評価画面 |
| Step 8: デプロイ | Console | REST API, Python SDK | 等価 |
| Step 9: 推論（統合） | Python SDK | REST API | nova-parser への統合 |

## 前提条件

### GCP プロジェクトと API 有効化

```bash
# Document AI API を有効化
gcloud services enable documentai.googleapis.com

# Cloud Storage API を有効化（トレーニングデータ格納用）
gcloud services enable storage.googleapis.com
```

### 必要な IAM ロール

| ロール | 用途 |
|--------|------|
| `roles/documentai.admin` | プロセッサの作成・管理・トレーニング |
| `roles/storage.admin` | トレーニングデータの Cloud Storage 管理 |

```bash
# IAM ロールの付与
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:YOUR_EMAIL" \
  --role="roles/documentai.admin"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:YOUR_EMAIL" \
  --role="roles/storage.admin"
```

### 認証設定

nova-parser の認証設定については [使い方の詳細 > 認証方法](./usage.md#認証方法) を参照してください。Custom Extractor でも同じ認証フローが使えます。

### Python SDK のインストール

nova-parser の依存に `google-cloud-documentai>=3.10.0` が含まれています。

```bash
# nova-parser の依存として自動インストールされる
uv sync

# 個別にインストールする場合
uv add google-cloud-documentai
```

## Step 1: カード領域の切り出し方針

> この Step は [strategy doc の「理想アーキテクチャ > 推奨構成」](./documentai-trpg-card-strategy.md#推奨構成) に対応します。

ページ画像にはカード以外の本文が混在します。Custom Extractor に渡す前に、カード領域だけを切り出すことで精度が向上します。

### 方針の選び分け

| 方針 | 概要 | 適した場面 |
|------|------|------------|
| A: 手動切り出し | 画像編集ツールでカード領域を手動で切り出す | サンプル数が少ない初期検証 |
| B: OCR_PROCESSOR の bounding_poly で自動切り出し | OCR 結果の座標情報からカード領域を推定・切り出す | カードの配置パターンが安定している場合 |
| C: 切り出さずページ全体を渡す | ページ画像をそのまま Custom Extractor に渡す | まず動かしたい場合（次善策） |

### 方針 A: 手動切り出し

最もシンプルな方法です。画像編集ツールや Python スクリプトでカード領域を矩形で切り出します。

```python
from PIL import Image

img = Image.open("page.tif")

# カード領域の座標を手動で指定（左, 上, 右, 下）
card_region = (100, 200, 800, 600)
card_img = img.crop(card_region)
card_img.save("card_001.png")
```

### 方針 B: OCR_PROCESSOR の bounding_poly で自動切り出し

nova-parser の既存 OCR パイプラインが返す `bounding_poly` 情報を使い、カード領域を推定します。

```python
from google.cloud import documentai_v1 as documentai
from PIL import Image

def extract_card_regions(document: documentai.Document, page_index: int = 0):
    """OCR 結果の block 座標からカード領域候補を抽出する"""
    page = document.pages[page_index]
    width = page.dimension.width
    height = page.dimension.height

    regions = []
    for block in page.blocks:
        vertices = block.layout.bounding_poly.normalized_vertices
        # 正規化座標をピクセル座標に変換
        left = int(vertices[0].x * width)
        top = int(vertices[0].y * height)
        right = int(vertices[2].x * width)
        bottom = int(vertices[2].y * height)
        regions.append((left, top, right, bottom))

    return regions
```

実際のカード領域判定は、block の密度・間隔・サイズなどのヒューリスティクスで行います。この部分はデータに応じたチューニングが必要です。

### 方針 C: 切り出さずページ全体を渡す

ページ全体を Custom Extractor に渡し、parent-child entities の反復でカードを学習させます。切り出し処理が不要な反面、本文ノイズの影響を受けます。

## Step 2: プロセッサの作成

| 操作手段 | 対応状況 |
|----------|----------|
| Console | 主手順（後述） |
| REST API | `POST /v1/projects/{project}/locations/{location}/processors` |
| Python SDK | `DocumentProcessorServiceClient.create_processor()` |

### Console での作成手順

1. [Document AI Workbench](https://console.cloud.google.com/ai/document-ai/workbench) を開く
2. **Custom Extractor** の「Create processor」を選択
3. プロセッサ名を入力（例: `trpg-card-extractor`）
4. リージョンを選択（`us` または `eu`）
5. ストレージオプション: **Google-managed storage** を選択（推奨）
6. 「Create」をクリック

### REST API での作成

```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://us-documentai.googleapis.com/v1/projects/${PROJECT_ID}/locations/us/processors" \
  -d '{
    "display_name": "trpg-card-extractor",
    "type": "CUSTOM_EXTRACTION_PROCESSOR"
  }'
```

レスポンスからプロセッサのリソース名を記録します:

```
projects/{PROJECT_NUMBER}/locations/us/processors/{PROCESSOR_ID}
```

### Python SDK での作成

```python
from google.api_core.client_options import ClientOptions
from google.cloud import documentai_v1 as documentai

def create_custom_extractor(project_id: str, location: str = "us"):
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    client = documentai.DocumentProcessorServiceClient(client_options=opts)

    parent = client.common_location_path(project_id, location)
    processor = client.create_processor(
        parent=parent,
        processor=documentai.Processor(
            display_name="trpg-card-extractor",
            type_="CUSTOM_EXTRACTION_PROCESSOR",
        ),
    )
    print(f"プロセッサ作成完了: {processor.name}")
    return processor
```

## Step 3: スキーマ定義

| 操作手段 | 対応状況 |
|----------|----------|
| Console | 主手順（Get Started タブ） |
| REST API | `PATCH /v1beta3/{datasetSchema.name}` |
| Python SDK | `dataset.update_dataset_schema()` |

### スキーマ設計

> スキーマの設計意図については [strategy doc の「推奨 schema 例」](./documentai-trpg-card-strategy.md#推奨-schema-例) を参照してください。

`game_card` を parent entity、各フィールドを child entity として定義します。

| 階層 | ラベル名 | データ型 | Occurrence | 説明 |
|------|----------|----------|------------|------|
| parent | `game_card` | — | Optional Multiple | 1 枚のカードに対応。ページ内に複数存在し得る |
| child | `type_name` | Plain Text | Required Once | カード種別（例: スキル、防具、白兵武器） |
| child | `name` | Plain Text | Required Once | 項目名称 |
| child | `ruby` | Plain Text | Optional Once | ふりがな |
| child | `skill` | Plain Text | Optional Once | 使用技能 |
| child | `timing` | Plain Text | Optional Once | タイミング（メジャー、マイナー等） |
| child | `target` | Plain Text | Optional Once | 対象 |
| child | `range` | Plain Text | Optional Once | 射程 |
| child | `cost` | Plain Text | Optional Once | コスト・購入価格 |
| child | `limit` | Plain Text | Optional Once | 制限・上限 |
| child | `description` | Plain Text | Optional Once | 解説テキスト |

### field description の書き方

field description は抽出精度に影響します。TRPG カードでは類似フィールドが多いため、各フィールドが何を指すか明確に記述します。

| ラベル名 | description 例 |
|----------|----------------|
| `type_name` | カードの種別名。ヘッダーや枠の種類で判別する（例: スキル、防具、サービス） |
| `name` | データ項目の固有名称。カード内で最も大きく表示される文字列 |
| `ruby` | name のふりがな。name の直上または直下に小さい文字で記載される |
| `cost` | 購入や使用にかかるコスト。「購」と略記されることがある。防御力や攻撃力ではない |
| `limit` | 上限レベルや使用制限。「制」「上限」と略記されることがある |
| `description` | カードの解説テキスト。カード内で最も長い文章部分 |

### Console での設定手順

1. 作成したプロセッサの **Get Started** タブを開く
2. 「Edit」を選択してスキーマエディタを開く
3. 「Add field」で `game_card` を追加
   - 「This is a parent label」にチェック
   - Occurrence: **Optional Multiple**
4. `game_card` の下に「Add child field」で子フィールドを追加
   - 各フィールドの name, data type, occurrence を上の表に従って設定
   - description を入力（上の表を参考に）
5. 設定を保存

### Document-level prompt の設定

プロセッサ全体へのヒントとして document-level prompt を設定できます（500 文字以内）。

推奨例:

```
この文書はTRPGルールブックです。抽出対象はカード状に記述されたゲームデータのみです。
本文の説明テキストや章見出しは抽出対象外です。各カードは枠や背景色で区切られています。
略記（購、隠、防S/P/I、制、電制）はそのまま値として抽出してください。
```

## Step 4: トレーニングデータの準備とインポート

| 操作手段 | 対応状況 |
|----------|----------|
| Console | 主手順（Build タブ > Import documents） |
| REST API | `POST /v1beta3/{dataset}:importDocuments` |
| Python SDK | `dataset.import_documents()` |

### 必要データ数

> アプローチの選び分けについては [strategy doc の「template-based と custom model-based の選び分け」](./documentai-trpg-card-strategy.md#template-based-と-custom-model-based-の選び分け) を参照してください。

| アプローチ | 最低 training | 最低 test | 推奨 |
|------------|--------------|-----------|------|
| custom model-based | 10 | 10 | 各フィールドにつき 10 以上の instance |
| template-based | 3 | 3 | 各 variation につき 3 以上 |

### データ形式と制約

| 項目 | 制約 |
|------|------|
| 対応形式 | PDF, TIFF, GIF, JPEG, PNG, BMP, WebP |
| ファイルサイズ上限 | 20 MB（オンライン処理） |
| 格納場所 | Cloud Storage バケット、またはローカルアップロード |

### Console でのインポート手順

1. プロセッサの **Build** タブを開く
2. 「Import documents」を選択
3. インポート方法を選択:
   - **Upload from computer**: ローカルファイルをドラッグ&ドロップ
   - **Import from Cloud Storage**: GCS パスを指定
4. Data split: **Auto-split** を選択（自動で 80% training / 20% test に分割）
5. Auto-labeling: 初回は **チェックしない**（手動ラベル付けを推奨）
6. 「Import」を選択

## Step 5: ラベル付け（Console GUI 必須）

| 操作手段 | 対応状況 |
|----------|----------|
| Console | **必須**（GUI のラベリングツール） |
| JSON import | 事前にラベル付き Document JSON を用意している場合 |

ラベル付けは Console GUI でのみ実行できます。

### ラベル付け手順

1. **Build** タブで「Start labeling」を選択
2. 文書が表示されたら、以下の手順でラベル付けを行う:
   1. まず `game_card`（親ラベル）の bounding box をカード全体に配置
   2. `game_card` の中に子ラベル（`name`, `ruby` 等）の bounding box を配置
   3. 各子ラベルのテキストが正しく選択されていることを確認
3. すべてのカードとフィールドをラベル付けしたら「Mark as labeled」を選択
4. 次の文書に移り、すべての文書でラベル付けを完了する

### parent-child ラベル付けのポイント

- **親を先に配置**: `game_card` の bounding box を先に作成し、その内部に子ラベルを配置する
- **複数カード**: 同一ページに複数カードがある場合、各カードごとに別の `game_card` を作成する
- **空欄フィールド**: template-based の場合、空欄でも bounding box を含めてラベル付けする

### 日本語 TRPG 固有の注意事項

| 注意点 | 対処方法 |
|--------|----------|
| ルビ（ふりがな） | name の直上/直下の小文字を `ruby` としてラベル付け。OCR が name とルビを連結する場合がある |
| 特殊文字（N◎VA 等） | OCR が「NOVA」と認識する場合がある。ラベル付け時はOCR結果に合わせる |
| 略記（購/隠/防S等） | 列ヘッダーの略記はラベルに含めない。値のみをラベル付けする |
| 縦書きテキスト | 縦書き部分がある場合、OCR の読み取り順が乱れる可能性がある |

### ラベル付け品質チェックリスト

- [ ] すべてのカードに `game_card` 親ラベルが付いている
- [ ] 各 `game_card` 内の子ラベルが漏れなく付いている
- [ ] `name` と `ruby` が正しく分離されている
- [ ] 本文テキスト（カード外）にラベルが付いていない
- [ ] training / test の両セットに十分なサンプルがある
- [ ] 各フィールドの instance 数が最低要件を満たしている

## Step 6: トレーニングの実行

| 操作手段 | 対応状況 |
|----------|----------|
| Console | 主手順（Build タブ > Create new version） |
| REST API | `POST /v1/{parent}/processorVersions:train` |
| Python SDK | `client.train_processor_version()` |

> custom model-based を主軸とします。選定理由は [strategy doc](./documentai-trpg-card-strategy.md#custom-model-based-を選ぶ条件) を参照してください。

### Console でのトレーニング手順

1. **Build** タブの「Train a custom model」セクションで「Create new version」を選択
2. バージョン名を入力（例: `trpg-card-v1`）
3. 「View label stats」でラベル付けの coverage を確認
4. Model training method: **Model based** を選択
   - template-based を選ぶ場合は **Template based** を選択してください。選び分けの基準は [strategy doc](./documentai-trpg-card-strategy.md#template-based-を選ぶ条件) を参照
5. 「Start training」をクリック

トレーニングには数時間かかります。ページを閉じても処理は継続します。

### REST API でのトレーニング

```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://us-documentai.googleapis.com/v1/projects/${PROJECT_ID}/locations/us/processors/${PROCESSOR_ID}/processorVersions:train" \
  -d '{
    "processorVersion": {
      "display_name": "trpg-card-v1"
    }
  }'
```

レスポンスは Long-Running Operation です。完了を確認するには:

```bash
curl -X GET \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://us-documentai.googleapis.com/v1/${OPERATION_NAME}"
```

## Step 7: 評価と改善

| 操作手段 | 対応状況 |
|----------|----------|
| Console | 主手順（Evaluate & Test タブ） |

### 評価指標

| 指標 | 説明 | 目安 |
|------|------|------|
| F1 score | Precision と Recall の調和平均 | 0.9 以上を目標 |
| Precision | 抽出結果のうち正解の割合 | 誤抽出が少ないか |
| Recall | 正解のうち抽出できた割合 | 抽出漏れが少ないか |

評価は文書全体とフィールド個別の両方で確認します。

### Console での評価手順

1. **Evaluate & Test** タブを開く
2. Version selector でトレーニング済みバージョンを選択
3. 文書全体と各ラベルの F1 / Precision / Recall を確認
4. 「Upload Test Document」で未知の文書をテスト

### 精度低下時の改善戦略

| 問題 | 対策 |
|------|------|
| 特定フィールドの Recall が低い | そのフィールドの training サンプルを追加 |
| 特定フィールドの Precision が低い | ラベル付けの一貫性を見直す。field description を改善 |
| 全体的に精度が低い | training データ数を増やす。ラベル付けの品質を再確認 |
| 類似フィールドの混同 | field description で差異を明確に記述 |
| 本文テキストの誤抽出 | Step 1 のカード切り出しを導入。document-level prompt を追加 |

### バージョン管理

新しい training データを追加してモデルを改善する場合、新しいバージョンとしてトレーニングします。

```
trpg-card-v1  → 初期バージョン
trpg-card-v2  → training データ追加後
trpg-card-v3  → field description 改善後
```

旧バージョンは評価比較のために残しておくことを推奨します。

## Step 8: デプロイ

| 操作手段 | 対応状況 |
|----------|----------|
| Console | 主手順（Deploy & Use タブ） |
| REST API | `POST /v1/{name}:deploy` |
| Python SDK | `client.deploy_processor_version()` |

### Console でのデプロイ手順

1. **Deploy & Use**（または **Manage Versions**）タブを開く
2. デプロイしたいバージョンのチェックボックスを選択
3. 「Deploy」をクリック
4. 確認ダイアログで「Deploy」を選択

デプロイには数分かかります。完了後、「Set as default」でデフォルトバージョンに設定できます。

### REST API でのデプロイ

```bash
# バージョンのデプロイ
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://us-documentai.googleapis.com/v1/projects/${PROJECT_ID}/locations/us/processors/${PROCESSOR_ID}/processorVersions/${VERSION_ID}:deploy"

# デフォルトバージョンの設定
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://us-documentai.googleapis.com/v1/projects/${PROJECT_ID}/locations/us/processors/${PROCESSOR_ID}:setDefaultProcessorVersion" \
  -d '{
    "default_processor_version": "projects/PROJECT_ID/locations/us/processors/PROCESSOR_ID/processorVersions/VERSION_ID"
  }'
```

### Python SDK でのデプロイ

```python
from google.api_core.client_options import ClientOptions
from google.cloud import documentai_v1 as documentai

def deploy_processor_version(
    project_id: str,
    location: str,
    processor_id: str,
    version_id: str,
):
    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    client = documentai.DocumentProcessorServiceClient(client_options=opts)

    name = client.processor_version_path(
        project_id, location, processor_id, version_id
    )

    operation = client.deploy_processor_version(name=name)
    operation.result()  # デプロイ完了まで待機
    print(f"デプロイ完了: {name}")
```

## Step 9: 推論（nova-parser への統合）

| 操作手段 | 対応状況 |
|----------|----------|
| Python SDK | 主手順（nova-parser の既存パイプライン） |
| REST API | `POST /v1/{name}:process` |

### 環境変数の設定

`.env` の `DOCUMENT_AI_PROCESSOR` を Custom Extractor のリソース名に差し替えます。

```bash
# .env
# 既存の OCR プロセッサ（参考）
# DOCUMENT_AI_PROCESSOR=projects/123456/locations/us/processors/ocr_processor_id

# Custom Extractor に切り替え
DOCUMENT_AI_PROCESSOR=projects/123456/locations/us/processors/custom_extractor_id
```

特定のバージョンを指定する場合は、リソース名にバージョン ID を付加します:

```bash
DOCUMENT_AI_PROCESSOR=projects/123456/locations/us/processors/custom_extractor_id/processorVersions/version_id
```

### document.entities からのデータ取得

Custom Extractor のレスポンスでは、`document.entities` にスキーマに沿ったエンティティが格納されます。これは [OCR プロセッサで空になるフィールド](./usage.md#ocr-プロセッサで空になるフィールド) として既に説明されているものです。

```python
from google.cloud import documentai_v1 as documentai

def extract_game_cards(document: documentai.Document) -> list[dict]:
    """Custom Extractor のレスポンスから game_card エンティティを抽出する"""
    cards = []

    for entity in document.entities:
        if entity.type_ != "game_card":
            continue

        card = {}
        for prop in entity.properties:
            card[prop.type_] = prop.mention_text
        cards.append(card)

    return cards
```

出力例:

```python
[
    {
        "type_name": "スキル",
        "name": "フェスラー国境警備隊",
        "ruby": "こっきょうけいびたい",
        "skill": "なし",
        "timing": "常時",
        "target": "自身",
        "range": "なし",
        "description": "解説テキスト...",
    },
    # ... 他のカード
]
```

### 既存の extract モードとの関係

現在の `extract` モードは `OCR_PROCESSOR` + Gemini で構造化抽出を行っています。Custom Extractor を導入すると、Document AI 単体でスキーマに沿った entity extraction が完結するため、Gemini による後段処理が不要になります。

移行パスとしては:

1. まず Custom Extractor を別プロセッサとして作成・評価
2. 精度が十分であることを確認
3. `DOCUMENT_AI_PROCESSOR` を切り替え
4. `documentai.py` のレスポンス処理を `document.entities` ベースに変更

## 日本語 TRPG 固有の注意点まとめ

| 項目 | 注意点 | 対策 |
|------|--------|------|
| generative AI extraction | 英語のみ公式サポート | custom model-based または template-based を使用 |
| ルビ（ふりがな） | OCR が name とルビを連結する場合がある | ラベル付け時に正確に分離。field description で明記 |
| 特殊文字 | N◎VA → NOVA 等の置換が発生 | 既存の後処理ロジック（`documentai.py`）と同様に対応 |
| 略記フィールド | 購、隠、防S/P/I、制、電制 | field description に「略記であり正式名称ではない」旨を記載 |
| 縦書き混在 | TRPG 書籍で縦書き部分がある場合 | 主に横書きカードを対象とし、縦書きは別途対応を検討 |
| カード種別の多様性 | 武器、防具、スキル等で子フィールドが異なる | まず `game_card` 共通 parent で始め、Optional フィールドで対応 |

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| プロセッサ作成時に `CUSTOM_EXTRACTION_PROCESSOR` が選択肢にない | リージョンが未対応 | `us` または `eu` リージョンを選択 |
| トレーニングが開始されない | training / test データが最低要件未満 | custom model-based: 各 10 件以上、template-based: 各 3 件以上 |
| トレーニング後の F1 が極端に低い | ラベル付けの不整合、データ不足 | ラベル付け品質を再確認。training データを追加 |
| 推論で entities が空 | デプロイされたバージョンが設定されていない | Deploy & Use タブでデプロイ状態を確認 |
| 推論で entities が空 | `DOCUMENT_AI_PROCESSOR` が OCR プロセッサのまま | `.env` のリソース名を Custom Extractor に変更 |
| 特定フィールドだけ抽出されない | field の instance 数が不足 | そのフィールドを含む training データを追加 |
| ルビと name が混同される | bounding box の重なり、field description 不足 | ラベル付けの bounding box を正確に。description を改善 |

## 参考資料

- [Custom extractor overview](https://cloud.google.com/document-ai/docs/custom-extractor-overview)
- [Custom extractor mechanisms](https://cloud.google.com/document-ai/docs/ce-mechanisms)
- [Custom-based extraction](https://cloud.google.com/document-ai/docs/custom-based-extraction)
- [Template-based extraction](https://cloud.google.com/document-ai/docs/ce-template-based)
- [Custom extractor with generative AI](https://cloud.google.com/document-ai/docs/ce-with-genai)
- [Label documents](https://cloud.google.com/document-ai/docs/label-documents)
- [Evaluate processor](https://cloud.google.com/document-ai/docs/workbench/evaluate)
- [Manage processor versions](https://cloud.google.com/document-ai/docs/manage-processor-versions)
- [Send a processing request](https://cloud.google.com/document-ai/docs/send-request)
- [Handle the processing response](https://cloud.google.com/document-ai/docs/handle-response)
- [Document AI REST API reference](https://cloud.google.com/document-ai/docs/reference/rest)
- [Document AI Python SDK reference](https://cloud.google.com/python/docs/reference/documentai/latest)
