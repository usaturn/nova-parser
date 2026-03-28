# TRPG カード状ゲームデータ向け Document AI 活用方針

この文書は、`nova-parser` の処理対象を以下のように限定した場合に、Google Cloud Document AI をどう使うのが理想的かを整理した設計提案書です。

- 対象は TRPG 書籍内のカード状に記述されたゲームデータ
- カードに記述されていない本文は抽出対象外
- 1 カードは複数の項目を持つ
- 1 ページに複数カードと本文が混在し得る

以下の結論は、2026-03-28 時点で確認できた Google 公式ドキュメントと、この repo の現行実装を突き合わせたうえでまとめています。

## 結論

この要件に最も合う本命は `CUSTOM_EXTRACTION_PROCESSOR` です。
ただし、日本語の TRPG 書籍を対象にする以上、**generative AI extraction をそのまま本番の第一候補にはしません**。

推奨は次のとおりです。

| 条件 | 推奨 |
|---|---|
| カードのレイアウトがかなり固定 | `CUSTOM_EXTRACTION_PROCESSOR` の template-based |
| カードのレイアウトに多少の揺れがある | `CUSTOM_EXTRACTION_PROCESSOR` の custom model-based |
| まず少量で試したい、または既存実装を大きく変えたくない | `OCR_PROCESSOR` + Gemini |
| 本命としては非推奨 | `FORM_PARSER_PROCESSOR`, `LAYOUT_PARSER_PROCESSOR` |

## なぜ `Custom Extractor` が本命か

今回欲しいのは、単なる OCR テキストではなく、カード単位にまとまった構造化データです。つまり「1 カード = 1 レコード」であり、その下に `名称`、`ルビ`、`技能`、`対象`、`射程`、`解説` のような複数フィールドがぶら下がります。

この形は、Document AI の機能で言うと「OCR」よりも「entity extraction」に近く、さらに事前定義した schema を持てる方が相性がよくなります。`Custom Extractor` はまさにこの用途向けで、公式 docs でも新しい文書タイプに対して custom entity extraction solution を作るための選択肢として説明されています。

加えて、ラベル設計では parent-child entities を持てます。公式 docs では foundation models で grandparent / parent / child の 3 層まで対応し、child の下にさらに 1 層持てると説明されています。今回の要件では、これを次のように使うのが自然です。

- 親エンティティ: `game_card`
- 子エンティティ: `name`, `ruby`, `skill`, `timing`, `target`, `range`, `cost`, `description` など
- 複数カード: 同じ `game_card` 親エンティティの反復

これは公式 docs の parent-child entities の仕様を踏まえた**設計推論**です。Google が TRPG カードを具体例として挙げているわけではありませんが、今回のデータ形状には最も素直に対応できます。

## Processor 比較

| processor | 向いている用途 | 今回の要件との適合度 | 主な弱点 |
|---|---|---|---|
| `OCR_PROCESSOR` | 文字とレイアウトの取得、読み順診断 | 中 | カード境界や本文除外を自前で処理する必要がある |
| `FORM_PARSER_PROCESSOR` | KVP、表、checkbox、generic entities | 低 | カード状データを業務スキーマとして扱う本命ではない |
| `LAYOUT_PARSER_PROCESSOR` | layout-aware chunking、RAG、文書構造理解 | 低 | カード単位の業務フィールド抽出が主目的ではない |
| `CUSTOM_EXTRACTION_PROCESSOR` | 独自 schema に沿った entity extraction | 高 | 学習・ラベル付け・評価が必要 |

### `OCR_PROCESSOR`

`OCR_PROCESSOR` は文字とレイアウトを安定して digitize する用途に最も素直です。日本語対応も広く、現行 repo もこの前提で動いています。
ただし、この要件ではカード外本文がノイズになります。`document.text` に全文を平坦化してから後段の LLM に解釈させる方式では、カード境界と対象外本文の切り分けが弱くなります。

したがって `OCR_PROCESSOR` は、次のような場合の暫定策としては有効です。

- 少量データで PoC したい
- 既存の `docai` / `extract` を大きく崩したくない
- まずカード領域抽出や schema を人手で詰める前に、ざっくり結果を見たい

### `FORM_PARSER_PROCESSOR`

`FORM_PARSER_PROCESSOR` は KVP、tables、checkboxes、generic entities 向けです。
今回のデータが本当に「フォーム」に近く、項目名と値が毎回明確にペアになっているなら候補になりますが、TRPG のカードは説明文や装飾、自由レイアウトを含むことが多く、Form Parser の典型的な得意領域とはずれます。

カードに表っぽい見た目があっても、最終的に欲しいのが「表セル」ではなく「ゲームデータの意味づけ済みフィールド」であれば、Form Parser を本命にする理由は弱いです。

### `LAYOUT_PARSER_PROCESSOR`

`LAYOUT_PARSER_PROCESSOR` は text / tables / lists を文書構造として捉え、context-aware chunks を作る用途に向いています。公式 docs でも primary use case は Search / RAG / discovery 寄りです。

今回のような「カード単位の抽出」が目的なら、Layout Parser は本命ではありません。
見出しや表を保った chunk を作るのには便利ですが、「本文は無視し、カードだけを card record として抽出する」こと自体は解決しません。

### `CUSTOM_EXTRACTION_PROCESSOR`

`CUSTOM_EXTRACTION_PROCESSOR` は、独自 schema を定義し、その schema に沿って entity extraction を行いたい場合の本命です。今回の要件では、カードそのものを親エンティティ、カード内の各項目を子エンティティとして定義できるため、最も相性がよいです。

ただし、注意点があります。

- 公式の `Processor list` では、`Custom Extractor` の **generative AI extraction は英語のみが公式サポート**
- 一方で `Custom Extractor` 全体の supported languages には日本語が含まれる
- したがって、日本語用途では generative AI foundation model を本番本命にするより、template-based か custom model-based を主軸にした方が安全

ここは **公式仕様 + 要件からの設計判断** です。

## 理想アーキテクチャ

### 推奨構成

品質最優先なら、理想は次の 2 段階です。

1. ページ画像からカード領域だけを切り出す
2. 切り出したカード画像を `CUSTOM_EXTRACTION_PROCESSOR` に渡す

この upstream のカード切り出しは、Document AI 単体機能ではなく**設計上の補助処理**です。公式 docs が TRPG カード向けに明示しているわけではありません。
ただし、今回の「本文は対象外」という要件をそのまま満たすには、最も素直な手です。

カード切り出しが難しい場合は、ページ全体を `Custom Extractor` に渡し、parent-child entities でカード反復を学習させる構成が次善です。

### 推奨 schema 例

これは**設計例**です。

| 階層 | 例 |
|---|---|
| parent | `game_card` |
| child | `type_name`, `name`, `ruby`, `skill`, `timing`, `target`, `range`, `cost`, `limit`, `description` |

カード種別ごとにフィールド差が大きい場合は、次のどちらかに寄せます。

- `game_card` 配下に共通フィールド + optional multiple を持たせる
- カード種別ごとに別 parent を切る

後者の方が schema は明確ですが、カード種別が多すぎると運用が重くなります。
この repo の現状を見る限り、まずは `game_card` を共通 parent にして、型名は child として持つ構成から始めるのが無難です。これは**repo 運用上の推奨**です。

## template-based と custom model-based の選び分け

### template-based を選ぶ条件

公式 docs では、template-based は fixed-layout use case 向けで、少ない学習データから始められます。
今回なら、次の条件で第一候補です。

- カードの位置と項目の並びがほぼ固定
- シリーズや版をまたいでも見た目がほとんど変わらない
- 空欄があっても配置そのものは変わらない

公式 docs では、template-based は 3 training / 3 test から始められ、各 variation につき少なくとも 3 件ずつ含めることが推奨されています。
また、template mode では空欄フィールドも bounding box を含めてラベル付けするのが推奨です。カードに optional 項目があるなら重要です。

### custom model-based を選ぶ条件

公式 docs では、custom model-based は layout variation across years or vendors のようなケース向けです。
今回なら、次の条件でこちらを選びます。

- カードの骨格は似ているが、版や書籍ごとに項目位置が揺れる
- 説明文の長さでカードの高さが変わる
- 一部の項目が別位置に出る

公式 docs では、custom model-based は最低 10 training / 10 testing の開始条件があり、custom extractor mechanisms のページでは各 field について training / test の instance 数も意識するよう求めています。
カード種類が多く、各項目の出現頻度が偏る場合は、minimum ぎりぎりでは不足しがちです。

## 日本語前提での注意点

日本語 TRPG 書籍を前提にすると、次を補足しておくべきです。

- `Custom Extractor` の generative AI extraction は英語のみが公式サポート
- そのため zero-shot / few-shot / fine-tuned foundation model は、日本語では「試験導入」または「schema 叩き台づくり」までに留めるのが安全
- 本番経路は template-based か custom model-based を優先する

これは今回の判断の重要ポイントです。
英語文書中心の業務帳票なら foundation model を先に試す意味がありますが、日本語 TRPG データではそのまま本命にしない方がよいです。

## この repo への当てはめ

現行実装は [src/nova_parser/documentai.py](../src/nova_parser/documentai.py) で `result.document.text` を主入力にし、その全文 OCR を Gemini に渡しています。
つまり現在は、カード境界も本文ノイズも一度 flatten してから解釈しています。

このため、今回の要件に対する評価は次のとおりです。

- 現行 `docai` / `extract`: PoC としては有効
- ただし理想形ではない
- 理由は、カードだけを対象にしたいのに、全文 OCR ベースで本文ノイズを混ぜているから

### 短期の現実解

大きく作り替えないなら、まずは `OCR_PROCESSOR` を維持したまま次を行うのが現実的です。

1. `document.text` だけでなく layout 情報も見る
2. カード領域だけを upstream で切り出す、または line / block 単位で絞る
3. card-only の OCR テキストだけを Gemini に渡す

これは完全な理想形ではありませんが、対象外本文の混入を減らせます。

### 中期の理想解

中期的には、`CUSTOM_EXTRACTION_PROCESSOR` に寄せるのが本筋です。

1. `game_card` を parent とした schema を定義
2. card sample を収集
3. layout 固定度で template-based / custom model-based を選択
4. 評価指標を見ながら version を固定

## 導入時の補足事項

### label 名と description を丁寧に作る

公式 docs では、field description は extraction accuracy の改善に使えると説明されています。
似た項目が多いカードでは、`description` に「この項目は消費コストであり、購入価格ではない」のような差分説明を書く価値があります。

### document-level prompt は補助として使える

Custom extractor mechanisms では document-level prompt も用意されています。
今回なら「この文書は TRPG ルールブックであり、対象はカード状のゲームデータだけで、本文説明は抽出対象外」のような全体ヒントを入れる余地があります。
ただし、これは厳格なルールエンジンではなく、補助的なヒントと考えるべきです。

### automated schema generation は補助用途

自動 schema 生成は便利ですが、公式 docs 上では Preview / Pre-GA です。
したがって、本番 schema を完全に任せるのではなく、初期たたき台の生成に使って人手で詰める前提が安全です。

## 最終提案

この repo の対象が本当に「TRPG 書籍内のカード状ゲームデータのみ」であり、「カード外本文は対象外」であるなら、理想は次です。

1. 本番本命は `CUSTOM_EXTRACTION_PROCESSOR`
2. カードのレイアウトが固定なら template-based
3. レイアウトが揺れるなら custom model-based
4. 可能なら upstream で card region を切り出してから処理
5. 既存の `OCR_PROCESSOR` + Gemini は PoC / 暫定運用として位置づける

## 参考資料

- [Processor list](https://docs.cloud.google.com/document-ai/docs/processors-list)
- [Extraction overview](https://docs.cloud.google.com/document-ai/docs/extracting-overview)
- [Custom extractor overview](https://docs.cloud.google.com/document-ai/docs/custom-extractor-overview)
- [Custom extractor mechanisms](https://docs.cloud.google.com/document-ai/docs/ce-mechanisms)
- [Template-based extraction](https://docs.cloud.google.com/document-ai/docs/ce-template-based)
- [Custom-based extraction](https://docs.cloud.google.com/document-ai/docs/custom-based-extraction)
- [Custom extractor with generative AI](https://docs.cloud.google.com/document-ai/docs/ce-with-genai)
- [Label documents](https://docs.cloud.google.com/document-ai/docs/label-documents)
- [Form Parser](https://docs.cloud.google.com/document-ai/docs/form-parser)
- [Process documents with Gemini layout parser](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk)
- [Automated schema generation](https://docs.cloud.google.com/document-ai/docs/ce-schema-extraction)
