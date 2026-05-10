from fastapi import FastAPI

from app.config import settings
from app.routers import health, memberships, tickets, users

app = FastAPI(
    title="Redmine Anon Helpdesk API",
    description=(
        "FastAPI bridge between chatbot and Redmine.\n\n"
        "python-redmine 経由で Redmine REST API を呼び出すサーバー。"
        "具体的なエンドポイントは要件確定後に追加していく。"
    ),
    version="0.1.0",
)

# ルーター登録
app.include_router(health.router)
app.include_router(users.router)
app.include_router(memberships.router)
app.include_router(tickets.router)


@app.get("/", tags=["meta"])
def root() -> dict:
    """サービスメタ情報。"""
    return {
        "service": "redmine-anon-helpdesk-api",
        "version": "0.1.0",
        "redmine_url": settings.redmine_url,
        "docs_url": "/docs",
    }
