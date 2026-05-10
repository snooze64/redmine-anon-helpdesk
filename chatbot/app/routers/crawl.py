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
    inserted: int
    updated: int
    skipped_unchanged: int


@router.post("", response_model=CrawlResponse, summary="手動 crawl + 差分 index")
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
        skipped_unchanged=outcome.skipped_unchanged,
    )
