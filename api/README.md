# Chatbot Bridge API (FastAPI + python-redmine)

チャットボットからの問い合わせを Redmine REST API 経由でチケット化するためのブリッジサーバー。`POST /users` でユーザー登録、`POST /memberships` でプロジェクト割当、`POST /tickets` で起票、という 3 段階のオーケストレーションで動作する。

## 構成

```
api/
├── Dockerfile           Python 3.12-slim + FastAPI + python-redmine
├── requirements.txt     依存パッケージ
├── .dockerignore
└── app/
    ├── main.py          FastAPI エントリ
    ├── config.py        環境変数 (REDMINE_URL / REDMINE_API_KEY 等)
    ├── redmine_client.py python-redmine クライアント生成
    └── routers/
        └── health.py    /health, /health/redmine
```

統合用 compose スニペット: プロジェクト直下の `compose.api.yml`。メインの `docker-compose.yml` を上書き拡張する形で読み込まれる。

## 起動方法 (メイン Redmine と一緒に立てる)

```powershell
# プロジェクトルートで実行
docker compose -f docker-compose.yml -f compose.api.yml up -d
```

## 前提: Redmine 側で REST API を有効化

Redmine の REST API はデフォルト無効。先に有効化が必要:

**Web UI 経由**: 管理 → 設定 → API → 「REST による Web サービス」をチェック → 保存

**CLI 経由 (1 回だけ)**:
```powershell
docker compose exec -T redmine bundle exec rails runner "Setting.rest_api_enabled = '1'"
```

これを忘れると python-redmine が **403 ForbiddenError: Requested resource is forbidden** を返す。

## 接続情報の設定

`.env` に以下のいずれかを追加:

```ini
# 推奨: Redmine の管理画面でユーザーを作って "API access key" を発行する
REDMINE_API_KEY=<取得した 40 桁の API key>

# フォールバック: Basic 認証 (ユーザー名 + パスワード)
# REDMINE_ADMIN_USERNAME=<管理者ユーザー名>
# REDMINE_ADMIN_PASSWORD=<管理者パスワード>
```

API key の取得方法:
1. Redmine に admin でログイン → 個人設定 (My account)
2. 右側「API アクセスキー」セクション → 「表示」または「リセット」
3. 表示された 40 桁の文字列を `.env` に貼る

## 動作確認

```powershell
# 単純な liveness
curl http://localhost:8000/health

# Redmine 連携の疎通 + 認証確認
curl http://localhost:8000/health/redmine

# サービス情報
curl http://localhost:8000/

# OpenAPI ドキュメント (ブラウザで)
# http://localhost:8000/docs
```

## エンドポイント (現状)

| Method | Path | 内容 |
|---|---|---|
| GET  | `/` | サービス名・バージョン・redmine_url を返す |
| GET  | `/health` | liveness（外部呼び出しなし） |
| GET  | `/health/redmine` | python-redmine 経由で `users/current.json` を呼んで認証ユーザー情報を返す |
| **POST** | **`/users`** | **Redmine にユーザーを作成（idempotent / プロジェクト割り当ては別エンドポイント）** |
| **POST** | **`/memberships`** | **既定プロジェクトに対象ユーザーを既定ロールで参加（idempotent）** |
| **POST** | **`/tickets`** | **チャットボットから問い合わせチケットを起票（質問者+回答者ロール全員を watcher 登録）** |
| GET  | `/docs` | Swagger UI |
| GET  | `/redoc` | ReDoc |

### POST /users

#### リクエスト

```json
{
  "login": "questioner_taro",
  "email": "taro@example.com",
  "password": "StrongPass123"
}
```

| フィールド | 制約 |
|---|---|
| `login` | 1〜60 文字。Redmine のログインIDになる |
| `email` | RFC 準拠のメールアドレス (pydantic で検証) |
| `password` | 8 文字以上推奨 (Redmine 側のパスワードポリシーにも従う) |

#### レスポンス

```json
{
  "status": "created",
  "user_id": 10,
  "login": "questioner_taro",
  "firstname": "User",
  "lastname": "75E8BC65",
  "mail": "taro@example.com"
}
```

#### `status`

| status | 状況 |
|---|---|
| `created` | login が未登録だったので新規作成した |
| `already_exists` | login が既存だったので何もせず情報を返した |

#### 責務分離

このエンドポイントは **Redmine 全体へのユーザー登録のみ** を担当します。プロジェクトメンバーシップ/ロール付与は `POST /memberships` に分離されています。チャットボットのオーケストレーション例:

```
POST /users        → 既存・新規どちらでも 200
POST /memberships  → プロジェクトに対象ロールで参加させる (idempotent)
POST /tickets      → チケット作成
```

#### 既存ユーザーへの非干渉

- メールアドレス・パスワード・氏名は **絶対に上書きしない**

### POST /memberships

設定中プロジェクトに対象ユーザーを設定中ロールで参加させる。`POST /users` で先にユーザー作成しておくこと。

#### リクエスト

```json
{ "login": "questioner_taro" }
```

#### レスポンス

```json
{
  "status": "created",
  "user_id": 10,
  "login": "questioner_taro",
  "project_identifier": "demo",
  "role_name": "質問者",
  "all_roles": ["質問者"]
}
```

#### `status` の意味

| status | 状況 |
|---|---|
| `created` | プロジェクトに未参加 → 新規 membership 作成 |
| `role_added` | 別ロールで参加済 → 対象ロールを **追加** (元のロールは保持) |
| `already_member` | 対象ロールで既に参加済 → 何もしなかった (no-op) |

`all_roles` フィールドで現在保持している全ロールが確認できる。

#### エラー

| HTTP | 状況 |
|---|---|
| 404 | login が未登録 → 先に `POST /users` を呼ぶ |
| 500 | プロジェクト or ロール設定の不備 |

#### 想定ユースケース

| シナリオ | 呼び出し |
|---|---|
| プロジェクト A の API に新しい質問者が来た | `POST /users` → `created` → `POST /memberships` → `created` |
| 同じ人がプロジェクト A の API を再利用 | `POST /users` → `already_exists` → `POST /memberships` → `already_member` |
| 同じ人がプロジェクト B の API を初利用 | `POST /users` → `already_exists` → `POST /memberships` (B 用 API) → `created` |
| プロジェクト C で既に Reporter ロールを持つ人を質問者に **昇格** | `POST /memberships` (C 用 API) → `role_added` (Reporter は保持) |

#### エラー

| HTTP | 状況 |
|---|---|
| 422 | リクエストボディのバリデーション失敗 (email 形式不正・login 空など) |
| 500 | 既定プロジェクト or ロールが Redmine に存在しない |
| 502 | Redmine API 呼び出しが失敗 (権限不足・パスワード弱すぎ等) |
| 503 | API 自体に Redmine 認証情報が未設定 |

### POST /tickets

チャットボットから問い合わせチケットを起票する。

#### リクエスト

```json
{
  "title": "ログインができない",
  "description": "今朝からログインできなくなった。\nパスワード忘れの可能性。",
  "watcher_login": "questioner_alpha",
  "is_private": false
}
```

| フィールド | 制約 |
|---|---|
| `title` | 1〜255 文字 (Redmine の Issue#subject に対応) |
| `description` | 任意。空文字可 |
| `watcher_login` | Redmine に既に存在しているユーザーのログインID。`POST /users` で先に作成しておく |
| `is_private` | true ならプライベートチケット。既定値 false |

#### レスポンス (成功)

```json
{
  "issue_id": 10,
  "project_identifier": "demo",
  "tracker_name": "Bug",
  "subject": "ログインができない",
  "is_private": false,
  "watchers": [
    {"user_id": 7, "login": "responder"},
    {"user_id": 9, "login": "questioner_alpha"}
  ]
}
```

#### 動作

- **起票プロジェクト**: `INQUIRY_PROJECT_IDENTIFIER` (空なら `QUESTIONER_PROJECT_IDENTIFIER` と同じ → 既定 `demo`)
- **トラッカー**: `INQUIRY_TRACKER_NAME` (空ならプロジェクトの先頭トラッカー)
- **ウォッチャー**:
  - 指定された `watcher_login` のユーザー (= 質問者) を登録
  - **`RESPONDER_ROLE_NAME` (既定 `回答者`) ロールをプロジェクトに持つ全メンバー** も自動で登録
  - API 呼出ユーザー (admin など) は Redmine の auto-watch 機能で一旦追加されるが、**上記 2 種類以外なら事後に削除される**
- **作者**: API 呼出に使用した認証ユーザー (= admin or REDMINE_API_KEY 所有者)

#### エラー

| HTTP | 状況 |
|---|---|
| 404 | `watcher_login` のユーザーが Redmine に未登録 |
| 422 | リクエストボディのバリデーション失敗 (title 空、長すぎ等) |
| 500 | プロジェクト or トラッカーが Redmine に存在しない |
| 502 | Redmine API 呼出失敗 (権限・設定) |
| 503 | API 自体に Redmine 認証情報が未設定 |

### 今後の予定 (要件確定次第)

- `POST /tickets/{id}/notes` — コメント追加
- `GET  /tickets/{id}/journals` — コメント取得 (ボットが回答内容を読む)
- `GET  /tickets?status_id=closed` — クローズ済チケット一覧 (RAG 取込用)
- 認証 (チャットボットからの API 呼び出しに API トークンを要求)

## 今後の検討事項

- [ ] チャットボット側からの認証方式 (API トークン / OAuth / 共有シークレット)
- [ ] エンドポイント一覧の確定
- [ ] ロギング (構造化 JSON ログ)
- [ ] エラーフォーマットの統一
- [ ] テスト (pytest + httpx)
- [ ] CI（GitHub Actions）
- [ ] Git に上げるタイミングで本リポジトリの `docker-compose.yml` 本体への統合を検討
