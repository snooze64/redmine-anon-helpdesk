from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """環境変数から読み込む設定。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- Redmine 接続 -----
    # 内部 (Python -> Redmine REST) 接続先。docker compose 内では http://redmine:3000
    redmine_url: str = "http://redmine:3000"
    # 外部 (ブラウザ等から Redmine へアクセスするときの公開 URL)。
    # citation のリンクや、メール本文中の Issue URL 生成に使う。
    # 既定はローカル開発を想定: http://localhost:3080
    redmine_public_url: str = "http://localhost:3080"
    redmine_api_key: str = ""
    redmine_admin_username: str = ""
    redmine_admin_password: str = ""

    # ----- 取込対象 -----
    crawl_project_identifier: str = "demo"
    # 全状態を含めるため status_id=* を使う
    crawl_include_journals: bool = True
    crawl_page_size: int = 100

    # ----- ベクトル DB (Chroma 永続化先) -----
    chroma_persist_dir: str = "/data/chroma"
    chroma_collection: str = "redmine_tickets"

    # ----- LLM プロバイダ既定 -----
    # 'ollama' | 'openai'。セッション作成時に上書き可能。
    llm_provider_default: str = "ollama"

    # ----- Ollama (LLM + embedding) -----
    ollama_url: str = "http://ollama:11434"
    ollama_llm_model: str = "qwen2.5:7b"
    ollama_embed_model: str = "nomic-embed-text"
    # WebUI のモデル選択ドロップダウンで提案するデフォルトモデル候補。
    # ollama list の実存にかかわらず提案する想定値。
    ollama_llm_suggestions: str = "qwen2.5:7b,qwen2.5:3b,qwen2.5:0.5b,llama3.1:8b,gemma2:9b"

    # ----- OpenAI (LLM のみ。埋め込みは Ollama のまま固定) -----
    openai_api_key: str = ""  # 環境変数のフォールバック。セッション側で上書き可
    openai_llm_model_default: str = "gpt-4o-mini"
    openai_llm_suggestions: str = "gpt-4o-mini,gpt-4o,gpt-4.1-mini,gpt-4.1,gpt-3.5-turbo,o1-mini,o1"

    # ----- RAG パラメータ -----
    retrieval_top_k: int = 5
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024

    # ----- エスカレーション先 (api/ サービス) -----
    bridge_api_url: str = "http://api:8000"

    # ----- スケジューラ -----
    crawl_interval_minutes: int = 0  # 0 = disabled (manual trigger only)


settings = Settings()
