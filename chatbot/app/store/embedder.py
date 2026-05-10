"""Ollama 経由で text を埋め込みベクトルに変換する。

Ollama の embedding API: POST /api/embed
  Request:  {"model": "nomic-embed-text", "input": ["text1", "text2", ...]}
  Response: {"embeddings": [[...], [...]], ...}
"""
from __future__ import annotations

from typing import Iterable

import httpx

from app.config import settings


class EmbeddingError(RuntimeError):
    pass


def embed_texts(texts: list[str], timeout: float = 60.0) -> list[list[float]]:
    """テキスト群を Ollama 埋め込みモデルでベクトル化する。

    1 リクエストにまとめて投げる (Ollama の /api/embed が batch 対応)。
    """
    if not texts:
        return []

    url = f"{settings.ollama_url.rstrip('/')}/api/embed"
    payload = {"model": settings.ollama_embed_model, "input": texts}

    try:
        with httpx.Client(timeout=timeout) as cli:
            r = cli.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        raise EmbeddingError(f"Ollama 埋め込み API 呼び出し失敗: {e}") from e

    embs = data.get("embeddings")
    if not embs or len(embs) != len(texts):
        raise EmbeddingError(f"Ollama レスポンスが不正: {data}")
    return embs


def embed_one(text: str, timeout: float = 60.0) -> list[float]:
    """単一テキスト用ヘルパ。"""
    embs = embed_texts([text], timeout=timeout)
    return embs[0]
