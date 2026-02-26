# MCP サーバー設定

Claude Code から外部ドキュメントを直接検索・参照するための MCP（Model Context Protocol）サーバーの設定手順です。

## 設定ファイル

MCP サーバーはプロジェクトルートの `.mcp.json` で管理されます。このファイルはリポジトリにコミットされており、`claude code` 起動時に自動で読み込まれます。

## 設定済みサーバー一覧

| サーバー名 | 用途 | トランスポート |
|---|---|---|
| `context7` | 任意のライブラリ・フレームワークのドキュメント検索 | stdio |
| `google-dev-knowledge` | Google 公式開発者ドキュメントの検索 | http |

## Google Developer Knowledge API

Google が提供する Developer Knowledge API の MCP サーバー。Android、Firebase、Chrome、Google Cloud 等の公式開発者ドキュメントを Claude Code から直接検索・参照できます。

### 前提条件

API キー認証が必要です。API の有効化 → MCP の有効化 → キー作成の順で設定します。

**方法 A: Google Cloud Console**

1. https://console.cloud.google.com/ でプロジェクトを選択（または新規作成）
2. 「API とサービス」→「有効な API とサービス」で **Developer Knowledge API** を有効化
3. **MCP を有効化する**（API 有効化とは別に必要）:
   ```bash
   gcloud beta services mcp enable --service=developerknowledge.googleapis.com --project=PROJECT_ID
   ```
4. 「認証情報」→「認証情報を作成」→「API キー」でキーを作成
5. API キーの制限で Developer Knowledge API のみに限定（推奨）

**方法 B: gcloud CLI**

```bash
# 1. API を有効化
gcloud services enable developerknowledge.googleapis.com --project=PROJECT_ID

# 2. MCP を有効化（API 有効化とは別に必要）
gcloud beta services mcp enable --service=developerknowledge.googleapis.com --project=PROJECT_ID

# 3. API キーを作成
gcloud services api-keys create --project=PROJECT_ID --display-name="DK API Key"
```

> **注意**: `gcloud beta` コマンドが未インストールの場合は `gcloud components install beta` で追加してください。

取得したキーを `.env` に設定します:

```
GOOGLE_DEV_KNOWLEDGE_API_KEY=取得したAPIキー
```

> **注意（devcontainer 環境）**: `.env` は devcontainer 起動時に `--env-file` で読み込まれます（`devcontainer.json` の `runArgs` で指定）。**起動後に `.env` を変更した場合、シェル環境には自動反映されません。** 変更を反映するには devcontainer を再ビルド（Rebuild Container）してください。

### 設定

`.mcp.json` に以下のエントリを追加します（設定済み）:

```json
{
  "mcpServers": {
    "google-dev-knowledge": {
      "type": "http",
      "url": "https://developerknowledge.googleapis.com/mcp",
      "headers": {
        "X-Goog-Api-Key": "${GOOGLE_DEV_KNOWLEDGE_API_KEY}"
      }
    }
  }
}
```

- **認証**: API キー必須（`X-Goog-Api-Key` ヘッダーで送信）
- **トランスポート**: Streamable HTTP（Claude Code 推奨のリモート MCP 接続方式）
- **環境変数展開**: `.mcp.json` の `${GOOGLE_DEV_KNOWLEDGE_API_KEY}` は `.env` の値で自動展開される

### 利用可能なツール

| ツール | 説明 |
|---|---|
| `search_documents` | Google 開発者ドキュメント全体からキーワード検索 |
| `get_document` | 単一ドキュメントの完全なコンテンツを取得 |
| `batch_get_documents` | 最大 20 ドキュメントを一括取得 |

### 使い方

Claude Code への指示に **「Google 公式ドキュメント」** や **「Google 開発者ドキュメント」** を含めると、このサーバーが優先的に使用されます。これらのキーワードがないと Context7 や WebSearch など別のツールが選ばれる場合があります。

**指示例**:

| やりたいこと | 指示例 |
|---|---|
| キーワード検索 | `Google 公式ドキュメントで「Firestore セキュリティルール」を検索して` |
| 実装の参考にしたい | `Google 公式ドキュメントで Vertex AI の Python SDK の使い方を調べて` |
| 対象プロダクトを限定 | `Android 公式ドキュメントで Jetpack Compose のレイアウトについて調べて` |
| 全文取得も含める | `Google 公式ドキュメントで Cloud Run のデプロイ手順を検索して、該当ドキュメントの全文も取得して` |

**確実にこのツールを使わせたい場合** はツール名を直接指定できます:

```
search_documents ツールで「Cloud Functions triggers」を検索して
```

### 対象プロダクト

Android、Chrome、Firebase、Google Cloud、Google AI、TensorFlow、Google Home、Fuchsia、Apigee、Web (web.dev) 等の Google 開発者ドキュメント全般。

### 接続確認

1. `.mcp.json` 編集後、Claude Code セッションを再起動する
2. `/mcp` コマンドを実行し、`google-dev-knowledge` が connected 状態であることを確認する
3. 検索テストとして、Google Cloud 等のドキュメントを検索してみる

## Context7

任意のプログラミングライブラリ・フレームワークの最新ドキュメントとコード例を検索できる MCP サーバーです。

### 設定

`.mcp.json` に以下のエントリを追加します（設定済み）:

```json
{
  "mcpServers": {
    "context7": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"],
      "env": {}
    }
  }
}
```

- **認証**: 不要
- **トランスポート**: stdio（ローカルプロセスとして起動）
- **前提条件**: Node.js と npm がインストールされていること

### 利用可能なツール

| ツール | 説明 |
|---|---|
| `resolve-library-id` | パッケージ名から Context7 互換のライブラリ ID を解決 |
| `query-docs` | ライブラリ ID を指定してドキュメント・コード例を取得 |

## トラブルシューティング

### サーバーが connected にならない

- `/mcp` で状態を確認する
- `.mcp.json` の JSON 構文が正しいか確認する（末尾カンマ等）
- Claude Code セッションを再起動する

### http タイプのサーバーに接続できない

- ネットワーク接続を確認する
- プロキシ環境下の場合、プロキシ設定を確認する
- API キーが必要なサーバーの場合、`.env` にキーが正しく設定されているか確認する
- `google-dev-knowledge` の場合、`GOOGLE_DEV_KNOWLEDGE_API_KEY` が `.env` に設定されているか確認する

### google-dev-knowledge で認証エラーが発生する

- **MCP が有効化されているか確認する**: API の有効化だけでは不十分です。以下のコマンドで MCP を有効化してください:
  ```bash
  gcloud beta services mcp enable --service=developerknowledge.googleapis.com --project=PROJECT_ID
  ```
- **API キーが環境変数に読み込まれているか確認する**: devcontainer 環境では、`.env` の変更後に再ビルドが必要です（`echo $GOOGLE_DEV_KNOWLEDGE_API_KEY` で確認）

### API クォータ超過エラー（429）

- Developer Knowledge API にはリクエストレートの制限があります
- Google Cloud Console の「API とサービス」→「割り当て」でクォータの使用状況を確認してください
- 頻繁に発生する場合はクォータの引き上げをリクエストしてください

### stdio タイプのサーバーが起動しない

- `npx` コマンドが利用可能か確認する（`which npx`）
- Node.js のバージョンが十分か確認する
