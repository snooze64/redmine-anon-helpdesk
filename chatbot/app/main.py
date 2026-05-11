import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.routers import crawl, health, models, search, sessions
from app.scheduler import start as start_scheduler, stop as stop_scheduler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title="Redmine Anon Helpdesk Chatbot API",
    description=(
        "Redmine チケットを RAG ソースにしたチャットボットのバックエンド。\n\n"
        "- `POST /crawl` で Redmine から取込 → Chroma に embedding 投入\n"
        "- `GET  /search?q=...` でベクトル類似検索\n"
        "- `POST /sessions` でチャットセッション開始\n"
        "- `POST /sessions/{id}/messages` で発話 → RAG 回答\n"
        "- `POST /sessions/{id}/{close|continue|escalate}` で HITL アクション\n"
        "- escalate は既存 api/ サービス (`POST /tickets`) を内部 HTTP で呼んで Redmine 起票"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(crawl.router)
app.include_router(search.router)
app.include_router(sessions.router)
app.include_router(models.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "redmine-anon-helpdesk-chatbot",
        "version": "0.1.0",
        "redmine_url": settings.redmine_url,
        "ollama_url": settings.ollama_url,
        "llm_model": settings.ollama_llm_model,
        "embed_model": settings.ollama_embed_model,
        "chroma_collection": settings.chroma_collection,
        "docs_url": "/docs",
    }
