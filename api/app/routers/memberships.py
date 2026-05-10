from fastapi import APIRouter, HTTPException

from app.redmine_client import RedmineNotConfigured
from app.services.membership_service import (
    AssignMembershipRequest,
    AssignMembershipResponse,
    UserNotFound,
    assign_membership,
)

router = APIRouter(prefix="/memberships", tags=["memberships"])


@router.post(
    "",
    response_model=AssignMembershipResponse,
    summary="既定プロジェクトに対象ユーザーを既定ロールで参加させる (idempotent)",
)
def assign_membership_endpoint(req: AssignMembershipRequest) -> AssignMembershipResponse:
    """指定された login のユーザーを、本 API の設定先プロジェクトに参加させる。

    対象プロジェクト: `QUESTIONER_PROJECT_IDENTIFIER`（既定 `demo`）
    付与ロール:       `QUESTIONER_ROLE_NAME`（既定 `質問者`）

    動作:
      - login が未登録      -> 404
      - 未参加              -> 新規 membership 作成 (status='created')
      - 参加済・対象ロール無 -> 既存 membership にロール **追加** (status='role_added')
      - 参加済・対象ロール有 -> 何もしない (status='already_member')

    既存ロールは削除しない (例: 既に Reporter で参加済 + 質問者を追加 → 両方持つ)。
    """
    try:
        return assign_membership(req)
    except RedmineNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except UserNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Redmine error: {type(e).__name__}: {e}",
        ) from e
