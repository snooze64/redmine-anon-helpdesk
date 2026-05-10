"""user_service / ticket_service から再利用する Redmine 検索ヘルパ。"""
from __future__ import annotations

from typing import Optional

from redminelib import Redmine
from redminelib.exceptions import ResourceNotFoundError


def find_user_by_login(rm: Redmine, login: str):
    """login が完全一致するユーザーを返す。無ければ None。

    rm.user.filter(name=login) は login / firstname / lastname / display_name の
    部分マッチなので、結果から完全一致だけを抽出する。
    """
    try:
        for u in rm.user.filter(name=login):
            if u.login == login:
                return u
    except ResourceNotFoundError:
        return None
    return None


def resolve_role_id(rm: Redmine, role_name: str) -> int:
    for r in rm.role.all():
        if r.name == role_name:
            return r.id
    raise RuntimeError(f"Redmine にロール '{role_name}' が存在しません。先に作成してください。")


def resolve_project(rm: Redmine, identifier: str):
    try:
        return rm.project.get(identifier)
    except ResourceNotFoundError as e:
        raise RuntimeError(
            f"Redmine にプロジェクト '{identifier}' が存在しません。"
            f"先に作成して identifier を一致させてください。"
        ) from e


def find_membership(rm: Redmine, project, user_id: int):
    """指定ユーザーのプロジェクトメンバーシップを返す。無ければ None。"""
    for m in rm.project_membership.filter(project_id=project.id):
        if hasattr(m, "user") and m.user.id == user_id:
            return m
    return None


def ensure_membership(
    rm: Redmine, project, user_id: int, role_id: int
) -> str:
    """ユーザーをプロジェクトに指定ロールで参加させる (idempotent)。

    Returns:
        "created"        : membership を新規作成 (元々非メンバー)
        "role_added"     : 既存 membership に役割を追加 (元々メンバーだがそのロール無し)
        "already_member" : 既にそのロールで参加済 (何もしなかった)
    """
    existing = find_membership(rm, project, user_id)
    if existing is None:
        rm.project_membership.create(
            project_id=project.id,
            user_id=user_id,
            role_ids=[role_id],
        )
        return "created"

    current_role_ids = {r.id for r in existing.roles}
    if role_id in current_role_ids:
        return "already_member"

    new_role_ids = sorted(current_role_ids | {role_id})
    existing.role_ids = new_role_ids
    existing.save()
    return "role_added"


def find_users_with_role_on_project(rm: Redmine, project, role_name: str) -> list[int]:
    """指定ロールをプロジェクトに持つユーザーの user_id 一覧を返す。

    グループメンバーシップ (m.group) はスキップし、個人メンバーシップ (m.user) のみ対象。
    role_name に対応するロールが存在しない場合は RuntimeError (resolve_role_id 経由)。
    """
    role_id = resolve_role_id(rm, role_name)
    user_ids: list[int] = []
    for m in rm.project_membership.filter(project_id=project.id):
        # グループメンバーシップは m.user 属性を持たない (m.group のみ)
        if not hasattr(m, "user"):
            continue
        if any(r.id == role_id for r in m.roles):
            user_ids.append(m.user.id)
    return user_ids


def resolve_tracker(rm: Redmine, project, name: Optional[str] = None):
    """プロジェクトで利用可能なトラッカーを返す。

    name 指定: 完全一致するトラッカーを返す (見つからなければ RuntimeError)。
    name 未指定: プロジェクトの最初のトラッカーを返す。
    """
    try:
        trackers = list(project.trackers)
    except Exception as e:
        raise RuntimeError(
            f"プロジェクト '{project.identifier}' の有効トラッカーを取得できません: {e}"
        ) from e

    if not trackers:
        raise RuntimeError(
            f"プロジェクト '{project.identifier}' に有効なトラッカーが 1 件もありません。"
            f" プロジェクト設定で少なくとも 1 つトラッカーを有効にしてください。"
        )

    if name:
        for t in trackers:
            if t.name == name:
                return t
        available = ", ".join(t.name for t in trackers)
        raise RuntimeError(
            f"プロジェクト '{project.identifier}' にトラッカー '{name}' が無効/未存在です。"
            f" 利用可能: [{available}]"
        )

    return trackers[0]
