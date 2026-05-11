"""Chroma ベクトルストアのラッパ。

仕様:
  - 1 チケット = 1 ドキュメント (id = "issue:<issue_id>")
  - メタデータに updated_on を保存し、差分更新の判定に使う
  - upsert (新規) / 更新 (元から存在する id を上書き) / 削除 をサポート
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings


# CrawlOutcome は pipeline.py 側に移動済 (こちらは後方互換用に残しても良いが未使用)
@dataclass
class CrawlOutcome:
    fetched: int
    inserted: int
    updated: int
    skipped_unchanged: int
    deleted: int = 0
    skipped_private: int = 0


def _doc_id(issue_id: int) -> str:
    return f"issue:{issue_id}"


class VectorStore:
    """Chroma を永続化モードで使う薄いラッパ。"""

    def __init__(self) -> None:
        self.client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        # embedding は外部 (Ollama) でやるので、ここでは embedding_function は登録しない
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

    # ---- メタ取得 ---------------------------------------------------------

    def get_existing_updated_on(self) -> dict[int, str]:
        """既に格納済みの (issue_id -> updated_on) の辞書を返す。差分判定用。"""
        out: dict[int, str] = {}
        try:
            res = self.collection.get(include=["metadatas"])
        except Exception:
            return out
        for md in res.get("metadatas", []) or []:
            if not md:
                continue
            iid = md.get("issue_id")
            uo = md.get("updated_on", "")
            if isinstance(iid, int):
                out[iid] = str(uo or "")
        return out

    def count(self) -> int:
        try:
            return int(self.collection.count())
        except Exception:
            return 0

    # ---- 投入 -------------------------------------------------------------

    def upsert(
        self, ids: list[str], documents: list[str],
        embeddings: list[list[float]], metadatas: list[dict],
    ) -> None:
        """upsert は ID が既存なら更新、なければ追加。"""
        if not ids:
            return
        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def delete_by_issue_id(self, issue_id: int) -> None:
        try:
            self.collection.delete(ids=[_doc_id(issue_id)])
        except Exception:
            pass

    # ---- 検索 -------------------------------------------------------------

    def query(
        self,
        query_embedding: list[float],
        top_k: int,
        where: Optional[dict] = None,
    ) -> list[dict]:
        """類似検索。返す形式:
            [{"id":..., "document":..., "metadata":{...}, "distance":...}, ...]
        """
        res = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        mds = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        return [
            {"id": i, "document": d, "metadata": m, "distance": dist}
            for i, d, m, dist in zip(ids, docs, mds, dists)
        ]


# モジュール内シングルトン
_store: Optional[VectorStore] = None


def get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


def doc_id(issue_id: int) -> str:
    return _doc_id(issue_id)
