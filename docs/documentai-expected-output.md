# Document AI で期待値に近い返り値を得るための手順

Vertex AI と組み合わせて Google Cloud Document AI を使う場合、最初に整理すべきなのは「何を返してほしいか」です。Document AI の OCR プロセッサが直接返すのは、主にテキストとレイアウト情報です。業務向けの構造化データやドメイン固有の意味づけまで欲しい場合は、OCR の後段に Gemini や Custom Extractor を置く必要があります。

このガイドは、まず一般的な運用手順を示し、その後で `nova-parser` の `docai_plain` / `docai` / `extract` モードにどう当てはめるかを整理します。

## 先に結論

- 文書画像や PDF から文字とレイアウトを安定して取りたいなら、第一候補は `OCR_PROCESSOR` です。
- 期待値を左右する要因は、プロンプトよりも先に、入力品質、プロセッサ選定、processor version 固定、ページ分割、レスポンスの見方です。
- `document.text` だけを見ると「文字列は取れたが、なぜ崩れたか」が分かりません。改善には `pages[].image_quality_scores`、`lines`、`tokens`、`layout.text_anchor` を併せて確認します。
- 日本語ヒント、デジタル PDF の native parsing、画像品質スコアは有効な調整手段ですが、常に全部有効にすればよいわけではありません。

## 手順 1. 期待する返り値を先に固定する

まず、欲しい返り値を次のいずれかに分類します。

| 分類 | ユーザが本当に欲しいもの | Document AI 単体で返るもの | 追加処理 | `nova-parser` での位置づけ |
|---|---|---|---|---|
| OCR テキスト | 読める文字列そのもの | `document.text` | 不要 | `docai_plain` でまず確認する層 |
| レイアウトつき OCR | 行、段落、座標、信頼度つきの OCR | `pages[].blocks` / `paragraphs` / `lines` / `tokens` と各 `layout` | 不要 | 現状は直接出力していないが、崩れ方の診断に使う層 |
| 構造化抽出 | 業務上の意味づけ済みデータ、JSON、TSV | OCR テキストまでは返る | Gemini または Custom Extractor が必要 | `docai` と `extract` が担う層 |

### 3分類の違い

`OCR テキスト` を選ぶ場面は、まず文字が読めているかだけを見たいときです。ここで期待すべき返り値は、改行を含んだ文字列です。ユーザが本当に知りたいのが「このページの文字をどれだけ正しく読めたか」であれば、まずここで止めるのが正解です。

`レイアウトつき OCR` を選ぶ場面は、文字列が崩れた理由まで見たいときです。同じ `OCR_PROCESSOR` でも、`document.text` だけではなく、段落、行、トークン、座標、信頼度を見ることで、どこで読み順が崩れたか、どの行が欠けたか、どの領域の品質が悪いかを追えます。ユーザが必要としているのが「OCR 結果」ではなく「OCR の診断材料」なら、この層まで見る必要があります。

`構造化抽出` を選ぶ場面は、最終成果物が JSON や TSV のときです。このとき欲しいのは、単なる文字列ではなく、`名称`、`価格`、`解説` のように意味づけされたフィールドです。これは OCR の仕事ではなく、OCR 後の解釈の仕事です。したがって、Document AI 単体で完結する期待ではなく、後段の Gemini や抽出ロジックも含めて品質を設計する必要があります。

### どこで責務が切り替わるか

返り値の期待を分ける目的は、責務境界を先に固定することです。

- OCR の責務は、画像や PDF に見えている文字と、そのレイアウトをできるだけ正しく返すことです
- 構造化抽出の責務は、その文字列に意味ラベルを付け、業務スキーマに押し込むことです
- TSV や JSON が崩れたとき、それが OCR の失敗なのか、後段の抽出や正規化の失敗なのかを切り分けるために、この境界が必要です

言い換えると、`document.text` が妥当なら OCR はおおむね成功しており、その先の崩れは Gemini 側や後処理側の問題である可能性が高くなります。逆に、`document.text` の時点で抜けや誤読が多いなら、後段の抽出だけを調整しても改善しません。

なお、表、フォーム、チェックボックスのように「レイアウトに意味がある要素」をプロセッサ側で直接返してほしい場合は、`OCR_PROCESSOR` ではなく `FORM_PARSER_PROCESSOR` などの専用プロセッサを検討します。ここで重要なのは、「構造化抽出が欲しい」のか、「専用レイアウト要素が欲しい」のかを混同しないことです。

### よくある誤った期待

- 「表が見えているのだから、表セルがそのまま返るはず」
  - これは OCR テキストと専用プロセッサの期待が混ざっています。`OCR_PROCESSOR` でまず得られるのは主に文字列とレイアウトです。
- 「Document AI に画像を渡したのだから、装備データの JSON まで直接返るはず」
  - これは OCR と意味抽出の責務を混同しています。業務 JSON は後段の Gemini や抽出ロジックの責務です。
- 「`document.text` が取れているのに TSV が崩れるのだから、OCR が悪いはず」
  - OCR が十分でも、型判定、項目分割、正規化、スキーマ制約のどこかで崩れることがあります。

### `nova-parser` でどう見るか

この repo では、3分類は次のように読み替えると分かりやすくなります。

- `OCR テキスト`: `docai_plain` で確認する対象です。まずここで、文字として読めているかを確認します。
- `レイアウトつき OCR`: 現状の CLI 出力には直接出していませんが、`src/nova_parser/documentai.py` が受け取る `Document` には含まれています。`document.text` だけでは原因が分からないときに見るべき層です。
- `構造化抽出`: `docai` と `extract` が担う対象です。ここでは OCR 自体ではなく、OCR 後にどう解釈し、どの型に落とし込むかが品質を左右します。

### 迷ったときの判断フロー

1. 文字列として読めているかだけ確認したいなら `OCR テキスト`
2. 読み順や欠落の原因まで見たいなら `レイアウトつき OCR`
3. 最終成果物が JSON / TSV なら `構造化抽出`

この順で考えると、「最初にどの返り値を検証すべきか」がぶれにくくなります。特に `nova-parser` では、いきなり `docai` や `extract` の結果を見るより、先に `docai_plain` で OCR 生出力を確認した方が切り分けが速くなります。

## 手順 2. その期待に合う processor を選ぶ

返り値の期待を分けたら、次はその期待に対応する processor を選びます。ここで重要なのは、Document AI の processor はすべて何らかの形でテキストとレイアウトを扱える一方で、どこまでを processor 側で意味づけして返すかがそれぞれ違う、という点です。

| 欲しい返り値 | 第一候補の processor | なぜその processor か | Document AI 単体で完結するか | `nova-parser` での扱い |
|---|---|---|---|---|
| OCR テキスト | `OCR_PROCESSOR` | 文字とレイアウトを安定して digitize する用途に最も素直だから | する | 現行の前提 |
| レイアウトつき OCR | `OCR_PROCESSOR` | `document.text` に加えて `pages` 配下の診断情報を使えるから | する | 現行の前提 |
| フォームの KVP、表、チェックボックス | `FORM_PARSER_PROCESSOR` | key-value pairs、tables、selection marks を processor 側で返せるから | する | 現行の前提外 |
| 文書要素の chunk 化、text/tables/lists の構造化 | `LAYOUT_PARSER_PROCESSOR` | 文書要素と context-aware chunks を返せるから | する | 現行の前提外 |
| 固定スキーマの業務フィールド抽出 | `CUSTOM_EXTRACTION_PROCESSOR` | schema に沿った entity extraction を processor 側で持てるから | 条件次第で完結する | 現行の前提外 |

### 選び分けの基本

まず確認すべきなのは、「欲しいのが OCR 結果なのか、processor が意味づけした構造なのか」です。

- 欲しいのが文字列や読み順、座標、信頼度なら `OCR_PROCESSOR` を選びます
- 欲しいのが表セル、KVP、チェックボックスなら `FORM_PARSER_PROCESSOR` を検討します
- 欲しいのが段落、見出し、表、リストを chunk 単位で扱える表現なら `LAYOUT_PARSER_PROCESSOR` を検討します
- 欲しいのが schema に沿った entity extraction なら `CUSTOM_EXTRACTION_PROCESSOR` を検討します

Google 公式の overview でも、processor 選定は use case ごとに分けて考える前提になっています。`Enterprise Document OCR` は text and layout extraction、`Form Parser` は structured form からの KVP と tables、`Layout Parser` は text/tables/lists と context-aware chunks、`Custom Extractor` は schema に沿った entity extraction のための選択肢です。

### `OCR_PROCESSOR` を選ぶべき場面

`OCR_PROCESSOR` は、まず「文字を正しく読むこと」が主目的のときに選びます。特に次の条件なら第一候補です。

- 画像や PDF からプレーンな OCR テキストを取りたい
- 読み順や欠落を `lines` や `tokens` で診断したい
- 後段の Gemini や独自ロジックで意味づけする前提にしたい
- レイアウトは見るが、KVP や table schema を processor 側に強く期待しない

この repo のユースケースは基本的にここに入ります。TRPG ルールブックのような自由度の高い紙面から、まず OCR テキストを安定して取り、その後で Gemini がゲームデータに解釈する流れなので、processor に業務スキーマまで背負わせるより `OCR_PROCESSOR` を選ぶ方が設計が素直です。

### `FORM_PARSER_PROCESSOR` を検討すべき場面

`FORM_PARSER_PROCESSOR` は、文書が「入力欄のあるフォーム」に近く、key-value pairs、tables、checkboxes を processor 側で返してほしいときに向いています。

- 項目名と値の対が紙面上で比較的明確
- 表セルを後段で再解釈するより、そのまま抽出したい
- checkbox や generic entities が必要

ただし、「表があるから即 Form Parser」とは限りません。欲しいのが最終的に表セルそのものではなく、ルールブック本文から意味づけ済みの TSV を作ることであれば、`OCR_PROCESSOR` で文字列を取り、後段で解釈した方が現行 repo の責務分離に合います。

### `LAYOUT_PARSER_PROCESSOR` を検討すべき場面

`LAYOUT_PARSER_PROCESSOR` は、文書を見出し、段落、リスト、表といった要素に分解し、context-aware chunks として扱いたいときの選択肢です。

- 後段が検索、RAG、discovery のような chunk 利用前提
- 文字列よりも「文書構造のまとまり」が欲しい
- PDF だけでなく HTML や Office 系文書も対象にしたい

一方、`nova-parser` の現行パイプラインは chunk retrieval ではなく OCR -> Gemini 抽出です。そのため、現時点では Layout Parser を第一候補にする理由は薄く、導入するならレスポンスの読み方と後段処理の前提を別途見直す必要があります。

### `CUSTOM_EXTRACTION_PROCESSOR` を検討すべき場面

`CUSTOM_EXTRACTION_PROCESSOR` は、Document AI 側に schema を持たせ、entity extraction を processor 側で完結させたいときの選択肢です。

- 抽出したいフィールドが明確に定義されている
- 文書集合に対して継続的に学習や評価を回したい
- OCR の後で毎回 LLM に自由解釈させるより、抽出契約を固定したい

ただし、この repo の対象は日本語を含む可変レイアウトのルールブックです。Google 公式の processor list では、Custom Extractor の generative AI extraction は英語のみが公式サポートです。したがって、少なくとも現行の日本語中心ユースケースでは、`CUSTOM_EXTRACTION_PROCESSOR` を標準経路にする理由は弱く、`OCR_PROCESSOR` + Gemini の方が実装と運用の一貫性を保ちやすくなります。

### `nova-parser` ではなぜ `OCR_PROCESSOR` なのか

この repo は `DOCUMENT_AI_PROCESSOR` に OCR プロセッサのリソース名を渡す前提で設計されています。これは実装と既存ドキュメントの両方に現れています。

- `src/nova_parser/documentai.py` は `document.text` を主な入力として後段に渡しています
- `docs/usage.md` でも `DOCUMENT_AI_PROCESSOR` を OCR プロセッサとして説明しています
- `docai_plain`、`docai`、`extract` のいずれも、最初の責務は OCR テキスト取得です

このため、processor 選定を変えるときは「環境変数の差し替え」だけでは足りません。`FORM_PARSER_PROCESSOR` や `LAYOUT_PARSER_PROCESSOR` に切り替えるなら、どのフィールドを主入力に使うか、後段の Gemini に何を渡すか、期待する返り値をどう再定義するかまで一緒に見直す必要があります。

### よくある選定ミス

- 「表が見えるから `FORM_PARSER_PROCESSOR` を選ぶ」
  - 欲しいのが表セル自体ではなく、自由文を含むドメイン抽出なら `OCR_PROCESSOR` の方が自然なことがあります。
- 「JSON が欲しいから `CUSTOM_EXTRACTION_PROCESSOR` を選ぶ」
  - schema が安定していて Document AI 側に責務を寄せたい場合は有力ですが、日本語や可変レイアウト前提では現行 repo と相性がよいとは限りません。
- 「文書構造を見たいから `LAYOUT_PARSER_PROCESSOR` を選ぶ」
  - chunking が目的でないなら、まずは `OCR_PROCESSOR` の `pages` 配下で十分なことが多いです。

## 手順 3. 入力品質を整える

期待とズレる返り値の多くは、API 呼び出し前の入力で決まります。

### 推奨チェックリスト

- 可能なら `PDF`、`PNG`、`TIFF` を優先し、劣化した JPEG の再保存を避ける
- 最低でも 200 dpi、できれば 300 dpi 以上を確保する
- 傾き、回転、トリミング不足、指や影の写り込み、強い glare を除去する
- 見開きは 1 ページ単位に分割し、不要ページを混ぜない
- 極小文字がある場合は拡大スキャンを優先する
- 1 リクエストに「異なる帳票種別」や「関係ない付録ページ」を混在させない
- デジタル PDF なら、画像化してから送る前に native PDF parsing を試す

### 制約として意識すること

- 対応形式は PDF、GIF、TIFF、JPEG、PNG、BMP、WebP です
- オンライン処理のファイルサイズ上限は 40 MB です
- 画像は 40 メガピクセル / ページまでです
- Enterprise Document OCR のオンライン同期処理は 15 ページまでです
- `imageless_mode` を使うと、1 ページ目から連続するページに限って同期 30 ページまで拡張できます

15 ページを超える PDF を同期処理したい場合は、次のいずれかに寄せます。

- ページ分割して複数回処理する
- 非同期バッチ処理に切り替える
- 条件を満たすなら `imageless_mode` を検討する

## 手順 4. processor version と location を固定する

OCR の「読み順」や一部挙動は processor version で変わり得ます。再現性が必要な運用では、毎回同じ processor version を使います。

- 新しい version は精度改善が入る一方、OCR の振る舞いが変わる可能性があります
- 厳密な一貫性が必要なら、凍結された model version を使って挙動を固定します
- `us` 以外の location を使う場合は `LOCATION-documentai.googleapis.com` を API endpoint に設定します
- プロセッサの location とクライアントの endpoint を一致させます

## 手順 5. リクエストを最小限の意図で組む

Document AI では、まず過剰な設定を避け、必要なものだけを有効化します。

### 推奨デフォルト

- 画像やスキャン由来の入力: `enable_image_quality_scores=True`
- デジタル PDF: `enable_native_pdf_parsing=True`
- 言語が本当に既知な場合のみ: `hints.language_hints=["ja"]`
- 不要ページがある場合: `from_start` / `from_end` / `individual_page_selector` を使う
- 応答サイズが大きすぎる場合: `field_mask` で返却項目を絞る

### 注意点

- `language_hints` は、言語が既知のまれなケースでは改善に効きますが、誤ったヒントは品質悪化の原因になります
- `enable_image_quality_scores` は、OCR と同程度の追加レイテンシを生みます。常時本番で使うか、診断時だけ使うかを決めておきます
- `enable_native_pdf_parsing` は、既に埋め込みテキストを持つ PDF に有効です
- `advanced_ocr_options=["legacy_layout"]` はレイアウト順序を変える可能性があるため、既定値で問題がある場合にだけ試します
- `ocr_config` は `OCR_PROCESSOR` と `FORM_PARSER_PROCESSOR` でのみ使えます

### Python 例

```python
from google.api_core.client_options import ClientOptions
from google.cloud import documentai_v1 as documentai

client = documentai.DocumentProcessorServiceClient(
    client_options=ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
)

request = documentai.ProcessRequest(
    name=processor_name,
    raw_document=documentai.RawDocument(content=content, mime_type=mime_type),
    process_options=documentai.ProcessOptions(
        ocr_config=documentai.OcrConfig(
            enable_image_quality_scores=True,
            enable_native_pdf_parsing=(mime_type == "application/pdf"),
            # 言語が確実に分かっている場合だけ指定する
            hints=documentai.OcrConfig.Hints(language_hints=["ja"]),
        )
    ),
)

result = client.process_document(request=request)
document = result.document
```

`field_mask` を使う場合は、まず `text` と `pages` 系だけで足りるかを確認し、必要なフィールドだけ返すようにします。

## 手順 6. `document.text` だけで判断しない

期待と違う返り値になったときは、次の順序で確認します。

1. `pages[].image_quality_scores`
2. `pages[].detected_languages`
3. `pages[].blocks` / `paragraphs` / `lines` / `tokens`
4. 各 `layout.text_anchor`
5. 各 `layout.bounding_poly`
6. 各 `layout.confidence`

この順で見る理由は次のとおりです。

- 品質スコアで、入力側の問題かどうかを先に切り分けられる
- `line` や `token` まで見ると、どこで読み順や分割が崩れたかが分かる
- `text_anchor` は `document.text` のどの位置に対応するかを示すため、原文断片を復元できる
- `bounding_poly` があれば、問題の断片が画像のどこにあるかを確認できる
- `confidence` は低品質箇所の再処理候補を絞る材料になる

テキスト断片は `layout.text_anchor.text_segments` から復元します。

```python
def layout_to_text(layout, text: str) -> str:
    return "".join(
        text[int(segment.start_index): int(segment.end_index)]
        for segment in layout.text_anchor.text_segments
    )
```

## 手順 7. よくあるズレと対処

| 症状 | 先に疑うこと | 主な対処 |
|---|---|---|
| 読み順が不自然 | version 差分、レイアウト検出 | processor version を固定し、必要なら `legacy_layout` を比較する |
| 文字化けや取りこぼし | 画像品質、解像度、傾き | 再スキャン、トリミング、300 dpi 化、ページ分割 |
| 日本語と英字が混在すると崩れる | 言語判定の揺れ | ヒントは言語が既知のときだけ使う |
| デジタル PDF なのに精度が低い | native PDF parsing 未使用 | `enable_native_pdf_parsing` を試す |
| 大量ページで失敗する | 同期上限超過 | 分割、非同期、`imageless_mode` を検討する |
| 最終 JSON / TSV だけ崩れる | OCR ではなく後段抽出 | まず OCR 生テキストを確認し、その後に Gemini / schema を直す |
| 特殊記号や固有表記が崩れる | ドメイン固有語 | 後処理の正規化ルールを追加する |

## `nova-parser` への適用

この repo では、Document AI の責務と Gemini の責務を次のように分けています。

| モード | Document AI の責務 | 後段処理 |
|---|---|---|
| `docai_plain` | OCR テキスト取得 | なし |
| `docai` | OCR テキスト取得 | Gemini でゲームデータ抽出し TSV 化 |
| `extract` | OCR テキスト取得 | Gemini でスキーマ準拠抽出し TSV 化 |

現行実装の前提は次のとおりです。

- `src/nova_parser/documentai.py` は現在 `document.text` を主に使用しています
- PDF は同期 15 ページ上限に合わせて 15 ページ単位で分割しています
- OCR 後に `NOVA` を `N◎VA` に補正する、ドメイン固有の後処理を入れています

このため、`nova-parser` で返り値の期待値を上げる順序は次になります。

1. 返り値の期待を固定する
2. 現行 repo では `OCR_PROCESSOR` を選ぶ
3. 入力画像を整える
4. `DOCUMENT_AI_PROCESSOR` の processor / version / location を固定する
5. まず `docai_plain` で OCR 生テキストを確認する
6. 問題がある場合は `document.text` だけでなく line / token ベースの診断を追加する
7. OCR が妥当になってから `docai` / `extract` 側の Gemini 抽出を調整する

認証や CLI の前提は [使い方の詳細](usage.md) を参照してください。

## 実務上の推奨フロー

運用では次の順番に固定するとぶれにくくなります。

1. 返り値の期待を「OCR テキスト」「レイアウトつき OCR」「構造化抽出」に分ける
2. その期待に合う processor を選ぶ
3. 入力品質をチェックする
4. processor version と location を固定する
5. `docai_plain` 相当で OCR 生出力を確認する
6. 画像品質スコアと line / token で崩れ方を確認する
7. 必要なら後処理や Gemini 抽出を直す

この順序を飛ばして、いきなり後段のプロンプトや正規表現だけを調整すると、根本原因が OCR 側にあるケースを見落としやすくなります。

## 参考資料

- [Enterprise Document OCR](https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr)
- [Extraction overview](https://docs.cloud.google.com/document-ai/docs/extracting-overview)
- [Process documents with client libraries](https://docs.cloud.google.com/document-ai/docs/process-documents-client-libraries)
- [ProcessOptions / OcrConfig reference](https://docs.cloud.google.com/document-ai/docs/reference/rest/v1/ProcessOptions)
- [Document schema / response reference](https://docs.cloud.google.com/document-ai/docs/reference/rest/v1/Document)
- [Supported files](https://docs.cloud.google.com/document-ai/docs/file-types)
- [Processor list](https://docs.cloud.google.com/document-ai/docs/processors-list)
- [Quotas](https://docs.cloud.google.com/document-ai/quotas)
- [Limits](https://docs.cloud.google.com/document-ai/limits)
- [Regional and multi-regional support](https://docs.cloud.google.com/document-ai/docs/regions)
