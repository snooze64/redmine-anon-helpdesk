"""crawler → embedder → vectorstore の組み合わせ。差分更新を行う。"""
from __future__ import annotations

from app.crawler.redmine_crawler import TicketChunk, crawl
from app.redmine_client import get_redmine
from app.store.embedder import embed_texts
from app.store.vectorstore import CrawlOutcome, doc_id, get_store


def crawl_and_index(project_identifier: str | None = None) -> CrawlOutcome:
    """対象プロジェクトを crawl → 差分判定 → 必要なものだけ埋め込み → upsert。

    差分判定:
      - 既存ストアの (issue_id -> updated_on) を取得
      - crawler が返した各チケットの updated_on と比較
      - 「未登録」 or 「updated_on が新しい」もののみ embedding + upsert
      - 何も変わってないものは skip (Ollama 呼出も skip → 高速)
    """
    rm = get_redmine()
    chunks: list[TicketChunk] = crawl(rm, project_identifier=project_identifier)

    store = get_store()
    existing = store.get_existing_updated_on()

    to_index: list[TicketChunk] = []
    inserted = 0
    updated = 0
    skipped = 0

    for c in chunks:
        prev = existing.get(c.issue_id)
        cur = str(c.metadata.get("updated_on", "") or "")
        if prev is None:
            inserted += 1
            to_index.append(c)
        elif cur and cur > prev:
            updated += 1
            to_index.append(c)
        else:
            skipped += 1

    if to_index:
        texts = [c.text for c in to_index]
        embs = embed_texts(texts)
        store.upsert(
            ids=[doc_id(c.issue_id) for c in to_index],
            documents=texts,
            embeddings=embs,
            metadatas=[c.metadata for c in to_index],
        )

    return CrawlOutcome(
        fetched=len(chunks),
        inserted=inserted,
        updated=updated,
        skipped_unchanged=skipped,
    )
