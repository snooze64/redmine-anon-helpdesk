"""チャットボット起票チケット作成のビジネスロジック。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import settings
from app.redmine_client import get_redmine, get_redmine_as
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
        description=(
            "起票元の質問者ログインID。Redmine に既に存在していること "
            "(POST /users で先に作成済みのもの)。"
            "settings.create_ticket_as_questioner=True (既定) の場合、"
            "このユーザーが author として impersonation 起票され、本人は "
            "private でも author rule で閲覧可能になる。"
        ),
    )
    is_private: bool = Field(
        default=False,
        description="True の場合、プライベートチケットとして作成",
    )
    chatbot_session_id: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "起票元のチャットボット session ID (監査用)。"
            "settings.chatbot_session_custom_field_id が 0 以外なら、"
            "該当カスタムフィールドにこの値が記録される。"
            "UI から起票したチケット (session_id 無し) と区別できる。"
        ),
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

    Author 方針 (privacy 関連で重要):
      - X-Redmine-Switch-User による impersonation で **質問者を author に
        する**。これにより質問者は自分の private チケットを author rule で
        閲覧可能になる (他の質問者の private は依然として見られない)。
      - 質問者ロールには `add_issues` (チケットの追加) 権限が必要。
        Redmine UI: 管理 → ロールと権限 → 質問者 → 「チケットの追加」を ON
        手順書: docs/manual_setup.md §1-1

    ウォッチャー方針:
      - 質問者は author になるので **watcher には登録しない** (通知は author
        として自動で飛ぶ)
      - プロジェクトに「回答者」ロールを持つメンバー全員を watcher に登録
      - Redmine の auto-watch で意図しないユーザー (admin など) が watcher
        に追加された場合は事後削除

    Raises:
        WatcherNotFound: watcher_login が Redmine に存在しないとき
        RuntimeError:    プロジェクト・トラッカー・回答者ロール設定の不備、
                         または質問者に add_issues 権限が無いとき
        他: Redmine API エラー (権限・バリデーション等)
    """
    rm_admin = get_redmine()

    # 1. 質問者の存在確認
    questioner = find_user_by_login(rm_admin, req.watcher_login)
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
    project = resolve_project(rm_admin, project_identifier)
    tracker = resolve_tracker(rm_admin, project, settings.inquiry_tracker_name or None)

    # 3. 回答者ロール保持ユーザーを抽出 (ロール未存在等の場合は空リスト)
    try:
        responder_user_ids = find_users_with_role_on_project(
            rm_admin, project, settings.responder_role_name
        )
    except RuntimeError:
        responder_user_ids = []

    # 4. 意図した watcher 集合を決める:
    #    - impersonation モード (create_ticket_as_questioner=True): 質問者は
    #      author なので watcher から除外。全回答者のみ。
    #    - 旧モード: 質問者 + 全回答者
    impersonate = settings.create_ticket_as_questioner
    if impersonate:
        intended_watcher_ids = sorted(set(responder_user_ids))
    else:
        intended_watcher_ids = sorted({questioner.id, *responder_user_ids})

    # 5. 監査用カスタムフィールド (任意)
    create_kwargs: dict = dict(
        project_id=project.id,
        tracker_id=tracker.id,
        subject=req.title,
        description=req.description,
        is_private=req.is_private,
        watcher_user_ids=intended_watcher_ids,
    )
    cf_id = settings.chatbot_session_custom_field_id
    if cf_id and req.chatbot_session_id:
        create_kwargs["custom_fields"] = [
            {"id": int(cf_id), "value": req.chatbot_session_id}
        ]

    # 6. チケット作成。
    #    - impersonation モード: X-Redmine-Switch-User で質問者として起票
    #      (private ticket を質問者本人だけが author rule で見られるようにする)
    #    - 旧モード: admin として起票 (private にすると質問者本人も見られない)
    rm_creator = get_redmine_as(req.watcher_login) if impersonate else rm_admin
    try:
        issue = rm_creator.issue.create(**create_kwargs)
    except Exception as e:
        if impersonate:
            # 質問者ロールに add_issues 権限が無いとここで 403/422 になる
            raise RuntimeError(
                f"質問者 '{req.watcher_login}' としてのチケット作成に失敗: {e}. "
                f"質問者ロールに「チケットの追加 (add_issues)」権限が付いているか "
                f"docs/manual_setup.md §1-1 を確認してください。"
                f"(回避: settings.create_ticket_as_questioner=False で admin 起票に戻せます)"
            ) from e
        raise

    # 7. 意図しない watcher (auto-watch されてしまった admin 等) を除去。
    #    削除は admin 権限で行う (質問者は他人の watcher 操作権限が無いため)。
    intended_set = set(intended_watcher_ids)
    issue_admin = rm_admin.issue.get(issue.id, include=["watchers"])
    actual_ids = {w.id for w in issue_admin.watchers}
    for unwanted_id in actual_ids - intended_set:
        # impersonation モードでは質問者は author なので、auto-watch で watcher
        # に入っていても残すのが自然 (本人への通知が飛ぶ)。
        if impersonate and unwanted_id == questioner.id:
            continue
        try:
            issue_admin.watcher.remove(unwanted_id)
        except Exception:
            pass

    # 8. レスポンス用に watcher の login を取得
    final_watchers: list[WatcherInfo] = []
    for uid in intended_watcher_ids:
        try:
            u = rm_admin.user.get(uid)
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
