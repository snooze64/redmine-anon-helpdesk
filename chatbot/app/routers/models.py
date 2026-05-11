"""利用可能な LLM モデルを返す。Streamlit のドロップダウン用。"""
from __future__ import annotations

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/models", tags=["models"])


class ModelsResponse(BaseModel):
    providers: list[str]
    ollama_default: str
    ollama_installed: list[str]      # Ollama サーバーに pull 済みのモデル
    ollama_suggestions: list[str]    # 既定設定にある提案候補
    openai_default: str
    openai_suggestions: list[str]    # OpenAI の典型モデル候補 (静的リスト)
    openai_base_url_default: str     # 環境変数で渡された OpenAI 互換 API の既定 base URL (空可)


def _ollama_installed() -> list[str]:
    try:
        with httpx.Client(timeout=3.0) as cli:
            r = cli.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
            r.raise_for_status()
            data = r.json()
        names: list[str] = []
        for m in data.get("models", []) or []:
            name = m.get("name") or m.get("model")
            if isinstance(name, str):
                names.append(name)
        return names
    except Exception:
        return []


def _csv(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


@router.get("", response_model=ModelsResponse, summary="LLM プロバイダ・モデル候補一覧")
def list_models() -> ModelsResponse:
    return ModelsResponse(
        providers=["ollama", "openai"],
        ollama_default=settings.ollama_llm_model,
        ollama_installed=_ollama_installed(),
        ollama_suggestions=_csv(settings.ollama_llm_suggestions),
        openai_default=settings.openai_llm_model_default,
        openai_suggestions=_csv(settings.openai_llm_suggestions),
        openai_base_url_default=settings.openai_base_url_default,
    )
