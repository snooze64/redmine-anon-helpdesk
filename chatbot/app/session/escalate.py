"""エスカレーション: 既存の api/ サービスを HTTP で叩いて Redmine 起票。

呼び出すエンドポイント:
  POST {bridge_api_url}/users         (idempotent)
  POST {bridge_api_url}/memberships   (idempotent)
  POST {bridge_api_url}/tickets       (起票 + watcher 自動登録)
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

import httpx

from app.config import settings


class EscalationError(RuntimeError):
    pass


def _login_from_email(email: str) -> str:
    """email から安定的なログイン ID を作る。

    同じ email を出した人は **常に同じ login** にマップされるので、Redmine 側で
    新しい匿名アカウントが量産されるのを防げる (idempotent な作成エンドポイントは
    login 単位で重複検知するため)。

    形式: "chat_<sha256(email_lc)[:10]>" (合計 15 文字、Redmine の 60 文字制限内)
    """
    h = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    return f"chat_{h[:10]}"


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


def _create_ticket(
    title: str, description: str, watcher_login: str, is_private: bool,
    chatbot_session_id: str | None = None,
) -> dict:
    url = f"{settings.bridge_api_url.rstrip('/')}/tickets"
    payload: dict = {
        "title": title[:255],
        "description": description,
        "watcher_login": watcher_login,
        "is_private": is_private,
    }
    if chatbot_session_id:
        payload["chatbot_session_id"] = chatbot_session_id
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
    chatbot_session_id: str | None = None,
) -> EscalationResult:
    """ユーザー登録 → メンバー登録 → 起票、を順に実行する。

    user_email は **必須**。同じ email を出した人は常に同じ Redmine アカウントに
    マップされる (sha256(email) から派生した login を使う) ため、同じ人が
    複数回エスカレーションしてもアカウントは増えない。

    user_login は任意。指定された場合はそれを使い、未指定なら email から派生する。
    """
    if not user_email or not user_email.strip():
        raise EscalationError(
            "user_email は必須です。同じ人による複数回のエスカレーションで "
            "Redmine 匿名アカウントが量産されないようにするため、email で名寄せします。"
        )
    user_email = user_email.strip()

    if not user_login:
        # email から派生した安定 login (idempotent な name-dedupe を効かせる)
        user_login = _login_from_email(user_email)

    generated_password: str | None = None

    try:
        # ユーザーが API 側で新規作成される場合に備えて password を発行
        generated_password = secrets.token_urlsafe(16)
        user_res = _ensure_user(user_login, user_email, generated_password)
        if user_res.get("status") == "already_exists":
            generated_password = None  # 既存ユーザーのパスワードは触らない

        _ensure_membership(user_login)
        ticket_res = _create_ticket(
            title, description, user_login, is_private,
            chatbot_session_id=chatbot_session_id,
        )

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
