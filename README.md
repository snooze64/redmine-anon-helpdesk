# Redmine デプロイテンプレート

Docker Compose で Redmine 6 を立ち上げ、匿名性確保のための [redmine_hidden_user_profile](https://github.com/JGallot/redmine_hidden_user_profile) プラグインを組み込んだ最小構成のテンプレートです。問い合わせ対応・ヘルプデスク・社内ナレッジベース等で **質問者間で互いの存在を隠したい** ユースケースを想定しています。

## 主な機能

- **Redmine 6 + MySQL 8** を 1 コマンドで起動（Docker Compose）
- **匿名性プラグイン** をビルド時に同梱
  - 一般ユーザーが他ユーザーのプロフィール (`/users/:id`) を開けないようにする
  - 担当者/ウォッチャーのリンクをプレーンテキスト化
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
┌─────────────────────────────────────────────────┐
│ Docker host                                     │
│  ┌───────────┐  ┌──────────┐                    │
│  │ redmine   │──│ db       │                    │
│  │ (Rails 7) │  │ (MySQL 8)│                    │
│  └─────┬─────┘  └──────────┘                    │
│        │ SMTP                                   │
│        ▼                                        │
│  ┌──────────────────────────────────┐           │
│  │ SMTP_PROVIDER で切替             │           │
│  │  - mailpit (開発、内部に貯める)  │           │
│  │  - gmail   (Gmail 経由で送信)    │           │
│  │  - custom  (任意の SMTP サーバー)│           │
│  └──────────────────────────────────┘           │
└─────────────────────────────────────────────────┘

公開ポート (既定値):
  - 3080  Redmine Web UI       (http://localhost:3080)
  - 13306 MySQL                (mysql client から接続用)
  - 8025  Mailpit Web UI       (Mailpit 利用時のみ)
```

## クイックスタート

### 必要なもの

- Docker Desktop（または Docker Engine + Compose v2.20+）
- Git

### 手順

```bash
# 1. クローン
git clone https://github.com/snooze64/redmine-anon-helpdesk.git
cd redmine-anon-helpdesk

# 2. 環境変数のテンプレートをコピー (中身は何も変更しなくても動く)
cp .env.example .env

# 3. ビルド & 起動
docker compose build
docker compose up -d

# 4. ブラウザで開く
#    http://localhost:3080
#    初回ログイン: admin / admin → 強制パスワード変更
```

ここまでで **空の Redmine** が動きます。続いて初期データ投入とロール設定が必要です:

```bash
# 5. 既定構成データ (Manager/Developer/Reporter ロール、Bug/Feature/Support トラッカー等) を投入
docker compose exec -T -e REDMINE_LANG=ja redmine bundle exec rake redmine:load_default_data
```

### 6. ロール・ユーザー・プロジェクト作成

ここから先は管理 UI で操作します。**[docs/manual_setup.md](docs/manual_setup.md)** に画面遷移付きの手順書があります（ロール `質問者` / `回答者` 作成、`Show user profile` 権限の制御、メール通知設定、サンプルチケット投入まで）。

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
| [docs/manual_setup.md](docs/manual_setup.md) | Web UI のみで完結する全セットアップ手順（ロール、ユーザー、プロジェクト、SMTP、サンプルチケット、動作確認） |
| [docs/plugin_install.md](docs/plugin_install.md) | redmine_hidden_user_profile プラグイン単体のインストール手順（既存の Redmine への後付け、オフライン環境向けパターンも含む） |

## 動作確認済み環境

- Redmine **6.1.x**
- MySQL **8.0**
- Docker Compose **v2.20+**（`depends_on.required: false` を使用）
- Ruby **3.4** / Rails **7.2**（Redmine 6 のベースイメージ依存）

## 依存プラグイン

| プラグイン | 用途 | リポジトリ |
|---|---|---|
| `redmine_hidden_user_profile` | プロフィール画面・ユーザーリンクの権限ベース非表示化 | https://github.com/JGallot/redmine_hidden_user_profile |

> 上記プラグインは LICENSE ファイルが提供されていません。本リポジトリは Dockerfile 内で `git clone` するのみで再配布はしていませんが、フォーク・ベンダリングして利用する場合は元プラグインのライセンス状況をご確認ください。

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
