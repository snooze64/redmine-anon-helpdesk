"""類似検索エンドポイント (RAG リトリーバ単体テスト用)。"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.store.embedder import EmbeddingError, embed_one
from app.store.vectorstore import get_store

router = APIRouter(prefix="/search", tags=["search"])


class SearchHit(BaseModel):
    issue_id: int
    subject: str
    status: str
    url: str
    distance: float
    snippet: str


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


@router.get("", response_model=SearchResponse, summary="ベクトル類似検索")
def search(q: str, top_k: Optional[int] = None) -> SearchResponse:
    if not q.strip():
        raise HTTPException(status_code=422, detail="q is required")
    k = top_k or settings.retrieval_top_k

    try:
        emb = embed_one(q)
    except EmbeddingError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    store = get_store()
    results = store.query(emb, top_k=k)

    public_base = settings.redmine_public_url.rstrip("/")
    hits: list[SearchHit] = []
    for r in results:
        md = r.get("metadata") or {}
        doc = r.get("document") or ""
        snippet = doc[:200].replace("\n", " ")
        iid = int(md.get("issue_id", 0))
        # 既存 metadata の url は内部 URL の可能性があるので、
        # 現在の public_base から組み立て直す
        url = f"{public_base}/issues/{iid}" if iid else str(md.get("url", ""))
        hits.append(SearchHit(
            issue_id=iid,
            subject=str(md.get("subject", "")),
            status=str(md.get("status", "")),
            url=url,
            distance=float(r.get("distance", 0.0)),
            snippet=snippet,
        ))
    return SearchResponse(query=q, hits=hits)
