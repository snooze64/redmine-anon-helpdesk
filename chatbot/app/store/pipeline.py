"""crawler → embedder → vectorstore の組み合わせ。差分更新を行う。"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.crawler.redmine_crawler import TicketChunk, crawl
from app.redmine_client import get_redmine
from app.store.embedder import embed_texts
from app.store.vectorstore import doc_id, get_store


@dataclass
class CrawlOutcome:
    fetched: int            # 公開チケットの取得数 (= inserted + updated + skipped_unchanged)
    inserted: int           # 未登録 → 新規 index
    updated: int            # 登録済 → updated_on が更新されたので再 embed して上書き
    deleted: int            # 登録済 (公開時に取り込んでいた) → 今 private 化されたので削除
    skipped_unchanged: int  # 公開状態のまま updated_on も変わっていない (no-op)
    skipped_private: int    # private のまま & まだ index されていない (no-op)


def crawl_and_index(project_identifier: str | None = None) -> CrawlOutcome:
    """対象プロジェクトを crawl → 差分判定 → 必要なものだけ埋め込み → upsert。

    プライベート扱い (settings.crawl_exclude_private=True 既定):
      - is_private=True のチケット:
          - 既に index されている → 削除 (公開時に取り込んだものが private 化された場合)
          - 未登録 → 何もしない (skipped_private)
      - is_private=False に戻ったチケット:
          - Redmine 側で updated_on が更新されるため、通常の "insert" or "update"
            のパスに自然に乗る (特別な分岐は不要)

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
    deleted = 0
    skipped_unchanged = 0
    skipped_private = 0

    for c in chunks:
        is_private = bool(c.metadata.get("is_private", False))
        prev = existing.get(c.issue_id)
        cur = str(c.metadata.get("updated_on", "") or "")

        if settings.crawl_exclude_private and is_private:
            if prev is not None:
                # 公開時に index 済 → private 化されたので削除
                store.delete_by_issue_id(c.issue_id)
                deleted += 1
            else:
                # private のまま、index もしていない
                skipped_private += 1
            continue

        # ここから公開チケットのみ
        if prev is None:
            # 新規 (もしくは「private → public」になって初めて拾った)
            inserted += 1
            to_index.append(c)
        elif cur and cur > prev:
            updated += 1
            to_index.append(c)
        else:
            skipped_unchanged += 1

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
        # private チケットは「取得」に含めない (= 公開チケットのみカウント)。
        # こうすると "取得 = 新規 + 更新 + スキップ(変更なし)" が常に一致する。
        fetched=inserted + updated + skipped_unchanged,
        inserted=inserted,
        updated=updated,
        deleted=deleted,
        skipped_unchanged=skipped_unchanged,
        skipped_private=skipped_private,
    )
