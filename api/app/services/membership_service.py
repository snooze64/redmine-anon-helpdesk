"""プロジェクトメンバーシップ割当 (idempotent)。

責務:
  - 設定中プロジェクトに対象ユーザーを指定ロールで参加させる
  - ユーザー自体の作成には関与しない (それは user_service の責務)
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.config import settings
from app.redmine_client import get_redmine
from app.services.redmine_helpers import (
    ensure_membership,
    find_membership,
    find_user_by_login,
    resolve_project,
    resolve_role_id,
)


# ---- 入出力モデル ---------------------------------------------------------

class AssignMembershipRequest(BaseModel):
    login: str = Field(
        ..., min_length=1, max_length=60,
        description="Redmine 上に既に存在するユーザーのログインID",
    )


class AssignMembershipResponse(BaseModel):
    status: Literal["created", "role_added", "already_member"]
    user_id: int
    login: str
    project_identifier: str
    role_name: str
    all_roles: list[str]


# ---- ユーザー向け例外 -----------------------------------------------------

class UserNotFound(LookupError):
    """指定ログインIDのユーザーが Redmine に未登録 (POST /users 未実行)。"""


# ---- メイン処理 -----------------------------------------------------------

def assign_membership(req: AssignMembershipRequest) -> AssignMembershipResponse:
    """対象ユーザーを既定プロジェクトに既定ロールで参加させる (idempotent)。

    Returns:
        status:
          'created'        -> 新規 membership 作成
          'role_added'     -> 既存 membership に対象ロールを追加
          'already_member' -> 何もしなかった (既に対象ロール付与済)

    Raises:
        UserNotFound: login が Redmine に存在しないとき (先に POST /users が必要)
        RuntimeError: プロジェクト or ロール設定の不備
    """
    rm = get_redmine()

    user = find_user_by_login(rm, req.login)
    if user is None:
        raise UserNotFound(
            f"ログインID '{req.login}' のユーザーが Redmine に存在しません。"
            f" 先に POST /users で作成してください。"
        )

    project = resolve_project(rm, settings.questioner_project_identifier)
    role_id = resolve_role_id(rm, settings.questioner_role_name)

    outcome = ensure_membership(rm, project, user.id, role_id)

    # 結果として持っているロール一覧 (確認用)
    membership = find_membership(rm, project, user.id)
    all_roles = sorted(r.name for r in membership.roles) if membership else []

    return AssignMembershipResponse(
        status=outcome,
        user_id=user.id,
        login=user.login,
        project_identifier=settings.questioner_project_identifier,
        role_name=settings.questioner_role_name,
        all_roles=all_roles,
    )
