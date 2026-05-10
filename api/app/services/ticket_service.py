"""チャットボット起票チケット作成のビジネスロジック。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import settings
from app.redmine_client import get_redmine
from app.services.redmine_helpers import (
    find_user_by_login,
    find_users_with_role_on_project,
    resolve_project,
    resolve_tracker,
)


# ---- 入出力モデル ---------------------------------------------------------

class CreateTicketRequest(BaseModel):
    """チャットボットから受け取る問い合わせ起票リクエスト。"""
    title: str = Field(
        ..., min_length=1, max_length=255,
        description="チケットの件名 (Redmine の Issue#subject、最大 255 文字)",
    )
    description: str = Field(
        default="",
        description="チケットの本文",
    )
    watcher_login: str = Field(
        ..., min_length=1, max_length=60,
        description="ウォッチャーに登録する質問者のログインID。"
                    "Redmine に既に存在しているユーザーであること (POST /users で先に作成済みのもの)。",
    )
    is_private: bool = Field(
        default=False,
        description="True の場合、プライベートチケットとして作成",
    )


class WatcherInfo(BaseModel):
    user_id: int
    login: str


class CreateTicketResponse(BaseModel):
    issue_id: int
    project_identifier: str
    tracker_name: str
    subject: str
    is_private: bool
    watchers: list[WatcherInfo]


# ---- ユーザー向け例外 -----------------------------------------------------

class WatcherNotFound(LookupError):
    """指定されたログインIDのユーザーが Redmine に未登録。"""


# ---- メイン処理 -----------------------------------------------------------

def create_inquiry_ticket(req: CreateTicketRequest) -> CreateTicketResponse:
    """既定プロジェクトに問い合わせチケットを起票する。

    ウォッチャー方針:
      - 指定された watcher_login (= 質問者) を必ず登録
      - プロジェクトに「回答者」ロールを持つメンバー全員も登録
      - API 呼出元 (admin など) を Redmine の auto-watch 機能が watcher に
        追加した場合、上記 2 種類以外であれば事後に削除する

    Raises:
        WatcherNotFound: watcher_login が Redmine に存在しないとき
        RuntimeError:    プロジェクト・トラッカー・回答者ロール設定の不備
        他: Redmine API エラー (権限・バリデーション等)
    """
    rm = get_redmine()

    # 1. 質問者の存在確認
    questioner = find_user_by_login(rm, req.watcher_login)
    if questioner is None:
        raise WatcherNotFound(
            f"ログインID '{req.watcher_login}' のユーザーが Redmine に存在しません。"
            f" 先に POST /users でアカウントを作成してください。"
        )

    # 2. プロジェクト & トラッカー
    project_identifier = (
        settings.inquiry_project_identifier
        or settings.questioner_project_identifier
    )
    project = resolve_project(rm, project_identifier)
    tracker = resolve_tracker(rm, project, settings.inquiry_tracker_name or None)

    # 3. 回答者ロール保持ユーザーを抽出 (ロール未存在等の場合は空リスト)
    try:
        responder_user_ids = find_users_with_role_on_project(
            rm, project, settings.responder_role_name
        )
    except RuntimeError:
        responder_user_ids = []

    # 4. 意図したウォッチャー集合 (質問者 + 全回答者、重複除去)
    intended_ids = sorted({questioner.id, *responder_user_ids})

    # 5. チケット作成 (作成と同時にウォッチャー登録)
    issue = rm.issue.create(
        project_id=project.id,
        tracker_id=tracker.id,
        subject=req.title,
        description=req.description,
        is_private=req.is_private,
        watcher_user_ids=intended_ids,
    )

    # 6. 想定外の watcher を除去
    #    (Redmine の auto-watch が API 呼出ユーザー = admin 等を追加するため)
    issue_full = rm.issue.get(issue.id, include=["watchers"])
    actual_ids = {w.id for w in issue_full.watchers}
    for unwanted_id in actual_ids - set(intended_ids):
        try:
            issue.watcher.remove(unwanted_id)
        except Exception:
            # 個別の削除失敗はログに残す程度で良い (ここでは握りつぶす)
            pass

    # 7. レスポンス用にユーザー詳細 (login) を取得
    final_watchers: list[WatcherInfo] = []
    for uid in intended_ids:
        try:
            u = rm.user.get(uid)
            final_watchers.append(WatcherInfo(user_id=u.id, login=u.login))
        except Exception:
            final_watchers.append(WatcherInfo(user_id=uid, login=""))

    return CreateTicketResponse(
        issue_id=issue.id,
        project_identifier=project.identifier,
        tracker_name=tracker.name,
        subject=req.title,
        is_private=req.is_private,
        watchers=final_watchers,
    )
