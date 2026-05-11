# Chatbot (RAG + HITL)

Redmine の過去チケットをベクトル化し、Ollama で動かす LLM が回答するチャットボット。AI 回答に満足できない場合は **既存の `api/` サービス経由で Redmine にチケット起票** してエスカレーションできる Human-in-the-Loop 設計。

## アーキテクチャ

```
[User] ──HTTP──> [Streamlit UI :8501]
                       │
                       │ HTTP
                       ▼
              [chatbot backend :8100] ──┬─ Ollama :11434  (LLM + embedding)
                       │                ├─ ChromaDB (永続ボリューム)
                       │                └─ Redmine REST   (RAG ソース取込)
                       │
                       │ Escalate
                       ▼
                [api :8000] ──> Redmine (チケット起票)
```

## 構成

```
chatbot/
├── Dockerfile                  Python 3.12-slim ベースの FastAPI バックエンド
├── requirements.txt            FastAPI / chromadb / ollama / python-redmine 等
├── .dockerignore
├── README.md                   このファイル
├── app/
│   ├── main.py                 FastAPI エントリ (lifespan で scheduler 起動)
│   ├── config.py               環境変数 (pydantic-settings)
│   ├── redmine_client.py       python-redmine ラッパ
│   ├── scheduler.py            APScheduler (定期 crawl)
│   ├── crawler/
│   │   └── redmine_crawler.py  チケット取得 + 1 チケット 1 チャンク化
│   ├── store/
│   │   ├── embedder.py         Ollama /api/embed 呼出
│   │   ├── vectorstore.py      Chroma 永続化ラッパ
│   │   └── pipeline.py         crawl → 差分判定 → embed → upsert
│   ├── chain/
│   │   ├── llm.py              Ollama /api/chat 呼出
│   │   └── rag.py              リトリーブ → コンテキスト整形 → LLM
│   ├── session/
│   │   ├── store.py            in-memory チャットセッション
│   │   └── escalate.py         api/ サービスを HTTP で叩く
│   └── routers/
│       ├── health.py           /health, /health/redmine, /health/ollama, /health/store
│       ├── crawl.py            POST /crawl
│       ├── search.py           GET /search?q=
│       └── sessions.py         /sessions, /sessions/{id}/{messages,close,continue,escalate}
└── frontend/
    ├── Dockerfile
    ├── requirements.txt
    └── app.py                  Streamlit ベースの簡易 UI
```

## 起動方法

メイン compose に `compose.api.yml` と `compose.chatbot.yml` を重ねる:

```bash
docker compose \
  -f docker-compose.yml \
  -f compose.api.yml \
  -f compose.chatbot.yml \
  build
docker compose \
  -f docker-compose.yml \
  -f compose.api.yml \
  -f compose.chatbot.yml \
  up -d
```

立ち上がる service:

| service | 役割 | 公開ポート |
|---|---|---|
| redmine | チケット管理 | 3080 |
| db | MySQL | 13306 |
| api | チケット起票ブリッジ FastAPI | 8000 |
| chatbot | RAG バックエンド FastAPI | **8100** |
| chatbot-frontend | Streamlit UI | **8501** |
| ollama | LLM + embedding サーバー | 11435 (任意、ホスト側の別 Ollama と衝突しないようずらした) |

## 初回セットアップ

### 1. Ollama に必要モデルを pull

初回は **モデルダウンロード (数 GB)** が必要。chatbot コンテナを起動した後、ホストから:

```powershell
# LLM (qwen2.5:7b、約 4.7 GB)
docker exec redmine-ollama ollama pull qwen2.5:7b

# 埋め込みモデル (nomic-embed-text、約 270 MB)
docker exec redmine-ollama ollama pull nomic-embed-text
```

完了確認:
```powershell
curl http://localhost:11434/api/tags
# → models 配列に qwen2.5:7b と nomic-embed-text が並ぶ
```

### 2. Redmine REST API を有効化

(これは api/ と同じ前提)

```powershell
docker compose exec -T redmine bundle exec rails runner "Setting.rest_api_enabled = '1'"
```

### 3. `.env` で接続情報設定

```ini
# Redmine 認証
REDMINE_API_KEY=<40 桁の API key>

# 取込対象プロジェクト
CRAWL_PROJECT_IDENTIFIER=demo

# (任意) スケジューラ間隔。0 で無効
CRAWL_INTERVAL_MINUTES=0
```

`.env` を編集後 `docker compose ... up -d` で再作成 (env 反映)。

### 4. 初回 crawl

Streamlit UI のサイドバー「🔄 ベクトル DB を更新 (crawl)」ボタン、または:

```powershell
curl -X POST http://localhost:8100/crawl
# → {"fetched": N, "inserted": N, "updated": 0, "skipped_unchanged": 0}
```

## エンドポイント

### バックエンド (chatbot)

| Method | Path | 内容 |
|---|---|---|
| GET | `/` | サービスメタ |
| GET | `/health` | liveness |
| GET | `/health/redmine` | Redmine 認証疎通 |
| GET | `/health/ollama` | Ollama 疎通 + モデル一覧 |
| GET | `/health/store` | Chroma コレクション状態 (件数) |
| POST | `/crawl` | 手動 crawl (差分更新ロジック実行) |
| GET | `/search?q=...&top_k=5` | ベクトル類似検索 (RAG リトリーバ単体) |
| POST | `/sessions` | 新規セッション開始 |
| GET | `/sessions/{id}` | セッション状態取得 |
| POST | `/sessions/{id}/messages` | 発話 → RAG 回答 |
| POST | `/sessions/{id}/close` | クローズ (満足) |
| POST | `/sessions/{id}/continue` | 継続宣言 (no-op だが UI 状態管理用) |
| POST | `/sessions/{id}/escalate` | 人にエスカレーション (Redmine 起票) |

OpenAPI: http://localhost:8100/docs

### フロントエンド

http://localhost:8501 を開くと Streamlit UI。3 ボタン:
- ✅ **クローズ**: 満足 → セッション終了
- ✏️ **継続**: そのまま下に質問入力で次ターン
- 📨 **エスカレーション**: ポップオーバーで件名 + プライベートフラグを指定 → Redmine 起票

## 動作フロー

### 取込 (crawl)

```
POST /crawl
  ↓
Redmine REST: GET /issues.json?project_id=demo&status_id=*&include=journals
  ↓
1 チケット = 1 チャンク化 (subject + description + 全 journal を 1 テキスト)
  ↓
ChromaDB に既存登録された updated_on と比較
  ↓
新規 or 更新されたチケットのみ Ollama embed → ChromaDB upsert
```

### 質問応答

```
ユーザー発話
  ↓
Ollama embed (nomic-embed-text)
  ↓
ChromaDB 類似検索 (top_k=5)
  ↓
コンテキスト整形 (#N issue 内容を Markdown で並べる)
  ↓
Ollama LLM (qwen2.5:7b) に送信 + 過去履歴 (最新 4 往復まで)
  ↓
回答 + 参照チケット一覧を返す
```

### エスカレーション

```
POST /sessions/{id}/escalate
  ↓
api サービスへ:
  POST /users        (idempotent)  → 質問者 Redmine ユーザー作成 or 既存
  POST /memberships  (idempotent)  → demo プロジェクトに 質問者 ロールで参加
  POST /tickets                    → 件名+本文で起票、watcher に質問者 + 回答者全員
  ↓
セッション status = "escalated"、issue_id を保存
```

## 設定 env 一覧 (主要)

`compose.chatbot.yml` 経由で chatbot コンテナに注入:

| env | 既定 | 内容 |
|---|---|---|
| `CRAWL_PROJECT_IDENTIFIER` | `demo` | RAG ソースとなる Redmine プロジェクト |
| `CRAWL_INCLUDE_JOURNALS` | `true` | コメント (journals) もチャンクに含めるか |
| `OLLAMA_LLM_MODEL` | `qwen2.5:7b` | チャット用 LLM モデル名 (Ollama に存在すること) |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | 埋め込みモデル名 (同上) |
| `RETRIEVAL_TOP_K` | `5` | 1 質問あたり検索する近傍チケット数 |
| `LLM_TEMPERATURE` | `0.2` | LLM 生成温度 |
| `LLM_MAX_TOKENS` | `1024` | LLM 出力トークン上限 |
| `BRIDGE_API_URL` | `http://api:8000` | エスカレーション時に叩く既存 api/ の URL |
| `CRAWL_INTERVAL_MINUTES` | `0` | 0 で無効、>0 で APScheduler が定期 crawl |

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `/health/ollama` が 502 | Ollama コンテナ未起動 | `docker compose ps` で `ollama` を確認 |
| `/health/ollama` で `models: []` | モデル未 pull | `docker exec redmine-ollama ollama pull qwen2.5:7b` 等 |
| `/crawl` が 503 | Redmine 認証情報未設定 | `.env` の REDMINE_API_KEY を確認 |
| `/crawl` が 502 で `Ollama 埋め込み API 呼び出し失敗` | nomic-embed-text 未 pull | 上記の pull 手順 |
| `/sessions/{id}/messages` が遅い | LLM 推論時間。CPU だと数十秒〜分 | GPU 環境を使う or 軽量モデル (`qwen2.5:3b` 等) に変更 |
| `escalate` が 502 で `Bridge API ...` | `api` サービス未起動 or REDMINE_API_KEY 未設定 | `compose.api.yml` も合わせて up -d |

## 今後の拡張候補

- **API トークン認証**: 現在は無認証で誰でも `/sessions` 叩ける。本番では `Depends(verify_token)` を追加
- **永続セッションストア**: 現在は in-memory。Redis 等に移行
- **複数プロジェクト対応**: 現状は env 1 つで 1 プロジェクト。プロジェクト ID をリクエストに含める方向の拡張も可
- **クローズチケットのみ取込オプション**: ノイズ削減のため
- **回答の信頼度しきい値**: distance が高すぎる時は「該当なし」と即答するロジック
- **テスト**: pytest + httpx でユニットテスト
