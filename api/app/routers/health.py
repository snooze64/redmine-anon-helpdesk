from fastapi import APIRouter, HTTPException

from app.redmine_client import RedmineNotConfigured, get_redmine

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def liveness() -> dict:
    """シンプルなヘルスチェック (外部依存なし)。"""
    return {"status": "ok"}


@router.get("/redmine")
def redmine_check() -> dict:
    """Redmine への到達性と認証成功を確認する。

    成功時: 200 + 認証ユーザー情報
    認証情報未設定: 503
    Redmine への接続失敗 / 認証失敗: 502
    """
    try:
        rm = get_redmine()
        user = rm.user.get("current")
        return {
            "status": "ok",
            "redmine_user": getattr(user, "login", None),
            "redmine_user_id": getattr(user, "id", None),
            "is_admin": getattr(user, "admin", None),
        }
    except RedmineNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Redmine への接続/認証に失敗: {type(e).__name__}: {e}",
        ) from e
