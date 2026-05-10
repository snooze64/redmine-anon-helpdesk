from fastapi import APIRouter, HTTPException

import httpx

from app.config import settings
from app.redmine_client import RedmineNotConfigured, get_redmine
from app.store.vectorstore import get_store

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def liveness() -> dict:
    return {"status": "ok"}


@router.get("/redmine")
def redmine_check() -> dict:
    try:
        rm = get_redmine()
        u = rm.user.get("current")
        return {"status": "ok", "redmine_user": getattr(u, "login", None)}
    except RedmineNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Redmine: {e}") from e


@router.get("/ollama")
def ollama_check() -> dict:
    try:
        with httpx.Client(timeout=5.0) as cli:
            r = cli.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
            r.raise_for_status()
            data = r.json()
        models = [m.get("name") for m in data.get("models", [])]
        return {
            "status": "ok",
            "ollama_url": settings.ollama_url,
            "models": models,
            "configured_llm": settings.ollama_llm_model,
            "configured_embed": settings.ollama_embed_model,
        }
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Ollama unreachable: {e}") from e


@router.get("/store")
def store_check() -> dict:
    s = get_store()
    return {
        "status": "ok",
        "collection": settings.chroma_collection,
        "persist_dir": settings.chroma_persist_dir,
        "count": s.count(),
    }
