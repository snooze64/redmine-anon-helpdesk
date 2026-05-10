"""エスカレーション: 既存の api/ サービスを HTTP で叩いて Redmine 起票。

呼び出すエンドポイント:
  POST {bridge_api_url}/users         (idempotent)
  POST {bridge_api_url}/memberships   (idempotent)
  POST {bridge_api_url}/tickets       (起票 + watcher 自動登録)
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

import httpx

from app.config import settings


class EscalationError(RuntimeError):
    pass


@dataclass
class EscalationResult:
    issue_id: int
    project_identifier: str
    user_login: str
    user_password: str | None  # 新規発行時のみ。既存ユーザーの場合 None


def _ensure_user(login: str, email: str, password: str) -> dict:
    url = f"{settings.bridge_api_url.rstrip('/')}/users"
    with httpx.Client(timeout=30.0) as cli:
        r = cli.post(url, json={"login": login, "email": email, "password": password})
        r.raise_for_status()
        return r.json()


def _ensure_membership(login: str) -> dict:
    url = f"{settings.bridge_api_url.rstrip('/')}/memberships"
    with httpx.Client(timeout=30.0) as cli:
        r = cli.post(url, json={"login": login})
        r.raise_for_status()
        return r.json()


def _create_ticket(title: str, description: str, watcher_login: str, is_private: bool) -> dict:
    url = f"{settings.bridge_api_url.rstrip('/')}/tickets"
    payload = {
        "title": title[:255],
        "description": description,
        "watcher_login": watcher_login,
        "is_private": is_private,
    }
    with httpx.Client(timeout=60.0) as cli:
        r = cli.post(url, json=payload)
        r.raise_for_status()
        return r.json()


def escalate(
    user_login: str | None,
    user_email: str | None,
    title: str,
    description: str,
    is_private: bool = False,
) -> EscalationResult:
    """ユーザー登録 → メンバー登録 → 起票、を順に実行する。

    user_login / user_email が未指定なら匿名ハンドルを生成する。
    """
    generated_password: str | None = None
    if not user_login:
        # 匿名ハンドル: chat_<6文字hex>
        user_login = f"chat_{secrets.token_hex(3)}"
    if not user_email:
        # `chatbot.local` のような .local TLD はメール検証で reserved name として
        # 弾かれるため、example.com を使う (RFC 2606 でテスト用に確保されている)
        user_email = f"{user_login}@example.com"

    try:
        # ユーザーが API 側で新規作成される場合に備えて password を発行
        generated_password = secrets.token_urlsafe(16)
        user_res = _ensure_user(user_login, user_email, generated_password)
        if user_res.get("status") == "already_exists":
            generated_password = None  # 既存ユーザーのパスワードは触らない

        _ensure_membership(user_login)
        ticket_res = _create_ticket(title, description, user_login, is_private)

        return EscalationResult(
            issue_id=int(ticket_res["issue_id"]),
            project_identifier=str(ticket_res.get("project_identifier", "")),
            user_login=user_login,
            user_password=generated_password,
        )
    except httpx.HTTPStatusError as e:
        raise EscalationError(
            f"Bridge API {e.request.url} → {e.response.status_code}: {e.response.text[:200]}"
        ) from e
    except httpx.HTTPError as e:
        raise EscalationError(f"Bridge API connection error: {e}") from e
