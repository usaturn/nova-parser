# 半構造化パイプライン（semistructure）運用手順

OCR の `*.regions.json` を、追跡可能な正本 JSONL（`segments.jsonl`）と Ruri 向け派生ビューへ変換する。対象例は『エンゼルギア 天使大戦TRPG The 2nd Edition』（EG 全 153 ページ / 748 領域）。

エントリポイント:

```bash
uv run nova-parser-semistructure --help
```

## 1. 運用手順（初回〜Ruri 引き渡し）

次の順序で進める。

### 1.1 dry-run で入力件数を確認する

```bash
uv run nova-parser-semistructure \
  --manifest config/semistructure/angel_gear_2e.json \
  --input-dir Output/EG \
  --output-dir Output/EG_semistructured \
  --dry-run
```

期待:

```text
pages=153 regions=748
llm_calls=0
input_errors=0
```

`input_errors=0` を確認してから通常実行へ進む。worktree 上に `Output/EG` が無い場合は本体リポジトリの絶対パスを `--input-dir` に渡す。

### 1.2 API キーを設定し通常実行する

`.env` に Vertex / Gemini のキーを設定する（例: `GOOGLE_GENAI_USE_VERTEXAI`, `VERTEX_AI_API_KEY`）。

```bash
uv run nova-parser-semistructure \
  --manifest config/semistructure/angel_gear_2e.json \
  --input-dir Output/EG \
  --output-dir Output/EG_semistructured
```

通常実行のサマリ例:

```text
pages=153 regions=748
llm_calls=...
input_errors=0
source_coverage=100.00%
validation_errors=0
segments=...
review_required=...
```

部分ページだけ LLM が失敗した場合は終了コード 0 のまま `failed_pages=...` と `review_required=...` が標準出力に出る（失敗ページは `unknown` フォールバックで正本に載る）。

### 1.3 `review/pending.md` を確認する

出力先の `review/pending.md` を上から確認する。優先順の目安:

1. `audience_downgrade_candidate`（最優先）
2. 別領域結合・ページまたぎ
3. 表・能力値・ルビ
4. 分類失敗フォールバック（`classifier_failure` 等）

同一内容は `review/queue.jsonl` にも JSONL で残る。

### 1.4 判断を `review/decisions.jsonl` へ追記する

1 行 1 JSON で記録する（`ReviewDecision` スキーマ）。例:

```json
{"review_id":"angel_gear_2e:<segment_id>","decision":"accept","audience":"gm","notes":"シナリオ本文"}
```

### 1.5 同じコマンドを再実行して判断を適用する

```bash
uv run nova-parser-semistructure \
  --manifest config/semistructure/angel_gear_2e.json \
  --input-dir Output/EG \
  --output-dir Output/EG_semistructured \
  --review-decisions Output/EG_semistructured/review/decisions.jsonl
```

入力ハッシュが変わって古くなった判断は再レビュー対象になる。ページ単位キャッシュを無視して再分類する場合は `--no-cache` を付ける（正本の原文検証は常に実行される）。

### 1.6 受入条件を確認する

次を満たすまで Ruri 入力を本番利用しない。

| 条件 | 確認方法 |
|------|----------|
| 原文被覆率 100% | サマリ `source_coverage=100.00%` |
| 検証エラー 0 | サマリ `validation_errors=0` |
| `audience=unknown` に未解決理由 | 正本 / レビューキュー |
| プレイヤー派生に `gm` / `unknown` が 0 件 | `derived/*` の audience メタ |
| 代表 6 ページの構造評価がベースライン超 | `--evaluate-gold` |
| 質問応答・類似探索がベースライン超 | 評価セット（`gold-queries.jsonl`） |

構造評価の例:

```bash
uv run nova-parser-semistructure \
  --output-dir Output/EG_semistructured \
  --evaluate-gold tests/fixtures/semistructure/gold-segments.jsonl
```

### 1.7 派生ビューを Ruri サービスへ渡す

- `derived/retrieval-inputs.jsonl` … 文書入力として埋め込む
- `derived/topic-inputs.jsonl` … トピック入力として埋め込む
- 問い合わせは別途 `検索クエリ: ` プレフィックスを付ける

**必須**: Ruri サービスが明示的な `input_type`（`document` / `topic` / `query`）を受け取れること。受け取れない場合は埋め込み処理を開始せず、サービス改修を別リポジトリの独立計画として扱う。

**禁止**: 現行の「100 文字未満を自動的に問い合わせ扱いする」判定 API へ投入してはならない。

ベクトルとメタデータは同じ `segment_id` で結び付ける。

### 1.8 `audience` フィルタをベクトル検索前に適用する

プレイヤー検索ではベクトル検索の**前**に次を適用する。

```text
audience in {"player", "shared"}
```

`gm` と `unknown` はプレイヤー向け結果に出さない（fail-closed）。

## 2. CLI リファレンス

```bash
uv run nova-parser-semistructure \
  --manifest PATH \
  --input-dir PATH \
  --output-dir PATH \
  [--review-decisions PATH] \
  [--no-cache] \
  [--dry-run] \
  [--evaluate-gold PATH]
```

| 引数 | 説明 |
|------|------|
| `--manifest` | 書籍マニフェスト JSON（パイプライン実行時は必須） |
| `--input-dir` | `*.regions.json` の入力ディレクトリ |
| `--output-dir` | 正本・派生・レビューの出力先 |
| `--review-decisions` | 人手判断 JSONL（任意） |
| `--no-cache` | ページ単位キャッシュの読み取りを無効化 |
| `--dry-run` | LLM を呼ばず入力検査と正規化まで |
| `--evaluate-gold` | gold セグメントとの構造比較。manifest/input 無しなら評価のみ |

### 終了コード

| コード | 意味 |
|--------|------|
| 0 | 成功。部分ページの LLM 失敗でも fallback が書けていれば 0（`failed_pages` / `review_required` を stdout に明示） |
| 1 | 実行前エラー（API キー未設定、評価対象ファイル欠落など） |
| 2 | 入力不正（マニフェスト / regions 読み取り失敗など）。`ValueError` / `FileNotFoundError` / `OSError` を CLI が捕捉して 2 にする。レポートの `input_errors` フィールドは件数表示用で、現状パイプラインは常に 0 を返し、実際の入力不正は例外経路で exit 2 になる |
| 3 | LLM が全ページで失敗 |
| 4 | 正本（provenance）検証エラー（`validation_errors>0`） |

プレイヤー可視性（GM/unknown のレビュー要）は終了コード 4 にはしない。レビューキューへ回し `review_required` として件数を出す。

### 出力レイアウト

```text
{output-dir}/
  segments.jsonl                 # 正本
  review/
    pending.md                   # 人手レビュー用 Markdown
    queue.jsonl                  # レビュー項目 JSONL
    decisions.jsonl              # （任意）人手判断の置き場
  derived/
    retrieval-inputs.jsonl       # Ruri 文書入力
    topic-inputs.jsonl           # Ruri トピック入力
  failures/                      # LLM JSON 失敗アーティファクト
  .cache/                        # ページ単位 StructureProposal キャッシュ
```

## 3. バージョンとトレーサビリティ

| 項目 | 値 / 場所 |
|------|-----------|
| プロンプト契約 | `PROMPT_CONTRACT_VERSION = semistructure-reference-selection-v1`（`llm.py`） |
| 正規化規則 | `NORMALIZE_RULE_VERSION = ja-word-wrap-v1`（`pipeline.py`） |
| 既定モデル | `FLASH_MODEL`（`nova_parser.ocr`）を `GeminiStructureClassifier` が使用 |
| 分類器 ID | `gemini:{model}:{PROMPT_CONTRACT_VERSION}` |
| マニフェスト | `config/semistructure/angel_gear_2e.json`（`schema_version` / 聴衆・文書種別 override） |
| キャッシュキー | 入力 SHA / manifest SHA / 正規化版 / 契約版 / classifier_id / schema_version |

正本セグメントの `processing` に `classifier_id` や `prompt_contract_version` が残る。

## 4. 評価フィクスチャと segment_id について

- 構造正解: `tests/fixtures/semistructure/gold-segments.jsonl`（代表 6 ページ: 22 / 23 / 203 / 249 / 251 / 259）
- 検索正解: `tests/fixtures/semistructure/gold-queries.jsonl`
- 入力サンプル: 同ディレクトリの `manifest.json` / `p022.regions.json` / `p234.regions.json`

**注意**: gold の `segment_id`（例: `eg:p022:heading`）は人手ラベル用の安定 ID であり、パイプラインが生成するハッシュベース ID（`{book_id}-{sha256[:16]}`）とは一致しない。`--evaluate-gold` の `segment_id` 対応付けは、ID 一致を前提とする現行メトリクスでは境界一致率が低く出ることがある。評価時は `source_coverage` と audience の critical エラーを優先して解釈し、ID 不一致を理由に埋め込みや本番引き渡しを開始しないこと。

本リポジトリの semistructure パイプラインは Ruri への埋め込み API 呼び出しを行わない。派生 JSONL を明示的 `input_type` 対応済みサービスへ渡すのは運用側の責務である。

## 5. ステージ順（参考）

```text
load manifest
→ load and validate OCR pages
→ normalize deterministic blocks
→ [dry-run: 件数返却して終了]
→ infer one coarse book outline
→ classify page windows (cache read/write)
→ assemble canonical segments
→ apply valid review decisions
→ validate provenance and visibility
→ write canonical JSONL
→ write review queue / Markdown
→ write Ruri retrieval/topic views (player mode, REJECTED 除外)
```
