"""Ollama 経由の LLM 呼出 (chat completion)。"""
from __future__ import annotations

from typing import Iterable

import httpx

from app.config import settings


class LLMError(RuntimeError):
    pass


def chat(messages: list[dict], temperature: float | None = None,
         max_tokens: int | None = None, timeout: float = 120.0) -> str:
    """Ollama /api/chat を呼び出し assistant メッセージを返す。

    messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
    """
    url = f"{settings.ollama_url.rstrip('/')}/api/chat"
    payload = {
        "model": settings.ollama_llm_model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature if temperature is not None else settings.llm_temperature,
            "num_predict": max_tokens if max_tokens is not None else settings.llm_max_tokens,
        },
    }
    try:
        with httpx.Client(timeout=timeout) as cli:
            r = cli.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        raise LLMError(f"Ollama chat 呼出失敗: {e}") from e

    msg = (data.get("message") or {}).get("content")
    if not isinstance(msg, str):
        raise LLMError(f"Ollama レスポンスが不正: {data}")
    return msg
