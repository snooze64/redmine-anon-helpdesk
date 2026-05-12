# Redmine デプロイテンプレート

Docker Compose で Redmine 6 を立ち上げ、匿名性確保のための [redmine_hidden_user_profile](https://github.com/JGallot/redmine_hidden_user_profile) プラグインを組み込んだ最小構成のテンプレートです。問い合わせ対応・ヘルプデスク・社内ナレッジベース等で **質問者間で互いの存在を隠したい** ユースケースを想定しています。

## 主な機能

- **Redmine 6 + MySQL 8** を 1 コマンドで起動（Docker Compose）
- **匿名性プラグイン** をビルド時に同梱
  - 一般ユーザーが他ユーザーのプロフィール (`/users/:id`) を開けないようにする
  - 担当者/ウォッチャーのリンクをプレーンテキスト化
- **チャットボット連携用の FastAPI ブリッジ** をオプションで同梱
  - `POST /users` でユーザー登録、`POST /memberships` で割当、`POST /tickets` で起票
  - 起票時に質問者と「回答者」ロール保持者全員が watcher 自動登録
  - 必要なときだけ `compose.api.yml` を追加で読ませる opt-in 構成
- **RAG チャットボット** (Ollama + ChromaDB + Streamlit) をさらにオプションで同梱
  - Redmine の指定プロジェクトのチケットをベクトル化し、過去の解決記録から回答
  - **Human-in-the-Loop UX**: クローズ / 継続 / 人にエスカレーション の 3 ボタン
  - エスカレーション時は内部で API ブリッジ経由で Redmine 起票
  - 差分更新クローラ (`updated_on` 基準で再ベクトル化)、定期実行も APScheduler で対応
- **SMTP の切替** を `.env` だけで実現
  - `mailpit`（開発時、メールをローカル捕獲）/ `gmail`（個人検証）/ `custom`（任意の SMTP サーバー）
- **環境変数による完全な設定外部化**
  - ポート / コンテナ名 / DB 認証情報 / プロキシ / Redmine secret_key_base — すべて `.env` で上書き可
- **オフライン環境対応**
  - イメージビルド時のプロキシ設定を渡せる
  - インターネット遮断環境向けに `docker save / load` 経由のデプロイ手順を docs に記載
- **Web UI セットアップ手順書を完備** — ロール作成・ユーザー作成・通知設定まで全て GUI 操作で完結

## 構成

```
┌─────────────────────────────────────────────────────────────┐
│ Docker host                                                 │
│                                                             │
│  ┌─────────────┐ optional ┌───────────┐  ┌──────────┐       │
│  │ api         │─────────>│ redmine   │──│ db       │       │
│  │ (FastAPI)   │ HTTP     │ (Rails)   │  │ (MySQL 8)│       │
│  └─────────────┘          └─────┬─────┘  └──────────┘       │
│       ▲                         │ SMTP                      │
│       │ HTTP (chatbot)          ▼                           │
│       │                  ┌──────────────────────────┐       │
│       │                  │ SMTP_PROVIDER で切替    │        │
│       │                  │  mailpit / gmail / custom│       │
│       │                  └──────────────────────────┘       │
└───────┼─────────────────────────────────────────────────────┘
        │
   [Chatbot 等の外部システム]

公開ポート (既定値):
  - 3080  Redmine Web UI       (http://localhost:3080)
  - 13306 MySQL                (mysql client から接続用)
  - 8025  Mailpit Web UI       (Mailpit 利用時のみ)
  - 8000  FastAPI ブリッジ     (Mode B のみ、http://localhost:8000)
```

## クイックスタート

### 必要なもの

- Docker Desktop（または Docker Engine + Compose v2.20+）
- Git

### 用途別の起動モード

このリポジトリは 2 通りの起動モードをサポートしています。**どちらを選ぶかで使うコマンドが変わるだけ**で、`.env` などの設定ファイルは共通です。

| モード | 含まれるもの | こんなときに |
|---|---|---|
| **Mode A: Redmine だけ** | Redmine + MySQL（+ Mailpit を有効化していれば） | Web UI から手動でチケット管理する。プラグインの動作確認だけしたい |
| **Mode B: Redmine + API** | 上記 + FastAPI ブリッジ | チャットボット等の外部システムから REST 経由でチケットを起票したい |
| **Mode C: Redmine + API + Chatbot** | 上記 + Ollama + ChromaDB + Streamlit | 過去チケットを RAG ソースに AI 回答 + Human-in-the-Loop でエスカレーション |

### 共通の事前準備

```bash
# 1. クローン
git clone https://github.com/snooze64/redmine-anon-helpdesk.git
cd redmine-anon-helpdesk

# 2. 環境変数のテンプレートをコピー (中身は何も変更しなくても起動できる)
cp .env.example .env

# 3. Redmine プラグインを host 側に取得 (推奨セットを clone)
#    Windows: .\tools\install_plugins.ps1
#    Linux/macOS: ./tools/install_plugins.sh
```

> 本リポジトリは **プラグインを Docker イメージに焼き込まず、ホストの
> `./plugins/` を bind-mount で読み込む** 方式です。プラグインの追加・更新は
> ホスト側で `git clone` / `git pull` するだけで、再ビルドは不要。詳細は
> [docs/plugin_install.md](docs/plugin_install.md) 参照。

### Mode A: Redmine だけ起動

```bash
# 4a. ビルド & 起動 (docker-compose.yml だけを使用)
docker compose build
docker compose up -d

# 5a. プラグインを Redmine に反映 (plugins:migrate + tmp:clear + restart)
#     初回または ./plugins/ 配下を変更したときに実行
#     Windows: .\tools\refresh_plugins.ps1
#     Linux/macOS: ./tools/refresh_plugins.sh

# 6a. ブラウザで開く
#     http://localhost:3080
#     初回ログイン: admin / admin → 強制パスワード変更
```

### Mode B: Redmine + API を一緒に起動

```bash
# 4b. ビルド & 起動 (docker-compose.yml に compose.api.yml を重ねる)
docker compose -f docker-compose.yml -f compose.api.yml build
docker compose -f docker-compose.yml -f compose.api.yml up -d

# 5b. プラグインを Redmine に反映 (Mode A と同じく refresh_plugins を実行)

# 6b. Redmine とブリッジ API の両方が起動
#     - http://localhost:3080      Redmine
#     - http://localhost:8000      FastAPI
#     - http://localhost:8000/docs Swagger UI (API 仕様)
```

> ❗ Mode B でブリッジ API を実際に使う前に、`管理 → 設定 → API → 「REST による Web サービス」` で REST API を有効化する必要があります（または下記の `Setting.rest_api_enabled = '1'` を実行）。Mode A しか使わないなら不要です。
>
> 詳細・エンドポイント仕様・接続情報の設定方法は **[api/README.md](api/README.md)** を参照。

### Mode C: Redmine + API + Chatbot をフルスタック起動

```bash
# 4c. ビルド & 起動 (3 つの compose ファイルを重ねる)
docker compose -f docker-compose.yml -f compose.api.yml -f compose.chatbot.yml build
docker compose -f docker-compose.yml -f compose.api.yml -f compose.chatbot.yml up -d

# 5c. プラグインを Redmine に反映 (Mode A と同じく refresh_plugins を実行)

# 6c. 初回のみ: Ollama に LLM と embedding モデルを pull (数 GB)
docker exec redmine-ollama ollama pull qwen2.5:7b
docker exec redmine-ollama ollama pull nomic-embed-text

# 7c. ブラウザで開く
#     - http://localhost:3080  Redmine
#     - http://localhost:8000  ブリッジ API (Swagger UI: /docs)
#     - http://localhost:8100  Chatbot バックエンド (Swagger UI: /docs)
#     - http://localhost:8501  Chatbot UI (Streamlit, 3 ボタン HITL)
#     - http://localhost:11435 Ollama (任意、ホストの別 Ollama 衝突回避のため標準ポートからずらしている)
```

> ❗ Mode C は Mode B の前提（REST API 有効化、認証情報設定）に加え、**Ollama のモデル pull** が必要です。`qwen2.5:7b` は約 4.7 GB あり、初回 pull に時間がかかります。
>
> 詳細・チューニング項目・トラブルシューティングは **[chatbot/README.md](chatbot/README.md)** を参照。

#### Mode C 固有の Redmine 側追加セットアップ

Mode C を実際に使うには、Mode A / B のセットアップに加えて以下が必要です:

1. **質問者ロールに「チケットの追加」権限を付与** ([docs/manual_setup.md §1-1](docs/manual_setup.md))
   - チャットボットが質問者本人として impersonate 起票するために必要
   - これだけだと UI からも直接起票できてしまうので 2 で抑止する
2. **View Customize プラグインで「+ 新しいチケット」 UI を抑止** ([docs/view_customize_setup.md](docs/view_customize_setup.md))
   - グローバルページは全員、プロジェクト内は質問者ロールのみ、起票 UI を非表示にする
3. **(任意) Chatbot Session カスタムフィールドで監査** ([docs/manual_setup.md §9-2](docs/manual_setup.md))
   - チャットボット経由・UI 直叩きの起票を後追いで区別したいとき

チャットボット利用者向けの操作マニュアルは **[docs/chatbot_usage.md](docs/chatbot_usage.md)**。

### 共通の初期セットアップ（Mode A / B 共通）

ここまでで Redmine 本体が動いていますが、ロール・トラッカー等の **既定データ投入が必要**です:

```bash
# 5. 既定構成データ (Manager/Developer/Reporter ロール、Bug/Feature/Support トラッカー等) を投入
docker compose exec -T -e REDMINE_LANG=ja redmine bundle exec rake redmine:load_default_data
```

### 6. ロール・ユーザー・プロジェクト作成

ここから先は管理 UI で操作します。**[docs/manual_setup.md](docs/manual_setup.md)** に画面遷移付きの手順書があります（ロール `質問者` / `回答者` 作成、`Show user profile` 権限の制御、メール通知設定、サンプルチケット投入まで）。

### 起動モードの切替

途中で Mode A → Mode B に切り替えたい場合、起動コマンドを `-f compose.api.yml` 付きで実行し直すだけで OK です。逆に Mode B → A に戻したい場合は `docker compose -f docker-compose.yml -f compose.api.yml down api`（API だけ停止）または通常の `docker compose down`（全停止）を使ってください。

データボリューム（DB/添付ファイル）は両モードで共通なので、切り替えてもデータは保持されます。

## 設定変数

すべての設定は **[.env.example](.env.example)** にコメント付きで列挙されています。代表的なもの:

| 変数 | 既定値 | 用途 |
|---|---|---|
| `REDMINE_PORT` | `3080` | Redmine の公開ポート |
| `MYSQL_PORT` | `13306` | MySQL の公開ポート |
| `SMTP_PROVIDER` | `mailpit` | `mailpit` / `gmail` / `custom` から選択 |
| `REDMINE_SECRET_KEY_BASE` | プレースホルダ | **本番投入前に必ず変更** (`openssl rand -hex 64` 推奨) |
| `MYSQL_PASSWORD` | `redmine_pw` | **本番投入前に必ず変更** |
| `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` | 空 | プロキシ環境の場合に設定（小文字版もあり） |

`.env` を変更したら `docker compose up -d` で再起動して反映。

### Mailpit (開発用 SMTP キャッチサーバー) を有効化したい場合

既定で **コメントアウト** されています。利用する場合は `docker-compose.yml` の `mailpit:` サービスブロックと `redmine.depends_on:` 配下の `mailpit:` 3 行のコメントを外し、`docker compose up -d`。詳細は [.env.example](.env.example) または [docs/manual_setup.md §4-1-a](docs/manual_setup.md) 参照。

## ドキュメント

| 文書 | 内容 |
|---|---|
| [docs/manual_setup.md](docs/manual_setup.md) | Web UI のみで完結する全セットアップ手順（ロール、ユーザー、プロジェクト、SMTP、サンプルチケット、動作確認、§9 で Mode C 固有の追加設定） |
| [docs/plugin_install.md](docs/plugin_install.md) | プラグイン管理ガイド (host bind-mount 方式) — 追加・更新・削除のフロー、`tools/install_plugins`・`refresh_plugins`・`reset_plugin_state` の使い方、トラブルシューティング |
| [docs/view_customize_setup.md](docs/view_customize_setup.md) | (Mode C 用) View Customize プラグインで「+ 新しいチケット」を抑止する手順 — グローバルは全員、プロジェクト内は質問者のみ非表示 |
| [docs/chatbot_usage.md](docs/chatbot_usage.md) | (Mode C 用) チャットボット利用者向けマニュアル — LLM 切替、エスカレーション、private チケットの見え方 |
| [api/README.md](api/README.md) | Mode B のチャットボット連携用 FastAPI ブリッジの仕様 — エンドポイント・接続情報・想定ユースケース |
| [chatbot/README.md](chatbot/README.md) | Mode C の RAG チャットボットの仕様 — クローラ / ベクトル DB / Ollama / HITL UX |

## 動作確認済み環境

- Redmine **6.1.x**
- MySQL **8.0**
- Docker Compose **v2.20+**（`depends_on.required: false` を使用）
- Ruby **3.4** / Rails **7.2**（Redmine 6 のベースイメージ依存）

## 依存プラグイン

`./tools/install_plugins.{ps1,sh}` で host の `./plugins/` に取得します
(Dockerfile に焼き込まず host bind-mount で読み込む方式)。詳細は
[docs/plugin_install.md](docs/plugin_install.md)。

| プラグイン | 用途 | リポジトリ |
|---|---|---|
| `redmine_hidden_user_profile` | プロフィール画面・ユーザーリンクの権限ベース非表示化 (匿名性) | https://github.com/JGallot/redmine_hidden_user_profile |
| `view_customize` (Mode C 用) | 任意 URL に JS/CSS 注入 — 質問者ロールから「+ 新しいチケット」を非表示にして起票経路をチャットボットに統一する | https://github.com/onozaty/redmine-view-customize |

> `redmine_hidden_user_profile` は LICENSE ファイルが提供されていません。本リポジトリはイメージに焼き込まず host bind-mount で読み込むだけで再配布はしていませんが、フォーク・ベンダリングして利用する場合は元プラグインのライセンス状況をご確認ください。

## ライセンス

本テンプレートは MIT License で配布します（[LICENSE](LICENSE) を後で追加してください）。

依存先プラグイン・ベースイメージ・dependent gems のライセンスはそれぞれの提供元に従います。

## ステータス

- 個人利用 / 内部利用向けのテンプレートとして作成
- 本番運用前には少なくとも以下を確認してください:
  - `REDMINE_SECRET_KEY_BASE` を強い乱数値に変更
  - `MYSQL_*` パスワードを強い値に変更
  - `MYSQL_PORT` を `0.0.0.0` に公開する必要があるか（不要ならポート行を削除）
  - SMTP プロバイダを本番用に切替
- バグ報告・改善提案歓迎
