# nova-parser OCR アプリケーション実装プラン

## Context

`nova-parser` は Images/ ディレクトリ内の画像を Gemini で OCR するアプリケーション。現在 `main.py` にはクライアント初期化と画像リスト取得のみ実装済みで、OCR ロジックは TODO 状態。これを、指定ディレクトリ配下の画像ファイル (jpg, png, tif, webp) を Gemini で OCR し、レイアウトを構造化した Markdown として出力する完全なアプリケーションに仕上げる。将来的に複雑な条件でのテキスト化を行うため、CLI オプションで拡張可能な設計にする。

## 技術的制約

- **TIFF 非サポート**: Gemini API は TIFF を直接受け付けない → Pillow で JPEG に変換が必要
- **インラインデータ制限**: Vertex AI Express モードでは 7MB まで → 大きい画像はリサイズが必要
- **最大有効解像度**: Gemini は 3072x3072 にスケールダウンする → 事前にリサイズすると効率的
- **Files API 不可**: `vertexai=True` では `client.files.upload()` が使えない → `Part.from_bytes()` を使用

## 実装ステップ

### Step 1: Pillow 依存の追加

```bash
uv add Pillow
```

### Step 2: `main.py` を全面改修

**CLI インターフェース (argparse)**:

```
uv run main.py <input_dir> [options]
```

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `input_dir` (位置引数) | - | 画像が格納されたディレクトリパス |
| `-o, --output-dir` | `./output` | 出力先ディレクトリ |
| `-m, --model` | `gemini-2.5-flash` | 使用する Gemini モデル |
| `-p, --prompt` | (組み込みデフォルト) | OCR 用カスタムプロンプト |
| `--extensions` | `.jpg,.jpeg,.png,.tif,.tiff,.webp` | 処理対象の拡張子 |
| `--max-size` | `4096` | 送信前の最大辺ピクセル数 |
| `--quality` | `90` | JPEG 変換時の品質 (1-100) |
| `--temperature` | `0.1` | Gemini の temperature |
| `--overwrite` | `False` | 既存の出力ファイルを上書きするか |

**処理フロー**:

```
1. CLI引数パース
2. 入力ディレクトリから対象画像をリスト
3. 出力ディレクトリを作成
4. 各画像に対して:
   a. Pillow で読み込み
   b. 非対応フォーマット (TIFF等) は JPEG に変換
   c. 最大辺が max-size を超える場合はリサイズ
   d. 7MB 以下になるよう品質調整
   e. types.Part.from_bytes() で Gemini に送信
   f. レスポンスを Markdown ファイルとして保存
5. 処理結果サマリーを表示
```

**デフォルト OCR プロンプト** (レイアウト構造化重視):

```
この画像に含まれるすべてのテキストを正確に抽出してください。

以下のルールに従ってください:
- 元のレイアウト・段落構造をできる限り保持する
- 表はMarkdownテーブル形式で出力する
- 見出し・タイトルは適切なMarkdown見出し（#, ##等）で表現する
- 箇条書きはMarkdownのリスト記法で表現する
- 縦書きテキストも正確に読み取る
- 読み取れない文字は [不明] と記載する
- ヘッダー・フッター・ページ番号も含める
- テキストの読み取り順序は左から右、上から下を基本とする
- 画像や図表にはその内容を簡潔に [図: 説明] の形式で記載する
```

**主要関数**:

- `parse_args()` → argparse による CLI パーサ
- `get_client()` → 既存の Gemini クライアント初期化（変更なし）
- `list_images(input_dir, extensions)` → 既存関数を引数対応に拡張
- `prepare_image(image_path, max_size, quality)` → 画像読み込み・変換・リサイズ。`(bytes, mime_type)` を返す
- `ocr_image(client, image_bytes, mime_type, model, prompt, temperature)` → Gemini API を呼び出して OCR 実行。テキストを返す
- `save_result(text, output_path)` → Markdown ファイルに保存
- `main()` → 全体フローの制御

## 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `main.py` | OCR ロジック全体を実装（全面改修） |
| `pyproject.toml` | `Pillow` 依存を追加 (uv add で自動) |

## 検証方法

```bash
# テスト実行（Images/ 直下の NAN_067.tif で検証）
uv run main.py Images/ -o output/

# 出力確認
cat output/NAN_067.md

# カスタムオプションでの実行テスト
uv run main.py Images/ -o output/ --model gemini-2.5-flash --temperature 0.2

# カスタムプロンプトでの実行テスト
uv run main.py Images/ -o output/ -p "テキストのみを抽出してください"
```
