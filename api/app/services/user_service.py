"""Redmine 全体へのユーザー登録 (idempotent)。

責務:
  - login 単位で Redmine にユーザーが存在することを保証する
  - 既に存在すれば既存情報を返し、メールやパスワード等は一切上書きしない
  - プロジェクトメンバーシップ等の Redmine リソースには関与しない
    (それは membership_service の責務)
"""
from __future__ import annotations

import secrets
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.redmine_client import get_redmine
from app.services.redmine_helpers import find_user_by_login


# ---- 入出力モデル ---------------------------------------------------------

class CreateUserRequest(BaseModel):
    login: str = Field(..., min_length=1, max_length=60, description="Redmine ログインID")
    email: EmailStr = Field(..., description="メールアドレス")
    password: str = Field(..., min_length=8, description="初期パスワード (8 文字以上推奨)")


class CreateUserResponse(BaseModel):
    status: Literal["created", "already_exists"]
    user_id: int
    login: str
    firstname: str
    lastname: str
    mail: Optional[str] = None


# ---- ヘルパ ---------------------------------------------------------------

def _generate_random_name() -> tuple[str, str]:
    """匿名表示用の擬似ランダム名 (firstname='User', lastname='3F8A2C1B')。"""
    return ("User", secrets.token_hex(4).upper())


# ---- メイン処理 -----------------------------------------------------------

def create_or_get_user(req: CreateUserRequest) -> CreateUserResponse:
    """idempotent なユーザー登録。

    1. login で既存検索。あれば既存情報を返す (status='already_exists')
    2. 無ければ作成する (status='created')
       - 氏名はランダム生成 (匿名性)
       - 言語は環境変数 (既定 'ja')
       - 強制パスワード変更なし
    3. 既存ユーザーには **絶対に何も書き換えない** (mail/password 上書き不可)
    """
    rm = get_redmine()

    existing = find_user_by_login(rm, req.login)
    if existing is not None:
        return CreateUserResponse(
            status="already_exists",
            user_id=existing.id,
            login=existing.login,
            firstname=getattr(existing, "firstname", "") or "",
            lastname=getattr(existing, "lastname", "") or "",
            mail=getattr(existing, "mail", None),
        )

    firstname, lastname = _generate_random_name()
    new_user = rm.user.create(
        login=req.login,
        firstname=firstname,
        lastname=lastname,
        mail=str(req.email),
        password=req.password,
        language=settings.questioner_language,
        must_change_passwd=False,
        mail_notification="only_my_events",
    )

    return CreateUserResponse(
        status="created",
        user_id=new_user.id,
        login=new_user.login,
        firstname=firstname,
        lastname=lastname,
        mail=str(req.email),
    )
