"""LLM 呼出 (Ollama / OpenAI を抽象化)。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import httpx

from app.config import settings


Provider = Literal["ollama", "openai"]


class LLMError(RuntimeError):
    pass


@dataclass
class LLMConfig:
    """1 リクエスト or 1 セッションの LLM 設定。

    provider:
      - "ollama": ローカル/コンテナ内 Ollama を使う (api_key 不要)
      - "openai": OpenAI API を使う (api_key 必須)。base_url を指定すれば
                  OpenAI 互換 API (Azure OpenAI / 社内 LLM ゲートウェイ /
                  LiteLLM / vLLM 等) も使える。
    model:
      未指定なら provider 既定モデルにフォールバック
    api_key:
      openai の場合のみ必須。未指定なら settings.openai_api_key にフォールバック
    base_url:
      openai 互換 API を使う場合に指定。未指定 (None or 空文字) なら
      settings.openai_base_url_default にフォールバック → それも空なら
      公式 OpenAI (https://api.openai.com/v1) を使う。
    """
    provider: Provider = "ollama"
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

    def resolve_model(self) -> str:
        if self.model:
            return self.model
        if self.provider == "ollama":
            return settings.ollama_llm_model
        return settings.openai_llm_model_default

    def resolve_temperature(self) -> float:
        return self.temperature if self.temperature is not None else settings.llm_temperature

    def resolve_max_tokens(self) -> int:
        return self.max_tokens if self.max_tokens is not None else settings.llm_max_tokens

    def resolve_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        return settings.openai_api_key

    def resolve_base_url(self) -> Optional[str]:
        """OpenAI 互換 API の base URL。空文字や None なら None を返す
        (公式 OpenAI = SDK 既定エンドポイント)。"""
        url = (self.base_url or settings.openai_base_url_default or "").strip()
        return url or None


# ---- Provider 別実装 ------------------------------------------------------

def _chat_ollama(messages: list[dict], cfg: LLMConfig, timeout: float) -> str:
    url = f"{settings.ollama_url.rstrip('/')}/api/chat"
    payload = {
        "model": cfg.resolve_model(),
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": cfg.resolve_temperature(),
            "num_predict": cfg.resolve_max_tokens(),
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


def _chat_openai(messages: list[dict], cfg: LLMConfig, timeout: float) -> str:
    api_key = cfg.resolve_api_key()
    if not api_key:
        raise LLMError(
            "OpenAI を使うには API キーが必要です。"
            "セッション作成時に llm_api_key を指定するか、環境変数 OPENAI_API_KEY を設定してください。"
        )

    # 遅延 import (openai SDK が未インストールでも ollama path は使えるように)
    try:
        from openai import OpenAI
    except ImportError as e:
        raise LLMError("openai SDK 未インストール。requirements.txt を確認してください。") from e

    base_url = cfg.resolve_base_url()
    client_kwargs: dict = {"api_key": api_key, "timeout": timeout}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)
    model = cfg.resolve_model()

    # o1 / o3 系は temperature 非対応・max_completion_tokens のみ
    is_reasoning_model = model.startswith(("o1", "o3"))

    try:
        if is_reasoning_model:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=cfg.resolve_max_tokens(),
            )
        else:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=cfg.resolve_temperature(),
                max_tokens=cfg.resolve_max_tokens(),
            )
    except Exception as e:
        # OpenAI SDK の AuthenticationError / RateLimitError などをまとめてラップ
        raise LLMError(f"OpenAI chat 呼出失敗: {type(e).__name__}: {e}") from e

    choices = getattr(resp, "choices", None) or []
    if not choices:
        raise LLMError(f"OpenAI レスポンスに choices が無い: {resp}")
    content = getattr(choices[0].message, "content", None)
    if not isinstance(content, str):
        raise LLMError(f"OpenAI レスポンス content が不正: {choices[0]}")
    return content


# ---- 公開関数 -------------------------------------------------------------

def chat(messages: list[dict], cfg: Optional[LLMConfig] = None,
         timeout: float = 120.0) -> str:
    """LLM に問い合わせて assistant メッセージ文字列を返す。

    cfg を渡さなければ settings の既定 (provider=settings.llm_provider_default)
    に従う。
    """
    if cfg is None:
        cfg = LLMConfig(provider=settings.llm_provider_default)  # type: ignore[arg-type]

    if cfg.provider == "ollama":
        return _chat_ollama(messages, cfg, timeout)
    if cfg.provider == "openai":
        return _chat_openai(messages, cfg, timeout)
    raise LLMError(f"未対応の LLM provider: {cfg.provider}")
