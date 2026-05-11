from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.redmine_client import RedmineNotConfigured
from app.store.pipeline import crawl_and_index
from app.store.embedder import EmbeddingError

router = APIRouter(prefix="/crawl", tags=["crawl"])


class CrawlRequest(BaseModel):
    project_identifier: Optional[str] = None  # 空なら settings の既定


class CrawlResponse(BaseModel):
    project_identifier: str
    fetched: int
    inserted: int           # 新規 index
    updated: int            # updated_on 更新による再 embed
    deleted: int            # 既に index 済が private 化されたので削除
    skipped_unchanged: int  # 公開かつ変更なし
    skipped_private: int    # private のまま (未 index)


@router.post("", response_model=CrawlResponse, summary="手動 crawl + 差分 index (private は除外)")
def trigger_crawl(req: Optional[CrawlRequest] = None) -> CrawlResponse:
    pid = (req.project_identifier if req else None) or settings.crawl_project_identifier
    try:
        outcome = crawl_and_index(project_identifier=pid)
    except RedmineNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except EmbeddingError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Crawl error: {type(e).__name__}: {e}"
        ) from e

    return CrawlResponse(
        project_identifier=pid,
        fetched=outcome.fetched,
        inserted=outcome.inserted,
        updated=outcome.updated,
        deleted=outcome.deleted,
        skipped_unchanged=outcome.skipped_unchanged,
        skipped_private=outcome.skipped_private,
    )
