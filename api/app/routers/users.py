from fastapi import APIRouter, HTTPException

from app.redmine_client import RedmineNotConfigured
from app.services.user_service import (
    CreateUserRequest,
    CreateUserResponse,
    create_or_get_user,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=CreateUserResponse,
    summary="Redmine にユーザーを作成 (idempotent)",
)
def create_user_endpoint(req: CreateUserRequest) -> CreateUserResponse:
    """ログインIDが未登録なら作成、登録済みなら既存情報を返す。

    プロジェクトメンバーシップ・ロール付与は本エンドポイントの責務外。
    必要なら別途 `POST /memberships` を呼び出すこと。

    新規作成時:
      - 氏名はランダム ("User" + 8 桁の 16 進文字列) — 匿名性確保のため
      - 言語: `QUESTIONER_LANGUAGE` (既定 `ja`)

    既存時:
      - 何も変更せず、現在の Redmine ユーザー情報を返す
      - メールやパスワードは絶対に上書きしない
    """
    try:
        return create_or_get_user(req)
    except RedmineNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Redmine error: {type(e).__name__}: {e}",
        ) from e
