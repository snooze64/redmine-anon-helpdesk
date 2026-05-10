from fastapi import APIRouter, HTTPException

from app.redmine_client import RedmineNotConfigured
from app.services.ticket_service import (
    CreateTicketRequest,
    CreateTicketResponse,
    WatcherNotFound,
    create_inquiry_ticket,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post(
    "",
    response_model=CreateTicketResponse,
    summary="チャットボットから問い合わせチケットを起票",
)
def create_ticket_endpoint(req: CreateTicketRequest) -> CreateTicketResponse:
    """既定プロジェクトに問い合わせチケットを作成する。

    - 起票プロジェクト: 環境変数 `INQUIRY_PROJECT_IDENTIFIER`
      (未指定時は質問者アカウントと同じ既定プロジェクトを使用)
    - トラッカー: `INQUIRY_TRACKER_NAME` (未指定時はプロジェクトの先頭トラッカー)
    - ウォッチャー: 指定された login ID のユーザーを 1 名登録
    - is_private: True ならプライベートチケットとして作成
    """
    try:
        return create_inquiry_ticket(req)
    except RedmineNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except WatcherNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        # プロジェクト・トラッカーの未存在等
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Redmine error: {type(e).__name__}: {e}",
        ) from e
