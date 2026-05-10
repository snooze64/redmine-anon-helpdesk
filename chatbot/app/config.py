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
    redmine_url: str = "http://redmine:3000"
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

    # ----- Ollama (LLM + embedding) -----
    ollama_url: str = "http://ollama:11434"
    ollama_llm_model: str = "qwen2.5:7b"
    ollama_embed_model: str = "nomic-embed-text"

    # ----- RAG パラメータ -----
    retrieval_top_k: int = 5
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024

    # ----- エスカレーション先 (api/ サービス) -----
    bridge_api_url: str = "http://api:8000"

    # ----- スケジューラ -----
    crawl_interval_minutes: int = 0  # 0 = disabled (manual trigger only)


settings = Settings()
